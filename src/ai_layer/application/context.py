from __future__ import annotations

from pathlib import Path

from ai_layer.application import epics as epic_uc
from ai_layer.context.service import memory_context as build_memory_context
from ai_layer.core.service import get_project, project_info
from ai_layer.db.session import session_scope
from ai_layer.domain.project_map import project_map_capability_contract
from ai_layer.epics.contracts import EPIC_EXECUTION_STATUSES, EPIC_OPEN_STATUSES
from ai_layer.memory.service import decision_search, memory_search

LEGACY_CONTEXT_EPIC_OPEN_LIMIT = 8
LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT = 2
LEGACY_CONTEXT_SUMMARY_MAX_CHARS = 700
LEGACY_CONTEXT_SOURCE_POINTER_LIMIT = 6


def project_details(project_root: str | Path) -> dict:
    with session_scope() as db:
        return project_info(db, project_root)


def search_knowledge(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return memory_search(db, project, query, limit)


def search_memory(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:
    """Backward-compatible application alias for search_knowledge."""
    return search_knowledge(project_root, query, limit)


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
            for item in open_rows[:LEGACY_CONTEXT_EPIC_OPEN_LIMIT]
        ],
        "contract": "Informational only. Call epic_next explicitly when resuming a managed Epic.",
    }


def _knowledge_hint(item: dict) -> dict:
    return {
        "key": item.get("key"),
        "title": item.get("title"),
        "summary": str(item.get("summary") or "")[:LEGACY_CONTEXT_SUMMARY_MAX_CHARS],
        "source_pointers": list(item.get("source_pointers") or [])[
            :LEGACY_CONTEXT_SOURCE_POINTER_LIMIT
        ],
        "score": item.get("score"),
    }


def _compact_legacy_context(payload: dict) -> dict:
    project = dict(payload.get("project") or {})
    state = dict(payload.get("knowledge_state") or {})
    brief = dict(payload.get("task_brief") or {})
    freshness = dict(payload.get("freshness") or {})
    return {
        "compatibility": {
            "legacy": True,
            "preferred_startup": "project_status",
            "contract": (
                "memory_context is a compact compatibility helper, not the project bootstrap. Use project_status "
                "for continuation/current work, project_search for Project Map navigation, knowledge_search for "
                "reviewed facts, and decision_search for rationale."
            ),
        },
        "project": {
            "name": project.get("name"),
            "root_path": project.get("root_path"),
        },
        "knowledge_state": {
            "verified": int(state.get("verified") or 0),
            "stale": int(state.get("stale") or 0),
            "draft": int(state.get("draft") or 0),
            "baseline_ready": bool(state.get("baseline_ready")),
        },
        "knowledge_hints": [
            _knowledge_hint(item)
            for item in list(brief.get("verified_knowledge") or [])[
                :LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT
            ]
        ],
        "freshness": {
            "status": freshness.get("status"),
            "snapshot_available": freshness.get("snapshot_available"),
            "background_refresh": freshness.get("background_refresh"),
            "refresh_job": freshness.get("refresh_job"),
            "scanner_evidence_withheld": bool(freshness.get("scanner_evidence_withheld")),
        },
        "policy": payload.get("policy") or "",
        "project_map": project_map_capability_contract(),
        "preferred_calls": {
            "state": "project_status",
            "navigation": "project_search",
            "map_update": "project_map_reconcile",
            "knowledge": "knowledge_search",
            "decisions": "decision_search",
        },
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
    """Return a compact compatibility context; workflow/navigation live in focused APIs."""
    with session_scope() as db:
        project = get_project(db, project_root)
        legacy = build_memory_context(db, project, task, limit)
    result = _compact_legacy_context(legacy)
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
