from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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


def _linked_work(db: Session, task: Task) -> WorkItem | None:
    return db.scalar(
        select(WorkItem)
        .where(WorkItem.project_id == task.project_id, WorkItem.linked_task_id == task.id)
        .order_by(WorkItem.updated_at.desc(), WorkItem.sequence.desc())
        .limit(1)
    )


def _matching_unlinked_work(db: Session, task: Task) -> WorkItem | None:
    rows = list(
        db.scalars(
            select(WorkItem)
            .where(
                WorkItem.project_id == task.project_id,
                WorkItem.linked_task_id.is_(None),
                WorkItem.status.in_(("active", "blocked")),
                WorkItem.goal == task.goal,
            )
            .order_by(WorkItem.updated_at.desc(), WorkItem.sequence.desc())
            .limit(2)
        ).all()
    )
    return rows[0] if len(rows) == 1 else None


def _new_control_plane_work(db: Session, project: Project, task: Task) -> WorkItem:
    locked = db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    if locked is None:
        raise RuntimeError("project no longer exists")
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
        goal=task.goal,
        kind="research" if task.workflow_profile == "analysis_only" else "change",
        status="active",
        map_disposition={"status": "pending"},
        observability_coverage="control_plane_only",
        assurance="agent_reported",
        linked_task_id=task.id,
        started_at=now,
        updated_at=now,
        last_milestone_at=now,
    )
    db.add(work)
    db.flush()
    append_contextual_event(
        db,
        event_type="WorkStarted",
        project=project,
        aggregate_type="work",
        aggregate_id=str(work.id),
        work=work,
        task_id=task.id,
        payload={"goal": work.goal, "kind": work.kind, "status": work.status},
        importance="high",
    )
    return work


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


def sync_task_backing_work(
    db: Session,
    project: Project,
    task_result: dict,
    *,
    create_if_missing: bool = False,
) -> dict | None:
    """Derive backing Work from managed Task state; callers never ask the agent to maintain the link."""
    task = _task_row(db, project, task_result)
    work = _linked_work(db, task)
    if work is None and create_if_missing:
        work = _matching_unlinked_work(db, task)
        if work is not None:
            work.linked_task_id = task.id
            work.updated_at = utcnow()
            work.last_milestone_at = work.updated_at
        else:
            work = _new_control_plane_work(db, project, task)
    if work is None:
        return None

    _backfill_task_context(db, task, work)
    transitioned_terminal = False
    if task.status == "blocked" and work.status in {"active", "blocked"}:
        work.status = "blocked"
        work.result_summary = str(task.blocked_reason or "Managed Task is blocked.")[:4000]
        work.updated_at = utcnow()
        work.last_milestone_at = work.updated_at
    elif task.status == "active" and work.status == "blocked":
        work.status = "active"
        work.updated_at = utcnow()
        work.last_milestone_at = work.updated_at
    elif task.status in {"completed", "cancelled"} and work.status in {"active", "blocked"}:
        terminal = "completed" if task.status == "completed" else "abandoned"
        work, _runs = finish_work(
            db,
            project,
            work_key_value=f"W-{work.sequence:04d}",
            status=terminal,
            summary=_terminal_summary(task),
            changed_paths=_changed_paths(task),
        )
        transitioned_terminal = True

    if transitioned_terminal:
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
    db.commit()
    return work_to_dict(db, work, include_runs=False)
