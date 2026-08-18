from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai_layer.core.redaction import redact_secrets
from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.work_models import AgentRun, RuntimeEventContext, WorkItem
from ai_layer.observability.domain_events import EVENT_TYPES, append_event

SAFE_EVENT_FIELDS = frozenset(
    {
        "status",
        "summary",
        "reason",
        "goal",
        "kind",
        "tool",
        "command_name",
        "duration_ms",
        "error_type",
        "updated",
        "removed",
        "scope_paths",
        "map_status",
    }
)
SAFE_EVENT_TEXT_LIMITS = {
    "status": 32,
    "summary": 4_000,
    "reason": 1_000,
    "goal": 2_000,
    "kind": 32,
    "tool": 128,
    "command_name": 128,
    "error_type": 128,
    "map_status": 32,
}
MILESTONE_EVENT_TYPES = frozenset(
    {
        "ApprovalRequested",
        "ApprovalResolved",
        "FindingOpened",
        "FindingVerified",
        "KnowledgePublished",
        "ProjectMapReconciled",
        "StageCompleted",
        "TaskBlocked",
        "TaskCompleted",
        "TaskCreated",
        "TaskResumed",
        "VerificationCompleted",
        "WorkAbandoned",
        "WorkAwaitingFeedback",
        "WorkCheckpointed",
        "WorkCompleted",
        "WorkFailed",
        "WorkInterrupted",
        "WorkResumed",
        "WorkStarted",
    }
) | frozenset(name for name in EVENT_TYPES if name.startswith("Epic"))


def _safe_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, max_chars in SAFE_EVENT_TEXT_LIMITS.items():
        value = raw.get(key)
        if value is None or not isinstance(value, (str, int, float, bool)):
            continue
        payload[key] = redact_secrets(str(value)[:max_chars])
    duration = raw.get("duration_ms")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        payload["duration_ms"] = max(0, duration)
    for key in ("updated", "removed"):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            payload[key] = value
    scope_paths = raw.get("scope_paths")
    if isinstance(scope_paths, list):
        payload["scope_paths"] = [
            redact_secrets(item[:512])
            for item in scope_paths[:120]
            if isinstance(item, str) and item
        ]
    return payload


def _linked_work_id(db: Session, *, task_id=None, epic_id=None):
    clauses = []
    if task_id is not None:
        clauses.append(WorkItem.linked_task_id == task_id)
    if epic_id is not None:
        clauses.append(WorkItem.linked_epic_id == epic_id)
    if not clauses:
        return None
    return db.scalar(
        select(WorkItem.id)
        .where(or_(*clauses))
        .order_by(WorkItem.updated_at.desc(), WorkItem.id.desc())
        .limit(1)
    )


def _milestone_importance(event_type: str, importance: str | None) -> str:
    if importance:
        return str(importance)[:16]
    return "high" if event_type in MILESTONE_EVENT_TYPES else "normal"


def append_contextual_event(
    db: Session,
    *,
    event_type: str,
    project: Project | None,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any] | None = None,
    work: WorkItem | None = None,
    run: AgentRun | None = None,
    work_id=None,
    run_id=None,
    task_id=None,
    epic_id=None,
    project_id=None,
    host: str = "",
    client: str = "",
    session_id: str = "",
    turn_id: str = "",
    model: str = "",
    retention_class: str = "durable",
    importance: str = "normal",
) -> RuntimeEvent:
    row = append_event(
        db,
        event_type=event_type,
        project=project,
        project_id=project_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    db.flush()
    resolved_work_id = work.id if work is not None else work_id
    if resolved_work_id is None:
        resolved_work_id = _linked_work_id(db, task_id=task_id, epic_id=epic_id)
    db.add(
        RuntimeEventContext(
            event_id=row.id,
            work_id=resolved_work_id,
            run_id=run.id if run is not None else run_id,
            task_id=task_id,
            epic_id=epic_id,
            host=str(host or "")[:64],
            client=str(client or "")[:64],
            session_id=str(session_id or "")[:128],
            turn_id=str(turn_id or "")[:128],
            model=str(model or "")[:128],
            retention_class=str(retention_class or "durable")[:32],
            importance=str(importance or "normal")[:16],
        )
    )
    return row


def append_task_event(
    db: Session,
    *,
    event_type: str,
    task,
    project: Project | None = None,
    payload: dict[str, Any] | None = None,
    aggregate_type: str = "task",
    aggregate_id: str | None = None,
    project_id=None,
    importance: str | None = None,
) -> RuntimeEvent:
    resolved_task_id = task.id
    return append_contextual_event(
        db,
        event_type=event_type,
        project=project,
        project_id=project_id if project_id is not None else task.project_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id or str(resolved_task_id),
        payload=payload,
        task_id=resolved_task_id,
        importance=_milestone_importance(event_type, importance),
    )


def safe_event_payload(
    event: RuntimeEvent,
    context: RuntimeEventContext | None = None,
) -> dict[str, Any]:
    raw = dict(event.payload or {})
    payload = _safe_payload({key: raw[key] for key in SAFE_EVENT_FIELDS if key in raw})
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "project_id": str(event.project_id) if event.project_id else None,
        "work_id": str(context.work_id) if context and context.work_id else None,
        "run_id": str(context.run_id) if context and context.run_id else None,
        "task_id": str(context.task_id) if context and context.task_id else None,
        "epic_id": str(context.epic_id) if context and context.epic_id else None,
        "correlation_id": event.correlation_id,
        "causation_id": event.causation_id,
        "actor_id": redact_secrets(event.actor_id),
        "actor_kind": redact_secrets(event.actor_kind),
        "interface": redact_secrets(event.interface),
        "host": redact_secrets(context.host) if context else "",
        "client": redact_secrets(context.client) if context else "",
        "session_id": redact_secrets(context.session_id) if context else "",
        "turn_id": redact_secrets(context.turn_id) if context else "",
        "model": redact_secrets(context.model) if context else "",
        "retention_class": context.retention_class if context else "durable",
        "importance": context.importance if context else "normal",
        "payload": payload,
        "occurred_at": event.created_at.isoformat(),
    }
