from __future__ import annotations

from sqlalchemy.orm import Session

from ai_layer.db.models import Project
from ai_layer.memory.service import memory_context as build_memory_payload
from ai_layer.tasks.navigation import next_task_action


def memory_context(db: Session, project: Project, task: str, limit: int = 4) -> dict:
    """Build task context while keeping Memory independent from Task implementation."""
    runtime = next_task_action(db, project)
    return build_memory_payload(db, project, task, limit, task_runtime=runtime)
