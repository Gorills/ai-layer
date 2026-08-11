from __future__ import annotations

from pathlib import Path

from ai_layer.context.service import memory_context as build_memory_context
from ai_layer.core.service import get_project, project_info
from ai_layer.db.session import session_scope
from ai_layer.memory.service import decision_search, memory_search


def project_details(project_root: str | Path) -> dict:
    with session_scope() as db:
        return project_info(db, project_root)


def search_memory(project_root: str | Path, query: str, limit: int = 8) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        return memory_search(db, project, query, limit)


def get_memory_context(project_root: str | Path, task: str, limit: int = 4) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        return build_memory_context(db, project, task, limit)


def search_decisions(project_root: str | Path, query: str, limit: int = 8) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        return decision_search(db, project, query, limit)
