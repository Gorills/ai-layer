from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.core.redaction import redact_secrets
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.db.work_models import (
    OBSERVABILITY_COVERAGE,
    AgentRun,
    RuntimeEventContext,
    WorkItem,
)
from ai_layer.work.evidence import (
    assurance_source,
    check_evidence,
    project_paths,
    safe_metadata_text,
)
from ai_layer.work.evidence import (
    map_disposition as normalize_map_disposition,
)
from ai_layer.work.evidence import (
    repository_delta as normalize_repository_delta,
)

WORK_RUN_STALE_SECONDS = 300
WORK_RECENT_LIMIT = 8
WORK_GOAL_MAX_CHARS = 2000
WORK_SUMMARY_MAX_CHARS = 4000
WORK_ACTION_MAX_CHARS = 1000
_TASK_KEY_RE = re.compile(r"^T-(\d{1,9})$", re.IGNORECASE)
_EPIC_KEY_RE = re.compile(r"^E-(\d{1,9})$", re.IGNORECASE)
_WORK_KEY_RE = re.compile(r"^W-(\d{1,9})$", re.IGNORECASE)


def work_key(work: WorkItem) -> str:
    return f"W-{int(work.sequence):04d}"


def _agent_runs_for_work(
    db: Session, work: WorkItem, preloaded_runs: list[AgentRun] | None = None
) -> list[AgentRun]:
    if preloaded_runs is not None:
        return list(preloaded_runs)
    return list(
        db.scalars(
            select(AgentRun)
            .where(AgentRun.work_id == work.id)
            .order_by(AgentRun.started_at, AgentRun.id)
        ).all()
    )


def _work_is_live(work: WorkItem, runs: list[AgentRun], *, now: datetime | None = None) -> bool:
    if work.status not in {"active", "blocked"}:
        return False
    return any(run.status == "active" and not _run_stale(run, now=now) for run in runs)


def _compact_work_row(work: WorkItem, *, live: bool) -> dict[str, Any]:
    disposition = dict(work.map_disposition or {}) or {"status": "pending"}
    return {
        "id": str(work.id),
        "key": work_key(work),
        "goal": redact_secrets(work.goal),
        "kind": work.kind,
        "status": work.status,
        "live": live,
        "map_disposition": {"status": disposition.get("status", "pending")},
        "map_pending": disposition.get("status") == "pending",
        "updated_at": work.updated_at.isoformat(),
    }


def _run_stale(run: AgentRun, *, now: datetime | None = None) -> bool:
    if run.status != "active":
        return False
    moment = now or datetime.now(UTC)
    heartbeat = run.heartbeat_at
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=UTC)
    return heartbeat < moment - timedelta(seconds=WORK_RUN_STALE_SECONDS)


def run_to_dict(run: AgentRun, *, now: datetime | None = None) -> dict[str, Any]:
    stale = _run_stale(run, now=now)
    return {
        "id": str(run.id),
        "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
        "role": run.role,
        "status": run.status,
        "effective_status": "stale" if stale else run.status,
        "stale": stale,
        "host": redact_secrets(run.host),
        "client": redact_secrets(run.client),
        "session_id": redact_secrets(run.session_id),
        "turn_id": redact_secrets(run.turn_id),
        "model": redact_secrets(run.model),
        "last_meaningful_action": redact_secrets(run.last_meaningful_action),
        "observability_coverage": run.observability_coverage,
        "assurance": run.assurance,
        "started_at": run.started_at.isoformat(),
        "heartbeat_at": run.heartbeat_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
    }


