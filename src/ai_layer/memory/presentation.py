from __future__ import annotations

import json

CONTINUATION_EXACT = {
    "continue",
    "resume",
    "carry on",
    "продолжай",
    "продолжи",
    "возобнови",
}
CONTINUATION_VERBS = ("continue", "resume", "carry on", "продолж", "возобнов")
CONTINUATION_OBJECTS = (
    "task",
    "work",
    "implementation",
    "plan",
    "previous",
    "prior",
    "earlier",
    "yesterday",
    "задач",
    "работ",
    "реализац",
    "план",
    "предыдущ",
    "прошл",
    "ранее",
    "вчера",
)

KNOWLEDGE_AUDIT_HINTS = ("audit", "review", "провер", "аудит")
KNOWLEDGE_SCOPE_HINTS = (
    "project knowledge",
    "verified knowledge",
    "knowledge base",
    "баз знаний",
    "база знаний",
    "базы знаний",
)
COVERAGE_HINTS = ("coverage", "completeness", "полнот", "покрыт")
CURRENT_SCANNER_STATUSES = {"fresh", "refreshed"}


def is_continuation_intent(task: str) -> bool:
    low = " ".join(str(task or "").casefold().split())
    normalized = low.strip(" \t\r\n.!?,:;")
    if normalized in CONTINUATION_EXACT:
        return True
    starts_with_verb = any(low.startswith(verb) for verb in CONTINUATION_VERBS)
    has_continuation_object = any(token in low for token in CONTINUATION_OBJECTS)
    return starts_with_verb and has_continuation_object


def context_mode(task: str) -> str:
    if is_continuation_intent(task):
        return "continuation"
    low = str(task or "").casefold()
    is_knowledge = any(token in low for token in KNOWLEDGE_SCOPE_HINTS)
    is_audit = any(token in low for token in KNOWLEDGE_AUDIT_HINTS)
    if not (is_knowledge and is_audit):
        return "task"
    if any(token in low for token in COVERAGE_HINTS):
        return "knowledge_coverage_audit"
    return "knowledge_audit"


def compact_inventory(cards: list[dict]) -> list[dict]:
    """Complete catalog surface: every key/title, short summaries only for reasonably small catalogs."""
    include_summary = len(cards) <= 60
    result: list[dict] = []
    for card in cards:
        item = {
            "key": card.get("key"),
            "category": card.get("category"),
            "title": str(card.get("title") or "")[:140],
            "unknown_count": len(card.get("unknowns") or []),
            "source_pointer_count": len(card.get("source_pointers") or []),
        }
        if include_summary:
            item["summary"] = str(card.get("summary") or "")[:260]
        result.append(item)
    return result


def _compact_next_action(runtime: dict) -> dict:
    task = runtime.get("task") or {}
    next_action = dict(task.get("next_action") or runtime.get("next_action") or {})
    return {
        key: next_action.get(key)
        for key in (
            "action",
            "tool",
            "stage",
            "stage_id",
            "worker_id",
            "required",
            "forbidden",
            "message",
        )
        if next_action.get(key) is not None
    }


def compact_task_runtime(runtime: dict) -> dict:
    """Minimal Task Layer state for ordinary memory_context calls. Full history belongs to task_current."""
    task = runtime.get("task") or {}
    result = {
        "active": bool(runtime.get("active")),
        "state": runtime.get("state"),
        "project_root": runtime.get("project_root"),
        "next_action": _compact_next_action(runtime),
    }
    if result["active"] and task:
        result["active_task"] = {
            key: task.get(key)
            for key in ("id", "key", "goal", "status", "workflow_profile", "active_stage")
            if task.get(key) is not None
        }
    preexisting = runtime.get("preexisting_changes") or {}
    if preexisting:
        result["preexisting_change_count"] = int(preexisting.get("total") or 0)
    return result


def compact_audit_runtime(runtime: dict) -> dict:
    """Keep navigation authority without previous stage reasoning or completed-task internals."""
    task = runtime.get("task") or {}
    result = {
        "active": bool(runtime.get("active")),
        "state": runtime.get("state"),
        "project_root": runtime.get("project_root"),
        "next_action": _compact_next_action(runtime),
    }
    if result["active"] and task:
        result["task"] = {
            key: task.get(key)
            for key in ("id", "key", "goal", "status", "workflow_profile", "active_stage")
            if task.get(key) is not None
        }
    preexisting = runtime.get("preexisting_changes") or {}
    if preexisting:
        result["preexisting_change_count"] = int(preexisting.get("total") or 0)
    return result


def compact_continuation_runtime(runtime: dict) -> dict:
    """Expose only the durable navigator for continuation; session/task history lives in the brief."""
    task = runtime.get("task") or {}
    result = {
        "active": bool(runtime.get("active")),
        "state": runtime.get("state"),
        "project_root": runtime.get("project_root"),
        "next_action": _compact_next_action(runtime),
    }
    if result["active"] and task:
        result["active_task"] = {
            key: task.get(key)
            for key in ("id", "key", "goal", "status", "workflow_profile", "active_stage")
            if task.get(key) is not None
        }
    preexisting = runtime.get("preexisting_changes") or {}
    if preexisting:
        result["preexisting_change_count"] = int(preexisting.get("total") or 0)
    return result


def compact_audit_guidance(
    project_root: str, mode: str, runtime: dict, *, inventory_complete: bool
) -> dict:
    return {
        "project_context": {"canonical_root": project_root},
        "next_task_action": _compact_next_action(runtime),
    }


