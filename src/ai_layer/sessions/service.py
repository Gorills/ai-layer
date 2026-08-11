from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from ai_layer.core.paths import project_state_path
from ai_layer.core.redaction import redact_secrets
from ai_layer.db.models import Decision, Project, WorkSession
from ai_layer.memory.embeddings import get_embedder

SNAPSHOT_SCHEMA = 2
SNAPSHOT_RETENTION = 200
SNAPSHOT_INDEX = "index.json"
MAX_SESSION_TEXT_CHARS = 8_000
MAX_SESSION_LIST_ITEMS = 24
MAX_SESSION_ITEM_CHARS = 2_000
MAX_SESSION_PAYLOAD_BYTES = 64_000
_PENDING_SNAPSHOTS_KEY = "ai_layer_pending_session_snapshots"


def _snapshot_dir(project: Project) -> Path:
    return _snapshot_dir_for_root(project.root_path)


def _snapshot_dir_for_root(root: str | Path) -> Path:
    path = project_state_path(root, "sessions")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _is_committed_snapshot(data: dict) -> bool:
    return (
        data.get("snapshot_schema") == SNAPSHOT_SCHEMA and data.get("commit_state") == "committed"
    )


def _read_snapshot(path: Path, *, committed_only: bool = True) -> dict | None:
    if path.is_symlink():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    required = {"id", "goal", "current_state", "created_at"}
    if not isinstance(data, dict) or not required <= set(data):
        return None
    if committed_only and not _is_committed_snapshot(data):
        # Pre-v0.6.2 snapshots can have been published before their surrounding DB transaction
        # committed. They are not authoritative recovery evidence unless a matching DB row exists.
        return None
    return data


def _created_at_key(item: dict) -> float:
    raw = str(item.get("created_at", "")).strip()
    if not raw:
        return 0.0
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _load_snapshot_index(directory: Path) -> list[str] | None:
    path = directory / SNAPSHOT_INDEX
    if path.is_symlink() or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SNAPSHOT_SCHEMA:
        return None
    ids = data.get("ids")
    if not isinstance(ids, list):
        return None
    return [str(item) for item in ids if str(item).strip()][:SNAPSHOT_RETENTION]