def work_to_dict(
    db: Session,
    work: WorkItem,
    *,
    include_runs: bool = True,
    compact: bool = False,
    preloaded_runs: list[AgentRun] | None = None,
) -> dict[str, Any]:
    rows = _agent_runs_for_work(db, work, preloaded_runs)
    live = _work_is_live(work, rows)
    if compact:
        return _compact_work_row(work, live=live)
    runs = [run_to_dict(row) for row in rows] if include_runs else []
    disposition = dict(work.map_disposition or {}) or {"status": "pending"}
    return {
        "id": str(work.id),
        "key": work_key(work),
        "goal": redact_secrets(work.goal),
        "kind": work.kind,
        "status": work.status,
        "live": live,
        "result_summary": redact_secrets(work.result_summary),
        "reviewed_paths": list(work.reviewed_paths or []),
        "changed_paths": list(work.changed_paths or []),
        "repository_delta": dict(work.repository_delta or {}),
        "checks": [
            {
                **item,
                "name": redact_secrets(str(item.get("name") or "")),
                "summary": redact_secrets(str(item.get("summary") or "")),
            }
            for item in (work.checks or [])
            if isinstance(item, dict)
        ],
        "map_disposition": {
            **disposition,
            "reason": redact_secrets(str(disposition.get("reason") or "")),
        },
        "map_pending": disposition.get("status") == "pending",
        "observability_coverage": work.observability_coverage,
        "assurance": work.assurance,
        "linked_task_id": str(work.linked_task_id) if work.linked_task_id else None,
        "linked_epic_id": str(work.linked_epic_id) if work.linked_epic_id else None,
        "legacy_session_id": str(work.legacy_session_id) if work.legacy_session_id else None,
        "started_at": work.started_at.isoformat(),
        "updated_at": work.updated_at.isoformat(),
        "last_milestone_at": work.last_milestone_at.isoformat(),
        "completed_at": work.completed_at.isoformat() if work.completed_at else None,
        "runs": runs,
    }


def _work_for_key(db: Session, project: Project, key: str, *, lock: bool = False) -> WorkItem:
    rendered = str(key or "").strip().upper()
    match = _WORK_KEY_RE.fullmatch(rendered)
    if not match:
        raise ValueError("work_key must look like W-0001")
    stmt = select(WorkItem).where(
        WorkItem.project_id == project.id,
        WorkItem.sequence == int(match.group(1)),
    )
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise ValueError(f"work item {rendered} does not exist in this project")
    return row


def _task_id(db: Session, project: Project, key: str | None):
    rendered = str(key or "").strip().upper()
    if not rendered:
        return None
    match = _TASK_KEY_RE.fullmatch(rendered)
    if not match:
        raise ValueError("linked_task_key must look like T-0001")
    task = db.scalar(
        select(Task).where(Task.project_id == project.id, Task.sequence == int(match.group(1)))
    )
    if task is None:
        raise ValueError(f"managed task {rendered} does not exist in this project")
    return task.id


def _epic_id(db: Session, project: Project, key: str | None):
    rendered = str(key or "").strip().upper()
    if not rendered:
        return None
    match = _EPIC_KEY_RE.fullmatch(rendered)
    if not match:
        raise ValueError("linked_epic_key must look like E-0001")
    from ai_layer.db.epic_models import Epic

    epic = db.scalar(
        select(Epic).where(Epic.project_id == project.id, Epic.sequence == int(match.group(1)))
    )
    if epic is None:
        raise ValueError(f"epic {rendered} does not exist in this project")
    return epic.id


def _apply_checkpoint_links(
    db: Session,
    project: Project,
    work: WorkItem,
    *,
    linked_task_key: str | None,
    linked_epic_key: str | None,
) -> None:
    task_key = str(linked_task_key or "").strip() or None
    epic_key = str(linked_epic_key or "").strip() or None
    task_id = _task_id(db, project, task_key)
    epic_id = _epic_id(db, project, epic_key)
    if task_key:
        work.linked_task_id = task_id
    if epic_key:
        work.linked_epic_id = epic_id


