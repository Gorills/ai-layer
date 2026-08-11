from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, Task, TaskStage


def lock_project(db: Session, project: Project) -> None:
    """Serialize project workflow mutations in PostgreSQL.

    Filesystem locks remain a local optimization, but the database row lock is the cross-process
    authority and works even when callers do not share a filesystem lock namespace.
    """
    stmt = select(Project.id).where(Project.id == project.id).with_for_update()
    if db.scalar(stmt) is None:
        raise RuntimeError("Registered project disappeared while acquiring workflow lock.")


def open_task_for_update(
    db: Session,
    project: Project,
    *,
    statuses: Iterable[str],
    latest: bool = True,
) -> Task | None:
    lock_project(db, project)
    stmt = select(Task).where(Task.project_id == project.id, Task.status.in_(tuple(statuses)))
    if latest:
        stmt = stmt.order_by(Task.updated_at.desc())
    return db.scalar(stmt.with_for_update().limit(1))


def active_stage_for_update(db: Session, task: Task) -> TaskStage | None:
    return db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == task.id, TaskStage.status == "active")
        .order_by(TaskStage.ordinal.desc())
        .with_for_update()
        .limit(1)
    )


def assert_expected_version(task: Task, expected_version: int | None) -> None:
    """Reject stale remote-style mutations without weakening local call compatibility."""
    if expected_version is None:
        return
    expected = int(expected_version)
    actual = int(task.version or 1)
    if expected != actual:
        raise RuntimeError(
            f"STALE_TASK_VERSION: expected task version {expected}, current version is {actual}."
        )


def bump_task_version(task: Task) -> None:
    """Advance the optimistic-concurrency token for every authoritative mutation."""
    task.version = max(1, int(task.version or 1)) + 1
