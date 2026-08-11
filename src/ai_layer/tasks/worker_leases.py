from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.core.filelock import directory_lock
from ai_layer.db.models import Project, Task, TaskStage, utcnow
from ai_layer.observability.domain_events import append_event
from ai_layer.tasks.concurrency import active_stage_for_update, bump_task_version, lock_project
from ai_layer.tasks.constants import (
    DEFAULT_WORKER_LEASE_SECONDS,
    MAX_WORKER_LEASE_SECONDS,
    MIN_WORKER_LEASE_SECONDS,
)
from ai_layer.tasks.contracts import _bounded_text
from ai_layer.tasks.state_store import (
    load_stage_start as _load_stage_start,
)
from ai_layer.tasks.state_store import (
    materialize_stage_start,
)
from ai_layer.tasks.state_store import (
    task_lock as _task_lock,
)
from ai_layer.tasks.views import _active_stage, _create_stage, _persist_task_view
from ai_layer.workspace.repository import capture_repository_state, repository_changes


def _bounded_lease_seconds(value: int | None) -> int:
    seconds = DEFAULT_WORKER_LEASE_SECONDS if value is None else int(value)
    if seconds < MIN_WORKER_LEASE_SECONDS or seconds > MAX_WORKER_LEASE_SECONDS:
        raise ValueError(
            f"worker lease must be between {MIN_WORKER_LEASE_SECONDS} and "
            f"{MAX_WORKER_LEASE_SECONDS} seconds"
        )
    return seconds


def start_worker_lease(
    stage: TaskStage,
    *,
    lease_seconds: int | None = None,
    now: datetime | None = None,
) -> None:
    current = now or utcnow()
    seconds = _bounded_lease_seconds(lease_seconds)
    stage.worker_heartbeat_at = current
    stage.worker_lease_expires_at = current + timedelta(seconds=seconds)


def heartbeat_worker(
    db: Session,
    project: Project,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> dict:
    worker = str(worker_id or "").strip()
    if not worker:
        raise ValueError("task_worker_heartbeat: `worker_id` is required")
    with directory_lock(_task_lock(project), timeout_seconds=15):
        task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status == "active")
            .order_by(Task.updated_at.desc())
            .limit(1)
            .with_for_update()
        )
        if task is None:
            raise RuntimeError("No active task exists for this project.")
        stage = _active_stage(db, task)
        if stage is None or not stage.worker_id:
            raise RuntimeError("No delegated active worker exists to heartbeat.")
        if stage.worker_id != worker:
            raise RuntimeError(
                f"Active stage is delegated to `{stage.worker_id}`, not `{worker}`; "
                "heartbeat cannot rebind worker identity."
            )
        start_worker_lease(stage, lease_seconds=lease_seconds)
        bump_task_version(task)
        task.updated_at = utcnow()
        append_event(
            db,
            event_type="AgentHeartbeat",
            project=project,
            aggregate_type="task_stage",
            aggregate_id=str(stage.id),
            payload={
                "worker_id": worker,
                "lease_expires_at": stage.worker_lease_expires_at.isoformat()
                if stage.worker_lease_expires_at
                else None,
            },
        )
        db.commit()
        return _persist_task_view(db, project, task)


def _block_missing_recovery_state(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    reason: str,
) -> dict:
    stage.status = "invalid"
    stage.outcome = "worker_recovery_state_missing"
    stage.summary = reason
    stage.completed_at = utcnow()
    task.status = "blocked"
    task.blocked_reason = (
        "WORKER_RECOVERY_STATE_MISSING: the delegated stage lost its durable repository-start "
        "snapshot. AI Layer cannot safely infer provenance. Restore a known state and cancel/adopt "
        "the intended work before continuing."
    )
    bump_task_version(task)
    task.updated_at = utcnow()
    append_event(
        db,
        event_type="StageInvalidated",
        project=project,
        aggregate_type="task_stage",
        aggregate_id=str(stage.id),
        payload={"kind": stage.kind, "outcome": stage.outcome, "worker_id": stage.worker_id},
    )
    append_event(
        db,
        event_type="TaskBlocked",
        project=project,
        aggregate_type="task",
        aggregate_id=str(task.id),
        payload={"reason": task.blocked_reason, "stage_id": str(stage.id)},
    )
    db.commit()
    return _persist_task_view(db, project, task)


