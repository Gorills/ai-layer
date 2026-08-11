from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from ai_layer.core.service import get_project
from ai_layer.db.models import ApprovalRequest, utcnow
from ai_layer.db.session import session_scope
from ai_layer.domain.security import Actor, Capability, DANGEROUS_CAPABILITIES, PolicyDecision
from ai_layer.observability.domain_events import append_event


def decide(
    actor: Actor, capability: Capability | str, *, require_approval: bool = False
) -> PolicyDecision:
    wanted = str(capability)
    if not actor.authenticated:
        return PolicyDecision(False, wanted, "actor is not authenticated")
    if not actor.has(wanted):
        return PolicyDecision(False, wanted, "actor lacks required capability")
    dangerous = wanted in {str(item) for item in DANGEROUS_CAPABILITIES}
    if require_approval and dangerous:
        return PolicyDecision(
            False,
            wanted,
            "operation requires an explicit approval decision",
            approval_required=True,
        )
    return PolicyDecision(True, wanted, "capability granted")


def request_approval(
    project_root: str | Path,
    *,
    actor: Actor,
    required_capability: Capability | str,
    action: str,
    context: dict | None = None,
) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        row = ApprovalRequest(
            project_id=project.id,
            requested_by=actor.actor_id,
            requested_by_kind=actor.kind,
            required_capability=str(required_capability),
            action=str(action)[:128],
            context=dict(context or {}),
        )
        db.add(row)
        db.flush()
        append_event(
            db,
            event_type="ApprovalRequested",
            project=project,
            aggregate_type="approval",
            aggregate_id=str(row.id),
            actor_id=actor.actor_id,
            actor_kind=actor.kind,
            payload={
                "required_capability": row.required_capability,
                "action": row.action,
            },
        )
        return _approval_payload(row)


def resolve_approval(
    approval_id: str,
    *,
    actor: Actor,
    decision: str,
) -> dict:
    normalized = str(decision).strip().lower()
    if normalized not in {"approved", "denied"}:
        raise ValueError("approval decision must be approved|denied")
    with session_scope() as db:
        row = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == UUID(str(approval_id)))
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("Approval request does not exist.")
        if row.status == "resolved":
            return _approval_payload(row)
        if not decide(actor, Capability.TASK_APPROVE).allowed:
            raise PermissionError("Actor lacks task.approve capability.")
        row.status = "resolved"
        row.resolved_at = utcnow()
        row.resolved_by = actor.actor_id
        row.decision = normalized
        db.flush()
        append_event(
            db,
            event_type="ApprovalResolved",
            project_id=row.project_id,
            aggregate_type="approval",
            aggregate_id=str(row.id),
            actor_id=actor.actor_id,
            actor_kind=actor.kind,
            payload={"decision": normalized, "required_capability": row.required_capability},
        )
        return _approval_payload(row)


def _approval_payload(row: ApprovalRequest) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id) if row.project_id else None,
        "status": row.status,
        "requested_by": row.requested_by,
        "requested_by_kind": row.requested_by_kind,
        "required_capability": row.required_capability,
        "action": row.action,
        "context": dict(row.context or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolved_by": row.resolved_by or None,
        "decision": row.decision or None,
    }
