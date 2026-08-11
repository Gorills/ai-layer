from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.core.request_context import interactive_request
from ai_layer.db.models import Decision, Project
from ai_layer.memory.freshness import ensure_memory_fresh
from ai_layer.memory.guidance import build_tool_guidance
from ai_layer.memory.history import (
    knowledge_audit_history,
    latest_task_summary,
    relevant_decision_brief,
    relevant_task_history,
)
from ai_layer.memory.knowledge_store import (
    knowledge_status,
    list_knowledge,
    relevant_source_pointers,
    search_knowledge,
)
from ai_layer.memory.presentation import (
    build_task_brief,
    compact_audit_guidance,
    compact_audit_runtime,
    compact_audit_scanner_evidence,
    compact_continuation_guidance,
    compact_continuation_runtime,
    compact_inventory,
    compact_task_runtime,
    context_budget,
    context_mode,
    present_scanner_evidence,
    scanner_snapshot_current,
)
from ai_layer.memory.refresh_runtime import interactive_freshness
from ai_layer.policy.service import RESPONSE_CONTRACT, dynamic_policy
from ai_layer.sessions.service import snapshot_decisions
from ai_layer.skills.profile import detect_project_profile

MIN_DECISION_SCORE = 0.18
MEMORY_CONTEXT_TOTAL_CHAR_BUDGET = 18_000
MEMORY_CONTEXT_POLICY_CHAR_BUDGET = 3_000
MEMORY_CONTEXT_MEMORY_CHAR_BUDGET = 4_000

# Compatibility injection hook for callers/tests that historically patched memory.service.task_runtime_state.
task_runtime_state = None


def _freshness_for_request(db: Session, project: Project) -> dict:
    if interactive_request():
        return interactive_freshness(project)
    return ensure_memory_fresh(db, project)


def _search_memory(db: Session, project: Project, query: str, limit: int = 8) -> list[dict]:
    """Compatibility name: search only review-gated project knowledge, never current source chunks."""
    return search_knowledge(db, project, query, status="VERIFIED", limit=limit)


def memory_search(db: Session, project: Project, query: str, limit: int = 8) -> list[dict]:
    freshness = _freshness_for_request(db, project)
    if freshness.get("status") == "initializing" and not freshness.get("snapshot_available"):
        raise RuntimeError(
            "AI_LAYER_MEMORY_INITIALIZING: deterministic repository evidence is not ready yet. "
            "Use current repository source or run `ai-layer scan`, then retry."
        )
    return _search_memory(db, project, query, limit)


def decision_search(db: Session, project: Project, query: str, limit: int = 8) -> list[dict]:
    """Search only durable decision history; repository/source evidence is intentionally excluded."""
    from ai_layer.memory.embeddings import get_embedder

    vector = get_embedder().embed([query])[0]
    candidate_limit = max(limit * 6, 30)
    stmt = (
        select(Decision, Decision.embedding.cosine_distance(vector).label("distance"))
        .where(Decision.project_id == project.id)
        .order_by("distance")
        .limit(candidate_limit)
    )
    candidates: list[dict] = []
    explicit_text: set[str] = set()
    for decision, distance in db.execute(stmt).all():
        score = max(0.0, 1.0 - float(distance if distance is not None else 1.0))
        if score < MIN_DECISION_SCORE:
            continue
        explicit_text.add(decision.decision.casefold())
        candidates.append(
            {
                "kind": "decision",
                "id": str(decision.id),
                "title": decision.title,
                "context": decision.context,
                "decision": decision.decision,
                "rationale": decision.rationale,
                "score": round(score, 4),
            }
        )

    q_tokens = {token for token in query.casefold().split() if len(token) >= 3}
    for item in snapshot_decisions(project, limit=candidate_limit):
        decision_text = item["decision"]
        if decision_text.casefold() in explicit_text:
            continue
        hay = f"{decision_text} {item.get('context', '')}".casefold()
        overlap = sum(1 for token in q_tokens if token in hay)
        if q_tokens and overlap == 0:
            continue
        score = min(0.78, 0.30 + overlap * 0.08)
        if score < MIN_DECISION_SCORE:
            continue
        candidates.append(
            {
                "kind": "session_decision",
                "id": f"session:{item['session_id']}",
                "title": decision_text[:120],
                "context": item.get("context", ""),
                "decision": decision_text,
                "rationale": "Recovered from a committed durable session handoff snapshot.",
                "score": round(score, 4),
                "session_id": item["session_id"],
            }
        )

    candidates.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    result: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item.get("decision") or item.get("id")).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _compact_context_hits(
    memory: list[dict],
    max_chars: int | None = None,
    total_chars: int = MEMORY_CONTEXT_MEMORY_CHAR_BUDGET,
) -> list[dict]:
    """Bound curated cards without source excerpts or transport-side truncation."""
    result: list[dict] = []
    remaining = max(0, total_chars)
    per_item = max_chars or 1600
    for item in memory:
        copy = dict(item)
        copy.pop("evidence", None)
        encoded = json.dumps(copy, ensure_ascii=False, sort_keys=True)
        if len(encoded) > per_item:
            copy["claims"] = list(copy.get("claims") or [])[:6]
            copy["constraints"] = list(copy.get("constraints") or [])[:4]
            copy["source_pointers"] = list(copy.get("source_pointers") or [])[:10]
            encoded = json.dumps(copy, ensure_ascii=False, sort_keys=True)
        if len(encoded) > remaining:
            break
        result.append(copy)
        remaining -= len(encoded)
    return result


