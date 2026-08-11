from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from ai_layer.core.paths import project_state_path
from ai_layer.db.models import Project, RepositorySnapshot, Task, TaskStage
from ai_layer.domain.ports import SnapshotReference, WorkflowSnapshotStore


SNAPSHOT_STORAGE_BACKEND = "postgresql-json"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_key(task: Task) -> str:
    return f"T-{int(task.sequence):04d}"


def task_root(project: Project) -> Path:
    root = project_state_path(project.root_path, "tasks")
    root.mkdir(parents=True, exist_ok=True)
    return root


def task_work_dir(project: Project, task_id: UUID | str) -> Path:
    path = task_root(project) / str(task_id)
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked task state directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_lock(project: Project) -> Path:
    return task_root(project) / "state.lock"


def atomic_write_json(path: Path, payload: dict) -> None:
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked task state file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp_name, 0o600)
        except OSError:
            pass
        os.replace(tmp_name, path)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def read_json(path: Path) -> dict | None:
    if path.is_symlink() or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def memory_hash_seed(project: Project) -> dict:
    path = project_state_path(project.root_path, "memory", "file_state.json")
    raw = read_json(path) or {}
    files: dict[str, dict] = {}
    for rel, item in raw.items():
        if not isinstance(rel, str) or not isinstance(item, dict):
            continue
        content_hash = str(item.get("content_sha256") or "").strip()
        if not content_hash:
            continue
        try:
            size = int(item.get("size", -1))
            mtime_ns = int(item.get("mtime_ns", -1))
            ctime_ns = int(item.get("ctime_ns", -1))
        except (TypeError, ValueError):
            continue
        files[rel] = {
            "sha256": content_hash,
            "size": size,
            "mtime_ns": mtime_ns,
            "ctime_ns": ctime_ns,
        }
    return {"files": files}


def baseline_path(project: Project, task: Task) -> Path:
    return task_work_dir(project, task.id) / "baseline.json"


def stage_start_path(project: Project, task: Task, stage: TaskStage) -> Path:
    return task_work_dir(project, task.id) / f"stage-{stage.id}-start.json"


def write_stage_start(project: Project, task: Task, stage: TaskStage, state: dict) -> None:
    """Materialize a disposable filesystem projection of a durable DB snapshot."""
    atomic_write_json(stage_start_path(project, task, stage), state)


def _validated_state(state: dict, *, expected_digest: str | None = None) -> dict:
    if not isinstance(state, dict):
        raise RuntimeError("Repository snapshot payload is not an object.")
    digest = str(state.get("digest") or "")
    files = state.get("files")
    if len(digest) != 64 or not isinstance(files, dict):
        raise RuntimeError("Repository snapshot payload is incomplete or malformed.")
    if expected_digest and digest != expected_digest:
        raise RuntimeError(
            "Repository snapshot digest does not match the workflow state that references it."
        )
    file_count = int(state.get("file_count", len(files)))
    if file_count != len(files):
        raise RuntimeError("Repository snapshot file_count does not match its file map.")
    return dict(state)


