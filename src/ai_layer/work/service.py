from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, Task, utcnow
from ai_layer.db.work_models import AgentRun, WorkItem

WORK_RUN_STALE_SECONDS = 300
WORK_RECENT_LIMIT = 8
WORK_GOAL_MAX_CHARS = 2000
WORK_SUMMARY_MAX_CHARS = 4000
WORK_ACTION_MAX_CHARS = 1000
WORK_PATH_LIMIT = 120
WORK_CHECK_LIMIT = 40
_TASK_KEY_RE = re.compile(r"^T-(\d{1,9})$", re.IGNORECASE)
_EPIC_KEY_RE = re.compile(r"^E-(\d{1,9})$", re.IGNORECASE)
_WORK_KEY_RE = re.compile(r"^W-(\d{1,9})$", re.IGNORECASE)


def _text(value: object, *, field: str, max_chars: int, required: bool = False) -> str:
    result = " ".join(str(value or "").strip().split())
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > max_chars:
        raise ValueError(f"{field} exceeds {max_chars} characters")
    return result


def _paths(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > WORK_PATH_LIMIT:
        raise ValueError(f"{field} exceeds {WORK_PATH_LIMIT} paths")
    result: list[str] = []
    for raw in value:
        path = str(raw or "").strip().replace("\\", "/")
        if not path or path.startswith("/") or path.startswith("../") or "/../" in path:
            raise ValueError(f"{field} contains a non-project-relative path")
        if path not in result:
            result.append(path)
    return result


def _checks(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("checks must be a list")
    if len(value) > WORK_CHECK_LIMIT:
        raise ValueError(f"checks exceeds {WORK_CHECK_LIMIT} items")
    result: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each check must be an object")
        result.append(
            {
                "name": _text(
                    item.get("name") or item.get("command"),
                    field="checks.name",
                    max_chars=240,
                    required=True,
                ),
                "status": _text(
                    item.get("status"), field="checks.status", max_chars=32, required=True
                ),
                "summary": _text(item.get("summary"), field="checks.summary", max_chars=500),
            }
        )
    return result


def _map_disposition(value: object) -> dict:
    if value is None:
        return {"status": "pending"}
    if not isinstance(value, dict):
        raise ValueError("map_disposition must be an object")
    status = _text(value.get("status"), field="map_disposition.status", max_chars=32, required=True)
    allowed = {"reconciled", "checked_no_change", "not_applicable", "deferred", "pending"}
    if status not in allowed:
        raise ValueError(
            "map_disposition.status must be reconciled, checked_no_change, not_applicable, deferred or pending"
        )
    scope = _paths(value.get("scope") or [], field="map_disposition.scope")
    reason = _text(value.get("reason"), field="map_disposition.reason", max_chars=500)
    event_id = _text(value.get("event_id"), field="map_disposition.event_id", max_chars=64)
    if status == "checked_no_change" and not scope:
        raise ValueError("checked_no_change requires non-empty map_disposition.scope")
    if status in {"not_applicable", "deferred"} and not reason:
        raise ValueError(f"{status} requires map_disposition.reason")
    return {"status": status, "scope": scope, "reason": reason, "event_id": event_id or None}


def work_key(work: WorkItem) -> str:
    return f"W-{int(work.sequence):04d}"


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
        "host": run.host,
        "client": run.client,
        "session_id": run.session_id,
        "turn_id": run.turn_id,
        "model": run.model,
        "last_meaningful_action": run.last_meaningful_action,
        "observability_coverage": run.observability_coverage,
        "assurance": run.assurance,
        "started_at": run.started_at.isoformat(),
        "heartbeat_at": run.heartbeat_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
    }


def work_to_dict(db: Session, work: WorkItem, *, include_runs: bool = True) -> dict[str, Any]:
    runs: list[dict] = []
    live = False
    if include_runs:
        rows = db.scalars(
            select(AgentRun)
            .where(AgentRun.work_id == work.id)
            .order_by(AgentRun.started_at, AgentRun.id)
        ).all()
        runs = [run_to_dict(row) for row in rows]
        live = any(item["status"] == "active" and not item["stale"] for item in runs)
    disposition = dict(work.map_disposition or {}) or {"status": "pending"}
    return {
        "id": str(work.id),
        "key": work_key(work),
        "goal": work.goal,
        "kind": work.kind,
        "status": work.status,
        "live": live and work.status in {"active", "blocked"},
        "result_summary": work.result_summary,
        "reviewed_paths": list(work.reviewed_paths or []),
        "changed_paths": list(work.changed_paths or []),
        "repository_delta": dict(work.repository_delta or {}),
        "checks": list(work.checks or []),
        "map_disposition": disposition,
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
    if normalized_coverage not in {
        "full_host_hooks",
        "lifecycle_only",
        "control_plane_only",
        "inferred_repository_delta",
        "unavailable",
    }:
        raise ValueError("unsupported observability_coverage")
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
        goal=_text(goal, field="goal", max_chars=WORK_GOAL_MAX_CHARS, required=True),
        kind=normalized_kind,
        status="active",
        map_disposition={"status": "pending"},
        observability_coverage=normalized_coverage,
        assurance=_text(assurance, field="assurance", max_chars=32) or "agent_reported",
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
        host=_text(host, field="host", max_chars=64) or "unknown",
        client=_text(client, field="client", max_chars=64) or "unknown",
        session_id=_text(session_id, field="session_id", max_chars=128),
        turn_id=_text(turn_id, field="turn_id", max_chars=128),
        model=_text(model, field="model", max_chars=128),
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
) -> tuple[WorkItem, AgentRun | None]:
    work = _work_for_key(db, project, work_key_value, lock=True)
    if work.status not in {"active", "blocked"}:
        raise RuntimeError(f"work item {work_key(work)} is terminal: {work.status}")
    now = utcnow()
    if summary:
        work.result_summary = _text(summary, field="summary", max_chars=WORK_SUMMARY_MAX_CHARS)
    if reviewed_paths is not None:
        work.reviewed_paths = _paths(reviewed_paths, field="reviewed_paths")
    if changed_paths is not None:
        work.changed_paths = _paths(changed_paths, field="changed_paths")
    if checks is not None:
        work.checks = _checks(checks)
    if repository_delta is not None:
        if not isinstance(repository_delta, dict):
            raise ValueError("repository_delta must be an object")
        work.repository_delta = dict(repository_delta)
    if blocked is not None:
        work.status = "blocked" if blocked else "active"
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
            run.last_meaningful_action = _text(
                summary, field="summary", max_chars=WORK_ACTION_MAX_CHARS
            )
    db.flush()
    return work, run


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
    now = utcnow()
    work.status = terminal
    work.result_summary = _text(
        summary, field="summary", max_chars=WORK_SUMMARY_MAX_CHARS, required=True
    )
    if reviewed_paths is not None:
        work.reviewed_paths = _paths(reviewed_paths, field="reviewed_paths")
    if changed_paths is not None:
        work.changed_paths = _paths(changed_paths, field="changed_paths")
    if checks is not None:
        work.checks = _checks(checks)
    if repository_delta is not None:
        if not isinstance(repository_delta, dict):
            raise ValueError("repository_delta must be an object")
        work.repository_delta = dict(repository_delta)
    work.map_disposition = _map_disposition(map_disposition)
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
    db: Session, project: Project, *, active_only: bool = False, limit: int = WORK_RECENT_LIMIT
) -> list[dict[str, Any]]:
    stmt = select(WorkItem).where(WorkItem.project_id == project.id)
    if active_only:
        stmt = stmt.where(WorkItem.status.in_(("active", "blocked")))
    rows = db.scalars(
        stmt.order_by(WorkItem.updated_at.desc(), WorkItem.sequence.desc()).limit(
            max(1, min(limit, 50))
        )
    ).all()
    return [work_to_dict(db, row) for row in rows]


def get_work(db: Session, project: Project, key: str) -> dict[str, Any]:
    return work_to_dict(db, _work_for_key(db, project, key))