def compact_continuation_guidance(project_root: str, runtime: dict) -> dict:
    calls = [
        {
            "tool": "session_restore",
            "when": "continuation was explicitly requested",
            "args": {"session_id": "latest", "project_root": project_root},
        }
    ]
    if runtime.get("active"):
        calls.append(
            {
                "tool": "task_next",
                "when": "resume the active managed workflow after restoring the handoff",
                "args": {"project_root": project_root},
            }
        )
    return {
        "recommended_calls": calls,
        "project_context": {"canonical_root": project_root},
        "next_task_action": _compact_next_action(runtime),
    }


def compact_audit_scanner_evidence(intelligence: dict) -> dict:
    stack = intelligence.get("stack") or {}
    data = intelligence.get("data") or {}
    testing = intelligence.get("testing") or {}
    docs = intelligence.get("documentation") or {}
    return {
        "assurance": "AI_LAYER_OBSERVED repository hints only; not reviewed semantic knowledge.",
        "manifests": list(stack.get("manifests") or [])[:12],
        "databases": list(data.get("databases") or [])[:8],
        "test_files": int(testing.get("test_files") or 0),
        "documentation_domains": sorted((docs.get("domains") or {}).keys())[:12],
    }


def scanner_snapshot_current(freshness: dict) -> bool:
    return str(freshness.get("status") or "").casefold() in CURRENT_SCANNER_STATUSES


def present_scanner_evidence(evidence: dict, freshness: dict, *, mode: str) -> dict:
    """Never expose scanner-derived facts when their repository snapshot is known to be stale."""
    if mode == "continuation":
        return {
            "available": False,
            "reason": "continuation_mode_uses_session_history_and_current_source",
        }
    if not scanner_snapshot_current(freshness):
        return {
            "available": False,
            "reason": "scanner_snapshot_not_current",
            "freshness_status": freshness.get("status"),
            "snapshot_available": bool(freshness.get("snapshot_available")),
        }
    return evidence


def build_task_brief(mode: str, materials: dict) -> dict:
    brief = {
        "relevant_history": materials["history"],
        "source_contract": "Project Knowledge is reviewed navigation/history; current repository files remain authoritative.",
    }
    if mode.startswith("knowledge_"):
        brief.update(
            {
                "presentation_mode": mode,
                "knowledge_inventory": materials["inventory"],
                "stale_inventory": materials["stale_inventory"],
                "inventory_complete": materials["inventory_complete"],
                "audit_contract": {
                    "goal": (
                        "Find material coverage gaps in existing VERIFIED Project Knowledge."
                        if mode == "knowledge_coverage_audit"
                        else "Independently verify factual correctness and sufficiency of VERIFIED Project Knowledge."
                    ),
                    "independence": "Previous reviewer reasoning is intentionally excluded from this context.",
                    "expand_only_when_needed": True,
                },
            }
        )
    elif mode == "continuation":
        return {
            "presentation_mode": "continuation",
            "recent_work": materials["history"][0] if materials["history"] else None,
            "continuation_contract": {
                "primary_action": "session_restore(latest)",
                "fallback": (
                    "If no committed session exists, treat recent_work only as historical evidence and inspect current "
                    "repository source before continuing. Never invent prior-session state."
                ),
            },
            "source_contract": "Current repository source is authoritative for implementation state.",
        }
    else:
        brief.update(
            {
                "verified_knowledge": materials["knowledge"],
                "stale_knowledge": materials["stale"],
                "relevant_decisions": materials["decisions"],
                "source_pointers": materials["source_pointers"],
            }
        )
    return brief


def context_budget(
    mode: str,
    policy_text: str,
    materials: dict,
    *,
    total_target_chars: int,
    policy_soft_target_chars: int,
) -> dict:
    knowledge_audit = mode.startswith("knowledge_")
    budget_mode = "task_project_brief+dynamic_policy+compact_runtime"
    if knowledge_audit:
        budget_mode = "knowledge_audit_inventory+compact_read_only_control_plane"
    elif mode == "continuation":
        budget_mode = "continuation_session_first+dynamic_policy+compact_runtime"
    expansion = "Use memory_search for reviewed project knowledge, decision_search for rationale, and host-native tools for code."
    if knowledge_audit:
        expansion = "Knowledge audit: use compact inventory first; expand only concrete cards/gaps and verify with host-native source tools."
    elif mode == "continuation":
        expansion = "Continuation: restore the latest WorkSession first; do not use generic continuation text as a memory_search query."
    return {
        "mode": budget_mode,
        "budgeted_content_target_chars": total_target_chars,
        "policy_soft_target_chars": policy_soft_target_chars,
        "policy_chars": len(policy_text),
        "policy_over_soft_target": len(policy_text) > policy_soft_target_chars,
        "automatic_skill_chars": 0,
        "raw_source_memory_chars": 0,
        "knowledge_chars": len(
            json.dumps(materials["knowledge"], ensure_ascii=False, sort_keys=True)
        ),
        "knowledge_inventory_chars": len(
            json.dumps(materials["inventory"], ensure_ascii=False, sort_keys=True)
        ),
        "history_chars": len(json.dumps(materials["history"], ensure_ascii=False, sort_keys=True)),
        "decision_brief_chars": len(
            json.dumps(materials["decisions"], ensure_ascii=False, sort_keys=True)
        ),
        "scanner_evidence_chars": len(
            json.dumps(materials["scanner_evidence"], ensure_ascii=False, sort_keys=True)
        ),
        "expansion": expansion,
    }
