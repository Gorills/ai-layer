from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai_layer.db.models import CommandReceipt, utcnow
from ai_layer.domain.security import Actor
from ai_layer.observability.domain_events import append_event

T = TypeVar("T", bound=dict[str, Any])


def _request_hash(command_name: str, request: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"command": command_name, "request": request},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _advisory_command_lock(db: Session, command_id: str) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(command_id.encode("utf-8")).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def execute_idempotent(
    db: Session,
    *,
    command_id: str,
    command_name: str,
    request: dict[str, Any],
    actor: Actor,
    correlation_id: str,
    project_id=None,
    handler: Callable[[], T],
) -> T:
    """Execute one mutation under a durable idempotency receipt in the caller transaction.

    The caller owns commit/rollback. Therefore the mutation and completed receipt become visible
    atomically; a lost response can be retried with the same command_id without duplicating effects.
    """
    identifier = str(command_id).strip()
    if not identifier or len(identifier) > 128:
        raise ValueError("command_id must contain 1..128 characters")
    name = str(command_name).strip()
    if not name or len(name) > 128:
        raise ValueError("command_name must contain 1..128 characters")
    request_digest = _request_hash(name, request)
    _advisory_command_lock(db, identifier)
    receipt = db.scalar(
        select(CommandReceipt).where(CommandReceipt.command_id == identifier).with_for_update()
    )
    if receipt is not None:
        if receipt.command_name != name or receipt.request_hash != request_digest:
            raise RuntimeError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_COMMAND")
        if receipt.status == "completed":
            return dict(receipt.result or {})  # type: ignore[return-value]
        raise RuntimeError("IDEMPOTENT_COMMAND_INCOMPLETE: prior transaction did not complete")

    receipt = CommandReceipt(
        project_id=project_id,
        command_id=identifier,
        command_name=name,
        request_hash=request_digest,
        status="started",
        actor_id=actor.actor_id,
        correlation_id=str(correlation_id)[:64],
    )
    db.add(receipt)
    db.flush()
    result = handler()
    receipt.status = "completed"
    receipt.result = dict(result)
    receipt.completed_at = utcnow()
    append_event(
        db,
        event_type="CommandExecuted",
        project_id=project_id,
        aggregate_type="command",
        aggregate_id=identifier,
        correlation_id=correlation_id,
        actor_id=actor.actor_id,
        actor_kind=actor.kind,
        command_id=identifier,
        payload={"command_name": name, "status": "completed"},
    )
    db.flush()
    return result
