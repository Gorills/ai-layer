"""Compatibility application facade for transport adapters.

The pre-foundation transports historically opened ORM sessions themselves.  This module preserves
those call shapes while moving transaction ownership behind the application boundary.  New transport
code should prefer the focused use-case modules directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_layer.application import context as context_uc
from ai_layer.application import sessions as sessions_uc
from ai_layer.application import tasks as tasks_uc
from ai_layer.application import verification as verification_uc
from ai_layer.application.projects import project_identity


@dataclass(frozen=True)
class ProjectRef:
    id: str
    root_path: str
    name: str


class ApplicationScope:
    """Opaque transport scope. It deliberately exposes no ORM/query API."""


@contextmanager
def application_scope() -> Iterator[ApplicationScope]:
    yield ApplicationScope()


def get_project(_scope: ApplicationScope, root: str | Path) -> ProjectRef:
    item = project_identity(root)
    return ProjectRef(id=item["id"], root_path=item["root_path"], name=item["name"])


def project_info(_scope: ApplicationScope, root: str | Path) -> dict:
    return context_uc.project_details(root)


def memory_search(
    _scope: ApplicationScope, project: ProjectRef, query: str, limit: int
) -> list[dict]:
    return context_uc.search_memory(project.root_path, query, limit)


def memory_context(_scope: ApplicationScope, project: ProjectRef, task: str, limit: int) -> dict:
    return context_uc.get_memory_context(project.root_path, task, limit)


def decision_search(
    _scope: ApplicationScope, project: ProjectRef, query: str, limit: int
) -> list[dict]:
    return context_uc.search_decisions(project.root_path, query, limit)


def task_current(
    _scope: ApplicationScope, project: ProjectRef, *, include_history: bool = True
) -> dict:
    return tasks_uc.current(project.root_path, include_history=include_history)


def task_next(_scope: ApplicationScope, project: ProjectRef) -> dict:
    return tasks_uc.next_action(project.root_path)


def task_create(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return tasks_uc.create(project.root_path, **kwargs)


def task_adopt(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return tasks_uc.adopt(project.root_path, **kwargs)


def task_delegate(
    _scope: ApplicationScope, project: ProjectRef, *, worker_id: str, **kwargs: Any
) -> dict:
    return tasks_uc.delegate(project.root_path, worker_id=worker_id, **kwargs)


def task_complete_current(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return tasks_uc.complete_current(project.root_path, **kwargs)


def task_complete_legacy(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return tasks_uc.complete_legacy(project.root_path, **kwargs)


def task_worker_disconnected(_scope: ApplicationScope, project: ProjectRef, *, reason: str) -> dict:
    return tasks_uc.worker_disconnected(project.root_path, reason=reason)


def task_worker_heartbeat(
    _scope: ApplicationScope,
    project: ProjectRef,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> dict:
    return tasks_uc.worker_heartbeat(
        project.root_path,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )


def task_resume(_scope: ApplicationScope, project: ProjectRef) -> dict:
    return tasks_uc.resume(project.root_path)


def task_cancel(_scope: ApplicationScope, project: ProjectRef, *, reason: str) -> dict:
    return tasks_uc.cancel(project.root_path, reason=reason)


def prepare_review_sandbox(_scope: ApplicationScope, project: ProjectRef) -> dict:
    return tasks_uc.prepare_review_sandbox(project.root_path)


def run_review_check(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return tasks_uc.run_review_check(project.root_path, **kwargs)


def cleanup_review_sandbox(_scope: ApplicationScope, project: ProjectRef) -> dict:
    return tasks_uc.cleanup_review_sandbox(project.root_path)


def list_sessions(_scope: ApplicationScope, project: ProjectRef, limit: int) -> list[dict]:
    return sessions_uc.list_project_sessions(project.root_path, limit)


def restore_session(_scope: ApplicationScope, project: ProjectRef, session_id: str) -> dict | None:
    return sessions_uc.restore_project_session(project.root_path, session_id)


def save_session(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return sessions_uc.save_project_session(project.root_path, **kwargs)


def run_verification(_scope: ApplicationScope, project: ProjectRef, **kwargs: Any) -> dict:
    return verification_uc.run_stage_verification(project.root_path, **kwargs)
