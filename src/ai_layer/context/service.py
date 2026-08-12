from __future__ import annotations

from sqlalchemy.orm import Session

from ai_layer.db.models import Project
from ai_layer.memory.service import memory_context as build_memory_payload


def memory_context(db: Session, project: Project, task: str, limit: int = 4) -> dict:
    """Build legacy composite context without invoking Task workflow navigation."""
    return build_memory_payload(db, project, task, limit, task_runtime=None)