def _write_snapshot_index(directory: Path, snapshots: list[dict]) -> None:
    ordered = sorted(snapshots, key=_created_at_key, reverse=True)[:SNAPSHOT_RETENTION]
    _atomic_write_json(
        directory / SNAPSHOT_INDEX,
        {
            "schema": SNAPSHOT_SCHEMA,
            "ids": [str(item["id"]) for item in ordered],
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _disk_sessions(project: Project, limit: int = SNAPSHOT_RETENTION) -> list[dict]:
    directory = _snapshot_dir(project)
    wanted = max(1, min(int(limit), SNAPSHOT_RETENTION))
    indexed = _load_snapshot_index(directory)
    snapshots: list[dict] = []
    if indexed is not None:
        for session_id in indexed[:wanted]:
            item = _read_snapshot(directory / f"{session_id}.json")
            if item:
                snapshots.append(item)
        snapshots.sort(key=_created_at_key, reverse=True)
        return snapshots[:wanted]

    # One-time compatibility recovery for installations created before the bounded index existed.
    for path in directory.glob("*.json"):
        if path.name in {"latest.json", SNAPSHOT_INDEX}:
            continue
        item = _read_snapshot(path)
        if item:
            snapshots.append(item)
    snapshots.sort(key=_created_at_key, reverse=True)
    if snapshots:
        try:
            _write_snapshot_index(directory, snapshots)
        except OSError:
            pass
    return snapshots[:wanted]


def _persist_snapshot(project: Project, snapshot: dict, *, committed: bool = False) -> None:
    """Persist a disk projection.

    Only snapshots written after a successful SQLAlchemy commit are marked authoritative. The
    optional non-committed form exists solely for diagnostics/tests and is never used by recovery.
    """
    directory = _snapshot_dir(project)
    payload = dict(snapshot)
    payload["snapshot_schema"] = SNAPSHOT_SCHEMA
    payload["commit_state"] = "committed" if committed else "provisional"
    payload["storage"] = "snapshot"
    if not committed:
        _atomic_write_json(directory / f"{payload['id']}.provisional.json", payload)
        return

    _atomic_write_json(directory / f"{payload['id']}.json", payload)
    _atomic_write_json(directory / "latest.json", payload)

    existing = _disk_sessions(project, limit=SNAPSHOT_RETENTION)
    by_id = {str(item["id"]): item for item in existing}
    by_id[str(payload["id"])] = payload
    ordered = sorted(by_id.values(), key=_created_at_key, reverse=True)
    _write_snapshot_index(directory, ordered)
    keep = {str(item["id"]) for item in ordered[:SNAPSHOT_RETENTION]}
    for path in directory.glob("*.json"):
        if path.name in {"latest.json", SNAPSHOT_INDEX}:
            continue
        if path.stem not in keep:
            path.unlink(missing_ok=True)


def _queue_snapshot_after_commit(db: Session, project: Project, snapshot: dict) -> None:
    queue = db.info.setdefault(_PENDING_SNAPSHOTS_KEY, [])
    queue.append((str(project.root_path), dict(snapshot)))


@event.listens_for(Session, "after_commit")
def _publish_committed_session_snapshots(
    db: Session,
) -> None:  # pragma: no cover - exercised via commit
    queued = list(db.info.pop(_PENDING_SNAPSHOTS_KEY, []))
    for root, snapshot in queued:
        try:
            project = type("ProjectSnapshotTarget", (), {"root_path": root})()
            _persist_snapshot(project, snapshot, committed=True)
        except Exception:
            # PostgreSQL is canonical. No projection/serialization failure may turn an already
            # successful DB commit into an apparent transaction failure that callers could retry.
            continue


@event.listens_for(Session, "after_rollback")
def _discard_rolled_back_session_snapshots(db: Session) -> None:  # pragma: no cover - event hook
    db.info.pop(_PENDING_SNAPSHOTS_KEY, None)


def _session_text(
    value: object, *, field: str, required: bool = False, max_chars: int = MAX_SESSION_TEXT_CHARS
) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"session_save: `{field}` is required.")
    if len(text) > max_chars:
        raise ValueError(f"session_save: `{field}` exceeds the {max_chars}-character limit.")
    return redact_secrets(text)


def _session_list(values: list[str] | None, *, field: str) -> list[str]:
    raw = list(values or [])
    if len(raw) > MAX_SESSION_LIST_ITEMS:
        raise ValueError(
            f"session_save: `{field}` exceeds the {MAX_SESSION_LIST_ITEMS}-item limit."
        )
    result: list[str] = []
    for index, value in enumerate(raw, start=1):
        text = _session_text(value, field=f"{field}[{index}]", max_chars=MAX_SESSION_ITEM_CHARS)
        if text:
            result.append(text)
    return result


def _bounded_session_payload(
    *,
    goal: str,
    completed_actions: list[str],
    current_state: str,
    next_steps: list[str],
    important_decisions: list[str],
    verified_facts: list[str],
    notable_findings: list[str],
) -> dict:
    payload = {
        "goal": _session_text(goal, field="goal", required=True),
        "completed_actions": _session_list(completed_actions, field="completed_actions"),
        "current_state": _session_text(current_state, field="current_state", required=True),
        "next_steps": _session_list(next_steps, field="next_steps"),
        "important_decisions": _session_list(important_decisions, field="important_decisions"),
        "verified_facts": _session_list(verified_facts, field="verified_facts"),
        "notable_findings": _session_list(notable_findings, field="notable_findings"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_SESSION_PAYLOAD_BYTES:
        raise ValueError(
            f"session_save payload exceeds the {MAX_SESSION_PAYLOAD_BYTES}-byte durable handoff limit; "
            "summarize the handoff instead of storing raw logs/output."
        )
    return payload


def save_session(
    db: Session,
    project: Project,
    *,
    goal: str,
    completed_actions: list[str],
    current_state: str,
    next_steps: list[str],
    important_decisions: list[str],
    verified_facts: list[str] | None = None,
    notable_findings: list[str] | None = None,
) -> WorkSession:
    """Stage a bounded/redacted handoff and publish its disk projection only after commit."""
    payload = _bounded_session_payload(
        goal=goal,
        completed_actions=completed_actions,
        current_state=current_state,
        next_steps=next_steps,
        important_decisions=list(important_decisions or []),
        verified_facts=list(verified_facts or []),
        notable_findings=list(notable_findings or []),
    )
    session = WorkSession(
        id=uuid4(),
        project_id=project.id,
        goal=payload["goal"],
        completed_actions=payload["completed_actions"],
        current_state=payload["current_state"],
        next_steps=payload["next_steps"],
        important_decisions=payload["important_decisions"],
        verified_facts=payload["verified_facts"],
        notable_findings=payload["notable_findings"],
        created_at=datetime.now(UTC),
    )
    db.add(session)
    db.flush()
    _queue_snapshot_after_commit(db, project, session_to_dict(session))

    # Decision indexing is useful but must never make session persistence fail. Embedding providers
    # can be unavailable/offline independently of PostgreSQL and the handoff still has to survive.
    normalized_decisions = payload["important_decisions"]
    if normalized_decisions:
        try:
            vectors = get_embedder().embed(normalized_decisions)
        except Exception:
            vectors = []
        for raw, vector in zip(normalized_decisions, vectors, strict=False):
            existing = db.scalar(
                select(Decision)
                .where(Decision.project_id == project.id, Decision.decision == raw)
                .limit(1)
            )
            if existing is None:
                db.add(
                    Decision(
                        project_id=project.id,
                        title=raw[:120] or "Decision",
                        context=payload["goal"],
                        decision=raw,
                        rationale="Captured from session memory.",
                        embedding=vector,
                    )
                )
    return session


def list_sessions(db: Session, project: Project, limit: int = 20) -> list[dict]:
    wanted = max(1, min(int(limit), SNAPSHOT_RETENTION))
    db_items = db.scalars(
        select(WorkSession)
        .where(WorkSession.project_id == project.id)
        .order_by(WorkSession.created_at.desc())
        .limit(wanted)
    ).all()
    merged: dict[str, dict] = {str(item.id): session_to_dict(item) for item in db_items}
    for item in _disk_sessions(project, limit=wanted):
        merged.setdefault(str(item["id"]), item)
    return sorted(merged.values(), key=_created_at_key, reverse=True)[:wanted]


def restore_session(db: Session, project: Project, session_id: str | None = None) -> dict | None:
    wanted = session_id or "latest"
    stmt = select(WorkSession).where(WorkSession.project_id == project.id)
    if wanted != "latest":
        try:
            stmt = stmt.where(WorkSession.id == UUID(wanted))
        except ValueError:
            return None
        item = db.scalar(stmt)
        if item is not None:
            return session_to_dict(item)
        return _read_snapshot(_snapshot_dir(project) / f"{wanted}.json")

    # PostgreSQL is the canonical transactional source. Disk is a committed recovery projection
    # used only when no DB handoff exists; it can never outrank a committed database row.
    db_item = db.scalar(stmt.order_by(WorkSession.created_at.desc()).limit(1))
    if db_item is not None:
        return session_to_dict(db_item)

    disk_payload = _read_snapshot(_snapshot_dir(project) / "latest.json")
    if disk_payload is not None:
        return disk_payload
    snapshots = _disk_sessions(project, limit=1)
    return snapshots[0] if snapshots else None


def snapshot_decisions(project: Project, limit: int = 100) -> list[dict]:
    """Return explicit decisions present in committed, bounded recovery snapshots."""
    result: list[dict] = []
    for session in _disk_sessions(project, limit=SNAPSHOT_RETENTION):
        for decision in session.get("important_decisions") or []:
            text = str(decision).strip()
            if text:
                result.append(
                    {
                        "decision": text,
                        "session_id": str(session.get("id")),
                        "context": str(session.get("goal", "")),
                        "created_at": str(session.get("created_at", "")),
                    }
                )
            if len(result) >= limit:
                return result
    return result


def session_to_dict(item: WorkSession | dict) -> dict:
    if isinstance(item, dict):
        return {
            "id": str(item.get("id")),
            "goal": item.get("goal", ""),
            "completed_actions": list(item.get("completed_actions") or []),
            "current_state": item.get("current_state", ""),
            "next_steps": list(item.get("next_steps") or []),
            "important_decisions": list(item.get("important_decisions") or []),
            "verified_facts": list(item.get("verified_facts") or []),
            "notable_findings": list(item.get("notable_findings") or []),
            "created_at": str(item.get("created_at", "")),
            "storage": item.get("storage", "snapshot"),
            "snapshot_schema": item.get("snapshot_schema"),
            "commit_state": item.get("commit_state"),
        }
    return {
        "id": str(item.id),
        "goal": item.goal,
        "completed_actions": item.completed_actions,
        "current_state": item.current_state,
        "next_steps": item.next_steps,
        "important_decisions": item.important_decisions,
        "verified_facts": item.verified_facts,
        "notable_findings": item.notable_findings,
        "created_at": item.created_at.isoformat(),
        "storage": "database",
    }
