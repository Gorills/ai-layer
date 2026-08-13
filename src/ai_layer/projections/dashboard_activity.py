from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.session import session_scope
from ai_layer.db.work_models import WORK_ASSURANCE, AgentRun, RuntimeEventContext, WorkItem
from ai_layer.observability.work_events import safe_event_payload
from ai_layer.projections.dashboard_activity_cursor import (
    activity_filter_fingerprint,
    decode_activity_cursor,
    encode_activity_cursor,
    public_activity_filters,
    utc_timestamp,
)
from ai_layer.projections.dashboard_common import project_key, project_options, selected_entries

ACTIVITY_LIMIT_MAX = 100
ACTIVITY_MODES = frozenset({"milestones", "all"})
ACTIVITY_IMPORTANCE = frozenset({"low", "normal", "high"})
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
        "WorkCheckpointed",
        "WorkCompleted",
        "WorkFailed",
        "WorkInterrupted",
        "WorkStarted",
    }
)


def _text(
    value: str | None,
    *,
    field: str,
    max_length: int,
    allowed: frozenset[str] | tuple[str, ...] | None = None,
    casefold: bool = False,
) -> str | None:
    rendered = str(value or "").strip()
    if not rendered:
        return None
    if len(rendered) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    normalized = rendered.casefold() if casefold else rendered
    if allowed is not None and normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{field} must be one of: {choices}")
    return normalized


def _filters(
    *,
    project_key_value: str | None,
    mode: str,
    occurred_after: datetime | None,
    occurred_before: datetime | None,
    work_id: UUID | None,
    task_id: UUID | None,
    epic_id: UUID | None,
    actor_id: str | None,
    event_type: str | None,
    status: str | None,
    importance: str | None,
    assurance: str | None,
) -> dict[str, Any]:
    normalized_after = utc_timestamp(occurred_after) if occurred_after is not None else None
    normalized_before = utc_timestamp(occurred_before) if occurred_before is not None else None
    if normalized_after and normalized_before and normalized_after >= normalized_before:
        raise ValueError("occurred_after must be earlier than occurred_before")
    return {
        "project_key": project_key_value,
        "mode": _text(mode, field="mode", max_length=16, allowed=ACTIVITY_MODES, casefold=True)
        or "milestones",
        "occurred_after": normalized_after,
        "occurred_before": normalized_before,
        "work_id": work_id,
        "task_id": task_id,
        "epic_id": epic_id,
        "actor_id": _text(actor_id, field="actor_id", max_length=128),
        "event_type": _text(event_type, field="event_type", max_length=96),
        "status": _text(status, field="status", max_length=32, casefold=True),
        "importance": _text(
            importance,
            field="importance",
            max_length=16,
            allowed=ACTIVITY_IMPORTANCE,
            casefold=True,
        ),
        "assurance": _text(
            assurance,
            field="assurance",
            max_length=32,
            allowed=WORK_ASSURANCE,
            casefold=True,
        ),
    }


def _project_scope(
    db: Session, project_key_value: str | None
) -> tuple[list[UUID], dict[UUID, tuple[str, str]]] | None:
    entries = selected_entries(project_key_value)
    if project_key_value and not entries:
        return None
    by_root = {str(Path(str(item["root"])).expanduser().resolve()): item for item in entries}
    if not by_root:
        return [], {}
    projects = db.scalars(select(Project).where(Project.root_path.in_(by_root))).all()
    metadata = {
        project.id: (
            project_key(by_root[project.root_path]),
            str(by_root[project.root_path].get("name") or Path(project.root_path).name),
        )
        for project in projects
    }
    return list(metadata), metadata