def begin_work(
    db: Session,
    project: Project,
    *,
    goal: str,
    kind: str = "change",
    host: str = "unknown",
    client: str = "unknown",
    session_id: str = "",
    turn_id: str = "",
    model: str = "",
    linked_task_key: str | None = None,
    linked_epic_key: str | None = None,
    observability_coverage: str = "lifecycle_only",
    assurance: str = "agent_reported",
) -> tuple[WorkItem, AgentRun]:
    normalized_kind = str(kind or "change").strip().casefold()
    if normalized_kind not in {"change", "diagnose", "review", "research", "planning", "ops"}:
        raise ValueError("kind must be change, diagnose, review, research, planning or ops")
    normalized_coverage = str(observability_coverage or "lifecycle_only").strip()
    if normalized_coverage not in OBSERVABILITY_COVERAGE:
        raise ValueError("unsupported observability_coverage")
    # Work sequences are human-facing project-local identifiers. Lock the durable project row so
    # different idempotency keys cannot concurrently observe the same MAX(sequence).
    locked_project = db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    if locked_project is None:
        raise ValueError("project no longer exists")
    sequence = (
        int(
            db.scalar(
                select(func.coalesce(func.max(WorkItem.sequence), 0)).where(
                    WorkItem.project_id == project.id
                )
            )
            or 0
        )
        + 1
    )
    now = utcnow()
    work = WorkItem(
        project_id=project.id,
        sequence=sequence,
        goal=safe_metadata_text(goal, field="goal", max_chars=WORK_GOAL_MAX_CHARS, required=True),
        kind=normalized_kind,
        status="active",
        map_disposition={"status": "pending"},
        observability_coverage=normalized_coverage,
        assurance=assurance_source(assurance or "agent_reported"),
        linked_task_id=_task_id(db, project, linked_task_key),
        linked_epic_id=_epic_id(db, project, linked_epic_key),
        started_at=now,
        updated_at=now,
        last_milestone_at=now,
    )
    db.add(work)
    db.flush()
    run = AgentRun(
        work_id=work.id,
        role="root",
        status="active",
        host=safe_metadata_text(host, field="host", max_chars=64) or "unknown",
        client=safe_metadata_text(client, field="client", max_chars=64) or "unknown",
        session_id=safe_metadata_text(session_id, field="session_id", max_chars=128),
        turn_id=safe_metadata_text(turn_id, field="turn_id", max_chars=128),
        model=safe_metadata_text(model, field="model", max_chars=128),
        observability_coverage=normalized_coverage,
        assurance=work.assurance,
        started_at=now,
        heartbeat_at=now,
    )
    db.add(run)
    db.flush()
    return work, run


