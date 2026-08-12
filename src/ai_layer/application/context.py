from __future__ import annotations

from pathlib import Path

from ai_layer.application import epics as epic_uc
from ai_layer.context.service import memory_context as build_memory_context
from ai_layer.core.service import get_project, project_info
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import EPIC_EXECUTION_STATUSES, EPIC_OPEN_STATUSES
from ai_layer.memory.service import decision_search, memory_search


def project_details(project_root: str | Path) -> dict:
    with session_scope() as db:
        return project_info(db, project_root)


def search_memory(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return memory_search(db, project, query, limit)


def _epic_intent(query: str, open_epics: list[dict]) -> list[dict]:
    text = str(query or "").casefold()
    direct = []
    for item in open_epics:
        key = str(item.get("key") or "").strip()
        title = str(item.get("title") or "").strip()
        if (key and key.casefold() in text) or (len(title) >= 8 and title.casefold() in text):
            direct.append(item)
    if direct:
        return direct
    if "epic" in text or "эпик" in text:
        return open_epics
    return []


def _workflow_focus(query: str, open_epics: list[dict], task_runtime: dict) -> dict:
    next_task = dict(task_runtime.get("next_action") or {})
    if task_runtime.get("active"):
        return {"authority": "task", **next_task}

    epic_matches = _epic_intent(query, open_epics)
    if len(epic_matches) == 1:
        epic = epic_matches[0]
        return {
            "authority": "epic",
            "action": "continue_epic",
            "tool": "epic_next",
            "epic_key": epic.get("key"),
            "message": (
                "This request explicitly targets an Epic. The Epic controls only this design/execution "
                "conversation; unrelated ordinary Tasks remain available when Epic work is not selected."
            ),
        }
    if len(epic_matches) > 1:
        return {
            "authority": "epic_selection",
            "action": "choose_epic",
            "tool": "epic_list",
            "message": "Multiple open Epics match this request; select the intended Epic before continuing.",
        }
    return {"authority": "task", **next_task}


def _epic_context(project_root: str | Path, query: str, task_runtime: dict) -> dict:
    try:
        rows = epic_uc.list_for_project(project_root, include_archived=False)
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"[:300]}

    open_rows = [item for item in rows if item.get("status") in EPIC_OPEN_STATUSES]
    execution = next(
        (item for item in open_rows if item.get("status") in EPIC_EXECUTION_STATUSES),
        None,
    )
    open_compact = [
        {
            "key": item.get("key"),
            "title": item.get("title"),
            "status": item.get("status"),
            "mode": ("execution" if item.get("status") in EPIC_EXECUTION_STATUSES else "design"),
            "passive": item.get("status") not in EPIC_EXECUTION_STATUSES,
        }
        for item in open_rows[:8]
    ]
    return {
        "available": True,
        "active": (
            {
                "key": execution.get("key"),
                "title": execution.get("title"),
                "status": execution.get("status"),
                "execution_spec_version": execution.get("execution_spec_version"),
            }
            if execution
            else None
        ),
        "open": open_compact,
        "workflow_focus": _workflow_focus(query, open_compact, task_runtime),
    }


def _apply_workflow_focus(result: dict, epic_state: dict) -> dict:
    task_runtime = dict(result.get("task_runtime") or {})
    focus = dict(epic_state.get("workflow_focus") or {})
    if not focus:
        focus = {"authority": "task", **dict(task_runtime.get("next_action") or {})}

    result["workflow_next_action"] = focus
    guidance = dict(result.get("tool_guidance") or {})
    if focus.get("authority") in {"epic", "epic_selection"}:
        if not task_runtime.get("active"):
            task_runtime["next_action"] = {}
            guidance.pop("next_task_action", None)
        guidance["workflow_next_action"] = focus
    else:
        guidance["workflow_next_action"] = focus
        if "next_task_action" not in guidance:
            guidance["next_task_action"] = dict(task_runtime.get("next_action") or {})
    result["task_runtime"] = task_runtime
    result["tool_guidance"] = guidance
    return result


def _add_source_verification_guidance(result: dict) -> None:
    freshness = dict(result.get("freshness") or {})
    status = str(freshness.get("status") or "").casefold()
    withheld = bool(freshness.get("scanner_evidence_withheld"))
    if withheld or (status and status not in {"fresh", "refreshed"}):
        result["source_verification"] = {
            "required": True,
            "authority": "current repository source via host-native tools",
            "wait_for_scanner": False,
            "scanner_evidence_current": False,
            "reason": "scanner_snapshot_not_current",
            "instruction": (
                "Inspect current source directly for code-truth claims. Do not wait for scanner refresh and "
                "do not treat withheld/stale scanner evidence as current repository truth."
            ),
        }


def get_memory_context(project_root: str | Path, task: str, limit: int = 4) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        result = build_memory_context(db, project, task, limit)
    result = dict(result)
    task_runtime = dict(result.get("task_runtime") or {})
    epic_state = _epic_context(project_root, task, task_runtime)
    result["epic_state"] = epic_state
    _apply_workflow_focus(result, epic_state)
    _add_source_verification_guidance(result)
    return result


def search_decisions(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return decision_search(db, project, query, limit)
