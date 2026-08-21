from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from ai_layer.application.action_state import (
    _public_worker_packet,
    _state_response,
    _upsert_action_state,
    _worker_kind,
)
from ai_layer.db.models import Project, Task
from ai_layer.db.work_models import WorkItem
from ai_layer.tasks.service import delegate_current_stage
from ai_layer.tasks.state_store import task_key
from ai_layer.tasks.views import _active_stage, task_to_dict


def managed_action(db: Session, project: Project, work: WorkItem, task: Task) -> dict:
    """Derive the public action for authoritative managed Task state."""
    if task.status == "completed":
        state = _upsert_action_state(
            db,
            project,
            work,
            task=task,
            stage=None,
            kind="done",
            worker_kind=None,
            worker_id="",
            state_version=int(task.version or 1),
            instruction="Managed assurance is complete; record the durable Work outcome.",
        )
        return _state_response(db, project, work, state)
    if task.status == "cancelled":
        state = _upsert_action_state(
            db,
            project,
            work,
            task=task,
            stage=None,
            kind="done",
            worker_kind=None,
            worker_id="",
            state_version=int(task.version or 1),
            instruction="Managed assurance was cancelled; close the Work with the appropriate terminal status.",
        )
        return _state_response(db, project, work, state)
    if task.status == "blocked":
        state = _upsert_action_state(
            db,
            project,
            work,
            task=task,
            stage=None,
            kind="human_decision",
            worker_kind=None,
            worker_id="",
            state_version=int(task.version or 1),
            instruction=task.blocked_reason
            or "Managed assurance is blocked; choose how to continue.",
            payload={"choices": ["resume", "cancel"]},
        )
        return _state_response(db, project, work, state)
    if task.status != "active":
        raise RuntimeError(f"unsupported managed Task status: {task.status}")

    stage = _active_stage(db, task)
    if stage is None:
        raise RuntimeError(f"active managed Task {task_key(task)} has no active stage")
    if bool(stage.delegation_required) and not stage.worker_id:
        worker_id = f"facade-{secrets.token_hex(12)}"
        delegate_current_stage(
            db,
            project,
            worker_id=worker_id,
            expected_version=int(task.version or 1),
        )
        refreshed_task = db.get(Task, task.id)
        if refreshed_task is None:
            raise RuntimeError("managed Task disappeared after worker binding")
        task = refreshed_task
        stage = _active_stage(db, task)
        if stage is None or not stage.worker_id:
            raise RuntimeError("worker binding did not produce a delegated active stage")
    if not stage.worker_id:
        raise RuntimeError("Phase 3 facade path requires an explicitly bound managed worker")

    task_payload = task_to_dict(db, task, include_history=False)
    worker = _public_worker_packet(task_payload, stage)
    worker_kind = _worker_kind(stage)
    state = _upsert_action_state(
        db,
        project,
        work,
        task=task,
        stage=stage,
        kind="run_worker",
        worker_kind=worker_kind,
        worker_id=stage.worker_id,
        state_version=int(task.version or 1),
        instruction="Run the bound worker from the returned compact job contract, then report its real result.",
        payload={"worker": worker},
    )
    return _state_response(db, project, work, state)
