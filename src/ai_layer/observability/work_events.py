from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.work_models import AgentRun, RuntimeEventContext, WorkItem
from ai_layer.observability.domain_events import append_event

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
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    db.flush()
    db.add(
        RuntimeEventContext(
            event_id=row.id,
            work_id=work.id if work is not None else work_id,
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


def safe_event_payload(
    event: RuntimeEvent,
    context: RuntimeEventContext | None = None,
) -> dict[str, Any]:
    raw = dict(event.payload or {})
    payload = {key: raw[key] for key in SAFE_EVENT_FIELDS if key in raw}
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
        "actor_id": event.actor_id,
        "actor_kind": event.actor_kind,
        "interface": event.interface,
        "host": context.host if context else "",
        "client": context.client if context else "",
        "session_id": context.session_id if context else "",
        "turn_id": context.turn_id if context else "",
        "model": context.model if context else "",
        "retention_class": context.retention_class if context else "durable",
        "importance": context.importance if context else "normal",
        "payload": payload,
        "occurred_at": event.created_at.isoformat(),
    }
