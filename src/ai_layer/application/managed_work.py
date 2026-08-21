from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.application.work_relations import ensure_task_work
from ai_layer.db.models import Project, Task, utcnow
from ai_layer.db.work_models import RuntimeEventContext, WorkItem
from ai_layer.observability.work_events import append_contextual_event
from ai_layer.work.service import finish_work, work_to_dict


def _task_row(db: Session, project: Project, payload: dict) -> Task:
    nested = payload.get("task")
    source: dict = nested if isinstance(nested, dict) else payload
    raw_id = str(source.get("id") or "").strip()
    if not raw_id:
        raise RuntimeError("managed Task result is missing id")
    task = db.scalar(select(Task).where(Task.id == UUID(raw_id), Task.project_id == project.id))
    if task is None:
        raise RuntimeError("managed Task no longer exists in this project")
    return task


def _backfill_task_context(db: Session, task: Task, work: WorkItem) -> None:
    for row in db.scalars(
        select(RuntimeEventContext).where(
            RuntimeEventContext.task_id == task.id, RuntimeEventContext.work_id.is_(None)
        )
    ).all():
        row.work_id = work.id


def _changed_paths(task: Task) -> list[str]:
    changes = dict(task.final_changes or {})
    paths: list[str] = []
    for field in ("added", "modified", "deleted", "renamed", "untracked"):
        value = changes.get(field)
        if isinstance(value, list):
            paths.extend(str(item) for item in value if isinstance(item, str) and item)
    return list(dict.fromkeys(paths))


def _terminal_summary(task: Task) -> str:
    return str(
        task.completion_summary
        or task.blocked_reason
        or f"Managed Task T-{task.sequence:04d} finished."
    )


def _sync_outcome_state(db: Session, project: Project, task: Task, work: WorkItem) -> bool:
    if task.status == "blocked" and work.status in {"active", "blocked"}:
        work.status = "blocked"
        work.result_summary = str(task.blocked_reason or "Managed Task is blocked.")[:4000]
        work.updated_at = utcnow()
        work.last_milestone_at = work.updated_at
        return False
    if task.status == "active" and work.status == "blocked":
        work.status = "active"
        work.updated_at = utcnow()
        work.last_milestone_at = work.updated_at
        return False
    if task.status not in {"completed", "cancelled"} or work.status not in {"active", "blocked"}:
        return False
    terminal = "completed" if task.status == "completed" else "abandoned"
    finish_work(
        db,
        project,
        work_key_value=f"W-{work.sequence:04d}",
        status=terminal,
        summary=_terminal_summary(task),
        changed_paths=_changed_paths(task),
    )
    return True


def _append_terminal_event(db: Session, project: Project, task: Task, work: WorkItem) -> None:
    event_type = "WorkCompleted" if work.status == "completed" else "WorkAbandoned"
    append_contextual_event(
        db,
        event_type=event_type,
        project=project,
        aggregate_type="work",
        aggregate_id=str(work.id),
        work=work,
        task_id=task.id,
        payload={
            "status": work.status,
            "summary": work.result_summary,
            "map_status": (work.map_disposition or {}).get("status", "pending"),
        },
        importance="high",
    )


def sync_task_backing_work(
    db: Session,
    project: Project,
    task_result: dict,
    *,
    create_if_missing: bool = False,
    preferred_work_key: str | None = None,
) -> dict | None:
    """Resolve canonical Task -> Work ownership and keep legacy Work projection compatible."""
    task = _task_row(db, project, task_result)
    binding = ensure_task_work(
        db,
        project,
        task,
        create_if_missing=create_if_missing,
        preferred_work_key=preferred_work_key,
    )
    if binding is None:
        return None

    work = binding.work
    _backfill_task_context(db, task, work)
    transitioned_terminal = False
    if binding.role == "outcome":
        transitioned_terminal = _sync_outcome_state(db, project, task, work)
    if transitioned_terminal:
        _append_terminal_event(db, project, task, work)
    db.commit()
    return work_to_dict(db, work, include_runs=False)
