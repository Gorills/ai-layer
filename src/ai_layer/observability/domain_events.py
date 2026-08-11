from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.core.request_context import current_operation
from ai_layer.db.models import EventConsumerCheckpoint, Project, RuntimeEvent, utcnow

EVENT_SCHEMA_VERSION = 1
EVENT_TYPES = frozenset(
    {
        "ProjectRegistered",
        "TaskCreated",
        "TaskAdopted",
        "TaskClassified",
        "StageDelegated",
        "StageCompleted",
        "StageInvalidated",
        "VerificationStarted",
        "VerificationCompleted",
        "FindingOpened",
        "FindingVerified",
        "TaskBlocked",
        "TaskResumed",
        "TaskCompleted",
        "SkillPlanCreated",  # legacy schema only: retained so historical events stay readable
        "SkillLoaded",
        "AgentAssigned",
        "AgentFailed",
        "AgentHeartbeat",
        "AgentLeaseExpired",
        "ApprovalRequested",
        "ApprovalResolved",
        "CommandExecuted",
        "KnowledgeDraftUpdated",
        "KnowledgeReviewInspected",
        "KnowledgePublished",
        "EpicCreated",
        "EpicSpecRevised",
        "EpicAudited",
        "EpicApproved",
        "EpicPhase0Started",
        "EpicReconciled",
        "EpicPlanCreated",
        "EpicPlanItemStarted",
        "EpicPlanItemCompleted",
        "EpicDriftDetected",
        "EpicDriftReconciliationStarted",
        "EpicFinalReviewRetryRequired",
        "EpicCompleted",
        "EpicArchived",
    }
)


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    event_type: str
    project_id: str | None
    aggregate_type: str
    aggregate_id: str
    correlation_id: str
    causation_id: str | None
    actor_id: str
    actor_kind: str
    interface: str
    command_id: str | None
    schema_version: int
    payload: dict[str, Any]
    occurred_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        timestamp = self.occurred_at.isoformat()
        data["occurred_at"] = timestamp
        data["created_at"] = timestamp  # compatibility alias for older consumers
        return data


def append_event(
    db: Session,
    *,
    event_type: str,
    project: Project | None = None,
    project_id=None,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    actor_id: str | None = None,
    actor_kind: str | None = None,
    interface: str | None = None,
    command_id: str | None = None,
    schema_version: int = EVENT_SCHEMA_VERSION,
) -> RuntimeEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported structured event type: {event_type}")
    context = current_operation()
    correlation = str(
        correlation_id or (context.correlation_id if context else None) or uuid4().hex
    )[:64]
    row = RuntimeEvent(
        project_id=project.id if project is not None else project_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        correlation_id=correlation,
        causation_id=(causation_id or (context.causation_id if context else None)),
        actor_id=str(actor_id or (context.actor.actor_id if context else "system:internal"))[:128],
        actor_kind=str(actor_kind or (context.actor.kind if context else "system"))[:32],
        interface=str(interface or (context.interface if context else "internal"))[:32],
        command_id=command_id or (context.command_id if context else None),
        schema_version=max(1, int(schema_version)),
        payload=dict(payload or {}),
    )
    db.add(row)
    return row


def _record(row: RuntimeEvent) -> EventRecord:
    return EventRecord(
        event_id=str(row.id),
        event_type=row.event_type,
        project_id=str(row.project_id) if row.project_id else None,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        actor_id=row.actor_id,
        actor_kind=row.actor_kind,
        interface=row.interface,
        command_id=row.command_id,
        schema_version=int(row.schema_version or 1),
        payload=dict(row.payload or {}),
        occurred_at=row.created_at,
    )


def read_structured_events(
    db: Session,
    *,
    project: Project | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = select(RuntimeEvent)
    if project is not None:
        stmt = stmt.where(RuntimeEvent.project_id == project.id)
    rows = db.scalars(
        stmt.order_by(RuntimeEvent.created_at.desc(), RuntimeEvent.id.desc()).limit(
            max(1, min(limit, 1000))
        )
    ).all()
    return [_record(row).to_dict() for row in rows]


def consumer_checkpoint(db: Session, consumer_name: str) -> str | None:
    row = db.get(EventConsumerCheckpoint, str(consumer_name))
    return str(row.last_event_id) if row and row.last_event_id else None


def advance_consumer_checkpoint(
    db: Session,
    *,
    consumer_name: str,
    event: RuntimeEvent,
) -> EventConsumerCheckpoint:
    name = str(consumer_name).strip()
    if not name or len(name) > 128:
        raise ValueError("consumer_name must contain 1..128 characters")
    row = db.get(EventConsumerCheckpoint, name)
    if row is None:
        row = EventConsumerCheckpoint(consumer_name=name)
        db.add(row)
    row.last_event_id = event.id
    row.updated_at = utcnow()
    db.flush()
    return row