class SqlAlchemyWorkflowSnapshotStore:
    """PostgreSQL/SQLAlchemy adapter for the persistence-neutral snapshot port."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _reference(row: RepositorySnapshot) -> SnapshotReference:
        return SnapshotReference(
            id=row.id,
            project_id=row.project_id,
            digest=row.digest,
            file_count=row.file_count,
            storage_backend=row.storage_backend,
            schema_version=row.schema_version,
        )

    def create(
        self,
        *,
        project_id: UUID,
        state: dict,
        snapshot_kind: str,
    ) -> SnapshotReference:
        payload = _validated_state(state)
        row = RepositorySnapshot(
            project_id=project_id,
            snapshot_kind=str(snapshot_kind)[:32],
            schema_version=max(1, int(payload.get("schema") or 1)),
            digest=str(payload["digest"]),
            file_count=int(payload["file_count"]),
            storage_backend=SNAPSHOT_STORAGE_BACKEND,
            state=payload,
        )
        self.db.add(row)
        self.db.flush()
        return self._reference(row)

    def get(self, snapshot_id: UUID) -> SnapshotReference | None:
        row = self.db.get(RepositorySnapshot, snapshot_id)
        return self._reference(row) if row is not None else None

    def load(self, snapshot_id: UUID, *, expected_digest: str) -> dict:
        row = self.db.get(RepositorySnapshot, snapshot_id)
        if row is None:
            raise RuntimeError("Durable repository snapshot reference points to a missing row.")
        if row.storage_backend != SNAPSHOT_STORAGE_BACKEND:
            raise RuntimeError(f"Unsupported repository snapshot backend: {row.storage_backend}")
        if row.digest != expected_digest:
            raise RuntimeError("Durable repository snapshot metadata digest mismatch.")
        return _validated_state(dict(row.state or {}), expected_digest=expected_digest)


def snapshot_store(db: Session) -> WorkflowSnapshotStore:
    return SqlAlchemyWorkflowSnapshotStore(db)


def create_repository_snapshot(
    db: Session,
    *,
    project_id: UUID,
    state: dict,
    snapshot_kind: str,
) -> SnapshotReference:
    return snapshot_store(db).create(
        project_id=project_id,
        state=state,
        snapshot_kind=snapshot_kind,
    )


def bind_task_baseline(db: Session, project: Project, task: Task, state: dict) -> SnapshotReference:
    if task.baseline_snapshot_id is not None:
        ref = snapshot_store(db).get(task.baseline_snapshot_id)
        if ref is None:
            raise RuntimeError("Task baseline snapshot reference points to missing durable state.")
        return ref
    ref = create_repository_snapshot(
        db,
        project_id=project.id,
        state=state,
        snapshot_kind="task_baseline",
    )
    task.baseline_snapshot_id = ref.id
    return ref


def bind_stage_start(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    state: dict,
    *,
    snapshot_id=None,
) -> SnapshotReference:
    if stage.start_snapshot_id is not None:
        ref = snapshot_store(db).get(stage.start_snapshot_id)
        if ref is None:
            raise RuntimeError("Task stage snapshot reference points to missing durable state.")
        return ref
    ref = snapshot_store(db).get(snapshot_id) if snapshot_id is not None else None
    if ref is None:
        ref = create_repository_snapshot(
            db,
            project_id=project.id,
            state=state,
            snapshot_kind="stage_start",
        )
    if ref.project_id != project.id:
        raise RuntimeError("Stage start snapshot belongs to another project.")
    if ref.digest != str(state.get("digest") or ""):
        raise RuntimeError("Stage start snapshot does not match the requested repository state.")
    stage.start_snapshot_id = ref.id
    return ref


def _snapshot_state(db: Session, snapshot_id: UUID, *, expected_digest: str) -> dict:
    return snapshot_store(db).load(snapshot_id, expected_digest=expected_digest)


def load_stage_start(db: Session, project: Project, task: Task, stage: TaskStage) -> dict:
    expected = str(stage.repository_digest_before or "")
    if stage.start_snapshot_id is not None:
        return _snapshot_state(db, stage.start_snapshot_id, expected_digest=expected)

    # Controlled compatibility path for an in-flight task created before the durable snapshot schema.
    state = read_json(stage_start_path(project, task, stage))
    if not state:
        raise RuntimeError(
            f"Task {task_key(task)} stage {stage.id} is missing its legacy repository-start "
            "snapshot and cannot be promoted to durable recovery state."
        )
    payload = _validated_state(state, expected_digest=expected)
    bind_stage_start(db, project, task, stage, payload)
    db.flush()
    return payload


def load_baseline(db: Session, project: Project, task: Task) -> dict:
    expected = str(task.baseline_digest or "")
    if task.baseline_snapshot_id is not None:
        return _snapshot_state(db, task.baseline_snapshot_id, expected_digest=expected)

    state = read_json(baseline_path(project, task))
    if not state:
        raise RuntimeError(
            f"Task {task_key(task)} is missing its legacy repository baseline and cannot be "
            "promoted to durable recovery state."
        )
    payload = _validated_state(state, expected_digest=expected)
    bind_task_baseline(db, project, task, payload)
    db.flush()
    return payload


def materialize_baseline(db: Session, project: Project, task: Task) -> None:
    atomic_write_json(baseline_path(project, task), load_baseline(db, project, task))


def materialize_stage_start(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
) -> None:
    write_stage_start(project, task, stage, load_stage_start(db, project, task, stage))
