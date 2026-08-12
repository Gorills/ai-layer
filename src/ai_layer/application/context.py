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


def _epic_context(project_root: str | Path) -> dict:
    """Return passive Epic state; lifecycle authority remains in explicit Epic tools."""
    try:
        rows = epic_uc.list_for_project(project_root, include_archived=False)
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    open_rows = [item for item in rows if item.get("status") in EPIC_OPEN_STATUSES]
    execution = next(
        (item for item in open_rows if item.get("status") in EPIC_EXECUTION_STATUSES),
        None,
    )
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
        "open": [
            {
                "key": item.get("key"),
                "title": item.get("title"),
                "status": item.get("status"),
                "mode": (
                    "execution" if item.get("status") in EPIC_EXECUTION_STATUSES else "design"
                ),
            }
            for item in open_rows[:8]
        ],
        "contract": "Informational only. Call epic_next explicitly when resuming a managed Epic.",
    }


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
    """Compatibility composite context; never chooses or advances Task/Epic workflow."""
    with session_scope() as db:
        project = get_project(db, project_root)
        result = build_memory_context(db, project, task, limit)
    result = dict(result)
    result["epic_state"] = _epic_context(project_root)
    result["execution_owner"] = "host-native agent runtime"
    result["workflow_contract"] = (
        "This payload is informational. Use project_status for continuation and call Task/Epic navigators "
        "only when explicitly resuming a managed workflow."
    )
    _add_source_verification_guidance(result)
    return result


def search_decisions(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return decision_search(db, project, query, limit)
