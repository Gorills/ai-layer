from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, utcnow
from ai_layer.db.work_models import AgentRun, WorkItem
from ai_layer.work.evidence import safe_metadata_text
from ai_layer.work.service import (
    WORK_ACTION_MAX_CHARS,
    WORK_SUMMARY_MAX_CHARS,
    resolve_work_key,
)


def effective_work_status(work: WorkItem, runs: Iterable[AgentRun]) -> str:
    """Return the user-facing Work state without changing the persisted compatibility status."""
    if work.status == "active" and not any(run.status == "active" for run in runs):
        return "awaiting_feedback"
    return work.status


def _locked_work(db: Session, project: Project, work_key_value: str | None) -> WorkItem:
    resolved = resolve_work_key(db, project, work_key_value)
    sequence = int(resolved.removeprefix("W-"))
    work = db.scalar(
        select(WorkItem)
        .where(WorkItem.project_id == project.id, WorkItem.sequence == sequence)
        .with_for_update()
    )
    if work is None:
        raise ValueError(f"work item {resolved} does not exist in this project")
    return work


def wait_work(
    db: Session,
    project: Project,
    *,
    work_key_value: str | None,
    summary: str = "",
) -> tuple[WorkItem, list[AgentRun]]:
    """End the current execution episode while keeping the durable WorkItem open."""
    work = _locked_work(db, project, work_key_value)
    if work.status != "active":
        raise RuntimeError(
            f"work item W-{work.sequence:04d} cannot await feedback from {work.status}"
        )

    now = utcnow()
    if summary:
        work.result_summary = safe_metadata_text(
            summary,
            field="summary",
            max_chars=WORK_SUMMARY_MAX_CHARS,
        )
    work.updated_at = now
    work.last_milestone_at = now

    runs = list(
        db.scalars(
            select(AgentRun).where(AgentRun.work_id == work.id, AgentRun.status == "active")
        ).all()
    )
    for run in runs:
        run.status = "completed"
        run.heartbeat_at = now
        run.ended_at = now
        if work.result_summary:
            run.last_meaningful_action = work.result_summary[:WORK_ACTION_MAX_CHARS]
    db.flush()
    return work, runs


def resume_work(
    db: Session,
    project: Project,
    *,
    work_key_value: str | None,
    host: str = "unknown",
    client: str = "unknown",
    session_id: str = "",
    turn_id: str = "",
    model: str = "",
) -> tuple[WorkItem, AgentRun]:
    """Start a new root execution episode on an open WorkItem awaiting user feedback."""
    work = _locked_work(db, project, work_key_value)
    if work.status != "active":
        raise RuntimeError(f"work item W-{work.sequence:04d} cannot resume from {work.status}")

    existing = db.scalar(
        select(AgentRun)
        .where(AgentRun.work_id == work.id, AgentRun.status == "active")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    if existing is not None:
        raise RuntimeError(
            f"work item W-{work.sequence:04d} already has an active AgentRun; do not duplicate execution"
        )

    now = utcnow()
    run = AgentRun(
        work_id=work.id,
        role="root",
        status="active",
        host=safe_metadata_text(host, field="host", max_chars=64) or "unknown",
        client=safe_metadata_text(client, field="client", max_chars=64) or "unknown",
        session_id=safe_metadata_text(session_id, field="session_id", max_chars=128),
        turn_id=safe_metadata_text(turn_id, field="turn_id", max_chars=128),
        model=safe_metadata_text(model, field="model", max_chars=128),
        observability_coverage=work.observability_coverage,
        assurance=work.assurance,
        started_at=now,
        heartbeat_at=now,
    )
    work.updated_at = now
    db.add(run)
    db.flush()
    return work, run