def _conditions(
    filters: dict[str, Any], project_ids: list[UUID], assurance_value: ColumnElement[str]
) -> list[ColumnElement[bool]]:
    result: list[ColumnElement[bool]] = [RuntimeEvent.project_id.in_(project_ids)]
    if filters["mode"] == "milestones":
        result.append(
            or_(
                RuntimeEventContext.importance == "high",
                RuntimeEvent.event_type.in_(MILESTONE_EVENT_TYPES),
            )
        )
    if filters["occurred_after"] is not None:
        result.append(RuntimeEvent.created_at >= filters["occurred_after"])
    if filters["occurred_before"] is not None:
        result.append(RuntimeEvent.created_at < filters["occurred_before"])
    for field in ("work_id", "task_id", "epic_id"):
        if filters[field] is not None:
            result.append(getattr(RuntimeEventContext, field) == filters[field])
    if filters["actor_id"] is not None:
        result.append(RuntimeEvent.actor_id == filters["actor_id"])
    if filters["event_type"] is not None:
        result.append(RuntimeEvent.event_type == filters["event_type"])
    if filters["status"] is not None:
        result.append(RuntimeEvent.payload["status"].as_string() == filters["status"])
    if filters["importance"] is not None:
        result.append(RuntimeEventContext.importance == filters["importance"])
    if filters["assurance"] is not None:
        result.append(assurance_value == filters["assurance"])
    return result


def activity_payload(
    *,
    project_key_value: str | None = None,
    mode: str = "milestones",
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    work_id: UUID | None = None,
    task_id: UUID | None = None,
    epic_id: UUID | None = None,
    actor_id: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    importance: str | None = None,
    assurance: str | None = None,
    cursor: str | None = None,
    limit: int = 25,
) -> dict | None:
    normalized = _filters(
        project_key_value=project_key_value,
        mode=mode,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        work_id=work_id,
        task_id=task_id,
        epic_id=epic_id,
        actor_id=actor_id,
        event_type=event_type,
        status=status,
        importance=importance,
        assurance=assurance,
    )
    fingerprint = activity_filter_fingerprint(normalized)
    cursor_position = decode_activity_cursor(cursor, fingerprint) if cursor else None
    bounded_limit = max(1, min(int(limit or 25), ACTIVITY_LIMIT_MAX))

    with session_scope() as db:
        scope = _project_scope(db, project_key_value)
        if scope is None:
            return None
        project_ids, metadata = scope
        assurance_value = func.coalesce(
            AgentRun.assurance,
            WorkItem.assurance,
            literal("ai_layer_observed"),
        )
        conditions = _conditions(normalized, project_ids, assurance_value)
        if cursor_position is not None:
            occurred_at, event_id = cursor_position
            conditions.append(
                or_(
                    RuntimeEvent.created_at < occurred_at,
                    and_(RuntimeEvent.created_at == occurred_at, RuntimeEvent.id < event_id),
                )
            )
        statement = (
            select(RuntimeEvent, RuntimeEventContext, assurance_value.label("assurance"))
            .outerjoin(RuntimeEventContext, RuntimeEventContext.event_id == RuntimeEvent.id)
            .outerjoin(AgentRun, AgentRun.id == RuntimeEventContext.run_id)
            .outerjoin(WorkItem, WorkItem.id == RuntimeEventContext.work_id)
            .where(*conditions)
            .order_by(RuntimeEvent.created_at.desc(), RuntimeEvent.id.desc())
            .limit(bounded_limit + 1)
        )
        rows = list(db.execute(statement).all()) if project_ids else []

    has_more = len(rows) > bounded_limit
    visible = rows[:bounded_limit]
    items = []
    for event, context, event_assurance in visible:
        safe = safe_event_payload(event, context)
        key, name = metadata.get(event.project_id, ("", "unknown"))
        details = safe.get("payload") or {}
        items.append(
            {
                **safe,
                "project_key": key,
                "project_name": name,
                "assurance": str(event_assurance or "ai_layer_observed"),
                "operation": details.get("tool") or safe.get("event_type") or "unknown",
                "status": details.get("status") or "observed",
                "duration_ms": details.get("duration_ms"),
                "error_type": details.get("error_type"),
            }
        )
    return {
        "contract_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "items": items,
        "next_cursor": encode_activity_cursor(visible[-1][0], fingerprint) if has_more else None,
        "has_more": has_more,
        "limit": bounded_limit,
        "projects": project_options(),
        "filters": public_activity_filters(normalized),
        "ordering": ["occurred_at:desc", "event_id:desc"],
        "retention": "durable RuntimeEvent journal; JSONL telemetry is diagnostic only",
    }