def checkpoint_work(
    db: Session,
    project: Project,
    *,
    work_key_value: str,
    summary: str = "",
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    blocked: bool | None = None,
    linked_task_key: str | None = None,
    linked_epic_key: str | None = None,
) -> tuple[WorkItem, AgentRun | None]:
    work = _work_for_key(db, project, work_key_value, lock=True)
    if work.status not in {"active", "blocked"}:
        raise RuntimeError(f"work item {work_key(work)} is terminal: {work.status}")
    now = utcnow()
    if summary:
        work.result_summary = safe_metadata_text(
            summary, field="summary", max_chars=WORK_SUMMARY_MAX_CHARS
        )
    if reviewed_paths is not None:
        work.reviewed_paths = project_paths(reviewed_paths, field="reviewed_paths")
    if changed_paths is not None:
        work.changed_paths = project_paths(changed_paths, field="changed_paths")
    if checks is not None:
        work.checks = check_evidence(checks)
    if repository_delta is not None:
        work.repository_delta = normalize_repository_delta(repository_delta)
    if blocked is not None:
        work.status = "blocked" if blocked else "active"
    _apply_checkpoint_links(
        db,
        project,
        work,
        linked_task_key=linked_task_key,
        linked_epic_key=linked_epic_key,
    )
    work.updated_at = now
    work.last_milestone_at = now
    run = db.scalar(
        select(AgentRun)
        .where(AgentRun.work_id == work.id, AgentRun.role == "root", AgentRun.status == "active")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    if run is not None:
        run.heartbeat_at = now
        if summary:
            run.last_meaningful_action = safe_metadata_text(
                summary, field="summary", max_chars=WORK_ACTION_MAX_CHARS
            )
    db.flush()
    return work, run


def _terminal_deferred_map_disposition(
    work: WorkItem,
    *,
    reviewed_paths: list[str] | None,
    changed_paths: list[str] | None,
) -> dict:
    reviewed = reviewed_paths if reviewed_paths is not None else list(work.reviewed_paths or [])
    changed = changed_paths if changed_paths is not None else list(work.changed_paths or [])
    scope = list(dict.fromkeys([*reviewed, *changed]))
    return {
        "status": "deferred",
        "scope": scope,
        "reason": (
            "No Project Map reconciliation was recorded before Work termination; "
            "reconcile later if this work established reusable navigation facts."
        ),
        "event_id": None,
    }


def finish_work(
    db: Session,
    project: Project,
    *,
    work_key_value: str,
    status: str,
    summary: str,
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    map_disposition: dict | None = None,
) -> tuple[WorkItem, list[AgentRun]]:
    terminal = str(status).strip().casefold()
    if terminal not in {"completed", "failed", "interrupted", "abandoned"}:
        raise ValueError("terminal work status must be completed, failed, interrupted or abandoned")
    work = _work_for_key(db, project, work_key_value, lock=True)
    if work.status not in {"active", "blocked"}:
        if work.status == terminal:
            return work, []
        raise RuntimeError(f"work item {work_key(work)} is already terminal: {work.status}")
    normalized_summary = safe_metadata_text(
        summary, field="summary", max_chars=WORK_SUMMARY_MAX_CHARS, required=True
    )
    normalized_reviewed_paths = (
        project_paths(reviewed_paths, field="reviewed_paths")
        if reviewed_paths is not None
        else None
    )
    normalized_changed_paths = (
        project_paths(changed_paths, field="changed_paths") if changed_paths is not None else None
    )
    normalized_checks = check_evidence(checks) if checks is not None else None
    normalized_repository_delta = (
        normalize_repository_delta(repository_delta) if repository_delta is not None else None
    )
    if map_disposition is not None:
        disposition = normalize_map_disposition(map_disposition)
        if disposition["status"] == "reconciled":
            event_id = UUID(str(disposition["event_id"]))
            event = db.scalar(
                select(RuntimeEvent)
                .join(RuntimeEventContext, RuntimeEventContext.event_id == RuntimeEvent.id)
                .where(
                    RuntimeEvent.id == event_id,
                    RuntimeEvent.project_id == project.id,
                    RuntimeEvent.event_type == "ProjectMapReconciled",
                    RuntimeEventContext.work_id == work.id,
                )
            )
            if event is None:
                raise ValueError(
                    "reconciled map_disposition.event_id must identify a ProjectMapReconciled "
                    "event for this Work item"
                )
            if list((event.payload or {}).get("scope_paths") or []) != disposition["scope"]:
                raise ValueError(
                    "reconciled map_disposition.scope must match the ProjectMapReconciled event scope"
                )
        if disposition["status"] == "pending":
            disposition = _terminal_deferred_map_disposition(
                work,
                reviewed_paths=normalized_reviewed_paths,
                changed_paths=normalized_changed_paths,
            )
        work.map_disposition = disposition
    elif (work.map_disposition or {}).get("status", "pending") == "pending":
        work.map_disposition = _terminal_deferred_map_disposition(
            work,
            reviewed_paths=normalized_reviewed_paths,
            changed_paths=normalized_changed_paths,
        )
    now = utcnow()
    work.status = terminal
    work.result_summary = normalized_summary
    if normalized_reviewed_paths is not None:
        work.reviewed_paths = normalized_reviewed_paths
    if normalized_changed_paths is not None:
        work.changed_paths = normalized_changed_paths
    if normalized_checks is not None:
        work.checks = normalized_checks
    if normalized_repository_delta is not None:
        work.repository_delta = normalized_repository_delta
    work.updated_at = now
    work.last_milestone_at = now
    work.completed_at = now
    runs = list(
        db.scalars(
            select(AgentRun).where(AgentRun.work_id == work.id, AgentRun.status == "active")
        ).all()
    )
    run_status = "completed" if terminal == "completed" else terminal
    for run in runs:
        run.status = run_status
        run.heartbeat_at = now
        run.ended_at = now
        run.last_meaningful_action = work.result_summary[:WORK_ACTION_MAX_CHARS]
    db.flush()
    return work, runs


def list_work(
    db: Session,
    project: Project,
    *,
    active_only: bool = False,
    limit: int = WORK_RECENT_LIMIT,
    compact: bool = False,
) -> list[dict[str, Any]]:
    stmt = select(WorkItem).where(WorkItem.project_id == project.id)
    if active_only:
        stmt = stmt.where(WorkItem.status.in_(("active", "blocked")))
    rows = db.scalars(
        stmt.order_by(WorkItem.updated_at.desc(), WorkItem.sequence.desc()).limit(
            max(1, min(limit, 50))
        )
    ).all()
    return [work_to_dict(db, row, compact=compact) for row in rows]


def get_work(db: Session, project: Project, key: str) -> dict[str, Any]:
    return work_to_dict(db, _work_for_key(db, project, key))