def _recover_worker_stage(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    reason: str,
    failure_outcome: str,
) -> dict:
    try:
        start_state = _load_stage_start(db, project, task, stage)
    except RuntimeError:
        return _block_missing_recovery_state(db, project, task, stage, reason=reason)

    current_state = capture_repository_state(project.root_path, previous=start_state)
    drift = repository_changes(start_state, current_state)
    worker = stage.worker_id
    stage.status = "invalid"
    stage.outcome = failure_outcome if not drift["total"] else f"{failure_outcome}_with_changes"
    stage.summary = reason
    stage.changes = drift
    stage.repository_digest_before = str(start_state.get("digest") or "")
    stage.repository_digest_after = str(current_state.get("digest") or "")
    stage.completed_at = utcnow()
    append_event(
        db,
        event_type="AgentFailed",
        project=project,
        aggregate_type="task_stage",
        aggregate_id=str(stage.id),
        payload={
            "worker_id": worker,
            "reason": reason,
            "repository_changes": drift.get("total", 0),
        },
    )
    append_event(
        db,
        event_type="StageInvalidated",
        project=project,
        aggregate_type="task_stage",
        aggregate_id=str(stage.id),
        payload={"kind": stage.kind, "outcome": stage.outcome, "worker_id": worker},
    )
    if drift["total"]:
        task.status = "blocked"
        task.blocked_reason = (
            "WORKER_DISCONNECTED_WITH_CHANGES: the lost or expired worker left repository changes. "
            "AI Layer will not attribute or rebind them automatically. Restore the stage-start state "
            "and resume, or cancel and use task_adopt if the changes should be retained."
        )
        append_event(
            db,
            event_type="TaskBlocked",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={"reason": task.blocked_reason, "stage_id": str(stage.id)},
        )
    else:
        replacement = _create_stage(
            db,
            task,
            kind=stage.kind,
            state=current_state,
            review_round=stage.review_round,
            fix_round=stage.fix_round,
        )
    bump_task_version(task)
    task.updated_at = utcnow()
    db.commit()
    if not drift["total"]:
        try:
            materialize_stage_start(db, project, task, replacement)
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
    return _persist_task_view(db, project, task)


def recover_disconnected_worker(db: Session, project: Project, *, reason: str) -> dict:
    reason = _bounded_text(
        reason,
        field="task_worker_disconnected: `reason`",
        max_chars=1000,
        required=True,
        redact=True,
    )
    with directory_lock(_task_lock(project), timeout_seconds=15):
        task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status == "active")
            .order_by(Task.updated_at.desc())
            .limit(1)
            .with_for_update()
        )
        if task is None:
            raise RuntimeError("No active task exists for this project.")
        stage = _active_stage(db, task)
        if stage is None or not stage.worker_id:
            raise RuntimeError("No delegated active worker exists to recover.")
        return _recover_worker_stage(
            db,
            project,
            task,
            stage,
            reason=reason,
            failure_outcome="worker_disconnected",
        )


def reap_stale_worker_leases(db: Session, *, now: datetime | None = None) -> dict:
    current = now or utcnow()
    candidates = db.execute(
        select(TaskStage.id, Task.id, Project.id)
        .join(Task, Task.id == TaskStage.task_id)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.status == "active",
            TaskStage.status == "active",
            TaskStage.worker_id != "",
            TaskStage.worker_lease_expires_at.is_not(None),
            TaskStage.worker_lease_expires_at <= current,
        )
        .order_by(TaskStage.worker_lease_expires_at, TaskStage.id)
    ).all()
    recovered = 0
    blocked = 0
    skipped = 0
    ids: list[str] = []
    for stage_id, task_id, project_id in candidates:
        project = db.get(Project, project_id)
        if project is None:
            skipped += 1
            continue
        with directory_lock(_task_lock(project), timeout_seconds=15):
            lock_project(db, project)
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            if task is None:
                skipped += 1
                continue
            stage = active_stage_for_update(db, task)
            if (
                stage is None
                or stage.id != stage_id
                or task.status != "active"
                or stage.status != "active"
                or not stage.worker_id
                or stage.worker_lease_expires_at is None
                or stage.worker_lease_expires_at > current
            ):
                skipped += 1
                continue
            append_event(
                db,
                event_type="AgentLeaseExpired",
                project=project,
                aggregate_type="task_stage",
                aggregate_id=str(stage.id),
                payload={
                    "worker_id": stage.worker_id,
                    "lease_expires_at": stage.worker_lease_expires_at.isoformat(),
                },
            )
            result = _recover_worker_stage(
                db,
                project,
                task,
                stage,
                reason="durable worker lease expired without heartbeat",
                failure_outcome="worker_lease_expired",
            )
            ids.append(str(stage.id))
            if result.get("status") == "blocked":
                blocked += 1
            else:
                recovered += 1
    return {
        "ok": True,
        "expired": len(candidates),
        "recovered": recovered,
        "blocked": blocked,
        "skipped": skipped,
        "stage_ids": ids,
    }
