from __future__ import annotations

from pathlib import Path

from ai_layer.application import epics as epic_uc
from ai_layer.context.service import memory_context as build_memory_context
from ai_layer.core.service import get_project, project_info
from ai_layer.db.session import session_scope
from ai_layer.memory.service import decision_search, memory_search


def project_details(project_root: str | Path) -> dict:
    with session_scope() as db:
        return project_info(db, project_root)


def search_memory(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return memory_search(db, project, query, limit)


def _epic_context(project_root: str | Path) -> dict:
    try:
        rows = epic_uc.list_for_project(project_root, include_archived=False)
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    execution_states = {"approved", "phase0", "planning", "running", "final_review", "blocked"}
    active = next((item for item in rows if item.get("status") in execution_states), None)
    return {
        "available": True,
        "active": (
            {
                "key": active.get("key"),
                "title": active.get("title"),
                "status": active.get("status"),
                "execution_spec_version": active.get("execution_spec_version"),
                "instruction": "Call epic_next for this Epic; use task_next only when Epic navigation says continue_task.",
            }
            if active
            else None
        ),
        "open": [
            {"key": item.get("key"), "title": item.get("title"), "status": item.get("status")}
            for item in rows[:8]
        ],
    }


def get_memory_context(project_root: str | Path, task: str, limit: int = 4) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        result = build_memory_context(db, project, task, limit)
    result = dict(result)
    result["epic_state"] = _epic_context(project_root)
    return result


def search_decisions(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return decision_search(db, project, query, limit)
