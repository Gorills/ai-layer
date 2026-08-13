from __future__ import annotations

from typing import Any

AGENT_RUNTIME_CONTRACT_VERSION = 2
PROJECT_SEARCH_MAX_QUERIES = 2


def agent_runtime_contract() -> dict[str, Any]:
    """Compact versioned contract for every agent-facing AI Layer surface.

    Stored Task/Epic prose and historical documentation can outlive the runtime that created them.
    This contract is therefore emitted dynamically and defines current procedure; current repository
    source remains authoritative for code truth.
    """
    return {
        "version": AGENT_RUNTIME_CONTRACT_VERSION,
        "architecture": "project_intelligence_control_plane",
        "execution_owner": "host-native agent runtime",
        "source_of_truth": "current repository source via host-native tools",
        "startup": {
            "tool": "project_status",
            "rule": "Use as the first AI Layer state call for registered-project work.",
        },
        "work": {
            "ordinary": "WorkItem records substantive user work; host-native execution remains the owner.",
            "begin": "work_begin",
            "checkpoint": "work_checkpoint only for meaningful milestones/blockers",
            "terminal": ["work_complete", "work_fail", "work_interrupt", "work_abandon"],
            "short_work_budget": "Normally work_begin + one terminal call; do not checkpoint every action.",
            "managed_task_relation": (
                "ManagedTask is optional assurance and may link to WorkItem; it is not the ordinary-work record."
            ),
        },
        "navigation": {
            "known_location": "inspect current source directly with host-native tools",
            "unknown_location": "project_search",
        },
        "search": {
            "max_queries": PROJECT_SEARCH_MAX_QUERIES,
            "primary": (
                "For non-English natural-language goals, derive one concise English code-centric retrieval "
                "query; never use raw user prose as the only query."
            ),
            "identifiers": (
                "Preserve exact paths, symbols, routes, config/env keys, error strings, tables and fields verbatim."
            ),
            "secondary": (
                "Use at most one original-language or mixed variant when domain aliases or weak first-pass "
                "coverage justify widening."
            ),
            "flow_completeness": (
                "For end-to-end flows cover entrypoint/handler, core service/domain, persistence/external "
                "integration and relevant tests before claiming the flow is understood."
            ),
            "degraded_semantics": (
                "When semantic search is degraded or results are implausible, use English code-centric terms "
                "then one bounded native exact-token search."
            ),
            "verification": "Project Map results are breadcrumbs; open current source before claims or edits.",
        },
        "project_policy": {
            "surface": "project_status.project_policy",
            "rule": "Apply bounded policy text and use version/hash to detect policy drift.",
        },
        "project_map": {
            "read": "project_search",
            "update": "project_map_reconcile",
        },
        "knowledge": {
            "read": "knowledge_search",
            "write": "review-gated managed Task flow only",
        },
        "decisions": {"read": "decision_search"},
        "skills": {
            "routing_owner": "host-native",
            "explicit_fallback": "skill_get",
        },
        "managed_work": {
            "task_resume": "task_next",
            "epic_resume": "epic_next",
            "idle": (
                "No managed Task/Epic is required for ordinary host-native work; create/select one only "
                "when durable strict assurance is explicitly useful."
            ),
        },
        "legacy": {
            "memory_context": "compatibility_only",
            "memory_search": "alias_of_knowledge_search",
            "work_sessions": "legacy_completed_work_handoff",
        },
        "precedence": [
            "higher-priority host/user policy",
            "project_status.project_policy",
            "current AI Layer runtime/tool contracts",
            "current repository source for code truth",
            "stored Task/Epic prose and historical documentation",
        ],
    }


def agent_runtime_bootstrap_line() -> str:
    return (
        f"AI Layer runtime contract v{AGENT_RUNTIME_CONTRACT_VERSION}: use `project_status` as the first "
        "registered-project state call and apply its `project_policy`. Record substantive ordinary work with "
        "`work_begin` and one terminal Work call; use `work_checkpoint` only for meaningful milestones or "
        "blockers. A managed Task is optional assurance, not the ordinary-work record. If code location is "
        "unknown, use `project_search`; for non-English goals make the primary retrieval query concise English "
        "and code-centric while preserving exact identifiers, with at most one original/mixed widening variant. "
        "Project Map hits are breadcrumbs, so verify current source. Read reviewed facts with `knowledge_search` "
        "and decisions with `decision_search`. Normal execution remains host-native. When a managed Task/Epic "
        "is active/selected, `task_next` or `epic_next` is the live strict procedure and overrides older stored "
        "workflow prose. `memory_context` is legacy compatibility only and `memory_search` aliases "
        "`knowledge_search`."
    )