def _compact_scanner_evidence(intelligence: dict) -> dict:
    """Expose navigation facts, not scanner-authored architecture claims."""
    stack = intelligence.get("stack") or {}
    runtime = intelligence.get("runtime") or {}
    data = intelligence.get("data") or {}
    testing = intelligence.get("testing") or {}
    docs = intelligence.get("documentation") or {}
    return {
        "assurance": "AI_LAYER_OBSERVED scanner evidence only; not reviewed project knowledge.",
        "languages": list(stack.get("languages") or [])[:10],
        "framework_candidates": list(stack.get("frameworks") or [])[:10],
        "manifests": list(stack.get("manifests") or [])[:12],
        "entrypoint_candidates": list(runtime.get("entrypoints") or [])[:12],
        "databases": list(data.get("databases") or [])[:8],
        "caches": list(data.get("caches") or [])[:8],
        "test_files": int(testing.get("test_files") or 0),
        "test_frameworks": list(testing.get("frameworks") or [])[:8],
        "documentation_domains": sorted((docs.get("domains") or {}).keys())[:12],
    }


def _freshness_paths(freshness: dict) -> list[str]:
    direct = list(freshness.get("changed_paths") or [])
    changes = freshness.get("changes") or {}
    direct.extend(list(changes.get("added") or []))
    direct.extend(list(changes.get("modified") or []))
    direct.extend(list(changes.get("deleted") or []))
    result: list[str] = []
    for raw in direct:
        path = str(raw or "").strip().replace("\\", "/")
        if path and path not in result:
            result.append(path)
    return result


def _compact_freshness(freshness: dict, source_pointers: list[str]) -> dict:
    changed = _freshness_paths(freshness)
    relevant = [path for path in changed if path in set(source_pointers)]
    return {
        "status": freshness.get("status"),
        "refreshed": bool(freshness.get("refreshed")),
        "snapshot_available": freshness.get("snapshot_available"),
        "changed_path_count": len(changed),
        "relevant_changed_paths": relevant[:12],
        "background_refresh": freshness.get("background_refresh"),
        "refresh_job": freshness.get("refresh_job"),
        "read_contract": freshness.get("read_contract")
        or (
            "Current repository source is authoritative. Verified knowledge is invalidated when its supporting evidence changes."
        ),
    }


def _audit_materials(
    db: Session, project: Project, knowledge_state: dict, intelligence: dict
) -> dict:
    verified = (
        list_knowledge(db, project, status="VERIFIED", limit=200)
        if knowledge_state["verified"]
        else []
    )
    stale = (
        list_knowledge(db, project, status="STALE", limit=200) if knowledge_state["stale"] else []
    )
    return {
        "knowledge": [],
        "stale": [],
        "inventory": compact_inventory(verified),
        "stale_inventory": compact_inventory(stale),
        "history": knowledge_audit_history(db, project, limit=4),
        "decisions": [],
        "source_pointers": [],
        "scanner_evidence": compact_audit_scanner_evidence(intelligence),
        "inventory_complete": len(verified) == int(knowledge_state.get("verified") or 0),
    }


def _continuation_materials(db: Session, project: Project, intelligence: dict) -> dict:
    recent = latest_task_summary(db, project)
    return {
        "knowledge": [],
        "stale": [],
        "inventory": [],
        "stale_inventory": [],
        "history": [recent] if recent else [],
        "decisions": [],
        "source_pointers": [],
        "scanner_evidence": _compact_scanner_evidence(intelligence),
        "inventory_complete": False,
    }


