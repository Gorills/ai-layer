from __future__ import annotations

from typing import Any

AGENT_RUNTIME_CONTRACT_VERSION = 1


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
        "navigation": {
            "known_location": "inspect current source directly with host-native tools",
            "unknown_location": "project_search",
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
                "when durable or strict managed execution is explicitly useful."
            ),
        },
        "legacy": {
            "memory_context": "compatibility_only",
            "memory_search": "alias_of_knowledge_search",
        },
        "precedence": [
            "higher-priority host/project policy",
            "current AI Layer runtime/tool contracts",
            "current repository source for code truth",
            "stored Task/Epic prose and historical documentation",
        ],
    }


def agent_runtime_bootstrap_line() -> str:
    return (
        f"AI Layer runtime contract v{AGENT_RUNTIME_CONTRACT_VERSION}: use `project_status` as the first "
        "registered-project state call; use `project_search` only when code location is unknown; read reviewed "
        "facts with `knowledge_search` and decisions with `decision_search`; update Project Map with "
        "`project_map_reconcile` only from inspected current-source scope. Normal execution remains host-native. "
        "A managed Task/Epic is not required for ordinary work; when one is active/selected, `task_next` or "
        "`epic_next` is the live procedure and overrides older stored workflow prose. `memory_context` is legacy "
        "compatibility only and `memory_search` is an alias of `knowledge_search`."
    )