def _task_materials(
    db: Session, project: Project, task: str, limit: int, knowledge_state: dict, intelligence: dict
) -> dict:
    knowledge = (
        _compact_context_hits(_search_memory(db, project, task, limit=limit))
        if knowledge_state["verified"]
        else []
    )
    stale = (
        _compact_context_hits(
            search_knowledge(db, project, task, status="STALE", limit=2), total_chars=1600
        )
        if knowledge_state["stale"]
        else []
    )
    return {
        "knowledge": knowledge,
        "stale": stale,
        "inventory": [],
        "stale_inventory": [],
        "history": relevant_task_history(db, project, task, limit=3),
        "decisions": relevant_decision_brief(db, project, task, limit=2),
        "source_pointers": relevant_source_pointers([*knowledge, *stale]),
        "scanner_evidence": _compact_scanner_evidence(intelligence),
        "inventory_complete": False,
    }


def _runtime_for_context(
    db: Session, project: Project, provided: dict | None, *, mode: str
) -> tuple[dict, dict]:
    full = (
        provided
        if provided is not None
        else (
            task_runtime_state(db, project)
            if callable(task_runtime_state)
            else {"active": False, "next_action": {"action": "create_task", "tool": "task_create"}}
        )
    )
    if mode.startswith("knowledge_"):
        return full, compact_audit_runtime(full)
    if mode == "continuation":
        return full, compact_continuation_runtime(full)
    return full, compact_task_runtime(full)


def _guidance_for_context(
    task: str,
    project: Project,
    mode: str,
    runtime_full: dict,
    runtime: dict,
    knowledge_state: dict,
    materials: dict,
) -> dict:
    if mode.startswith("knowledge_"):
        return compact_audit_guidance(
            project.root_path, mode, runtime, inventory_complete=materials["inventory_complete"]
        )
    if mode == "continuation":
        return compact_continuation_guidance(project.root_path, runtime)
    guidance = build_tool_guidance(task, project.root_path, materials["knowledge"])
    if runtime.get("active"):
        guidance["recommended_calls"] = [
            call
            for call in guidance.get("recommended_calls", [])
            if call.get("tool") != "session_restore"
        ]
    guidance["next_task_action"] = (runtime.get("task") or runtime).get("next_action")
    if knowledge_state["onboarding_recommended"]:
        guidance["knowledge_onboarding"] = {
            "status": "missing_verified_baseline",
            "auto_create": False,
        }
    return guidance


def memory_context(
    db: Session, project: Project, task: str, limit: int = 4, *, task_runtime: dict | None = None
) -> dict:
    """Return the smallest Project Knowledge presentation appropriate for the current task type."""
    mode = context_mode(task)
    knowledge_audit = mode.startswith("knowledge_")
    raw_freshness = _freshness_for_request(db, project)
    state = knowledge_status(db, project)
    intelligence = getattr(project, "project_intelligence", None) or {}
    if knowledge_audit:
        materials = _audit_materials(db, project, state, intelligence)
    elif mode == "continuation":
        materials = _continuation_materials(db, project, intelligence)
    else:
        materials = _task_materials(db, project, task, limit, state, intelligence)
    materials["scanner_evidence"] = present_scanner_evidence(
        materials["scanner_evidence"], raw_freshness, mode=mode
    )
    runtime_full, runtime = _runtime_for_context(db, project, task_runtime, mode=mode)
    guidance = _guidance_for_context(task, project, mode, runtime_full, runtime, state, materials)
    policy_text = dynamic_policy(project.root_path, read_only=knowledge_audit)
    profile = (
        detect_project_profile(project.languages or {}, project.dependencies or {})
        if scanner_snapshot_current(raw_freshness) and mode != "continuation"
        else {
            "available": False,
            "reason": (
                "continuation_mode_uses_session_history_and_current_source"
                if mode == "continuation"
                else "scanner_snapshot_not_current"
            ),
        }
    )
    payload = {
        "project": {
            "name": project.name,
            "root_path": project.root_path,
            "profile": profile,
        },
        "knowledge_state": state,
        "task_brief": build_task_brief(mode, materials),
        "scanner_evidence": materials["scanner_evidence"],
        "freshness": _compact_freshness(raw_freshness, materials["source_pointers"]),
        "skill_access": {
            "routing_owner": "host-native",
            "authoritative_store": "ai-layer",
            "retrieval_tool": "skill_get",
            "automatic_domain_skill_injection": False,
        },
        "policy": policy_text,
        "policy_truncated": False,
        "response_contract": RESPONSE_CONTRACT,
        "task_runtime": runtime,
        "tool_guidance": guidance,
    }
    if materials["scanner_evidence"].get("available") is False:
        payload["freshness"]["scanner_evidence_withheld"] = True
    payload["context_budget"] = context_budget(
        mode,
        policy_text,
        materials,
        total_target_chars=MEMORY_CONTEXT_TOTAL_CHAR_BUDGET,
        policy_soft_target_chars=MEMORY_CONTEXT_POLICY_CHAR_BUDGET,
    )
    return payload
