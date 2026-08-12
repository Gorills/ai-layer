from __future__ import annotations

from typing import Any

PROJECT_MAP_CONTRACT_VERSION = 1


def project_map_capability_contract(*, source_task_key: str | None = None) -> dict[str, Any]:
    """Host-neutral contract explaining how Project Map is read and reconciled.

    The contract is intentionally static and versioned so old Tasks/Epics can learn the current
    capability at navigation time instead of depending on the wording stored when they were created.
    """
    update_call: dict[str, Any] = {
        "tool": "project_map_reconcile",
        "required": ["scope_paths"],
        "optional": ["entries", "remove_paths", "no_changes_reason", "source_task_key"],
        "entry_fields": [
            "path",
            "purpose",
            "responsibilities",
            "domain_terms",
            "important_symbols",
            "related_files",
            "related_tests",
            "navigation_hints",
        ],
    }
    if source_task_key:
        update_call["source_task_key"] = source_task_key
        update_call["required"] = ["scope_paths", "source_task_key"]

    return {
        "version": PROJECT_MAP_CONTRACT_VERSION,
        "name": "Project Map",
        "purpose": (
            "Reusable navigation metadata answering WHERE relevant code lives and how inspected areas relate. "
            "It is not source truth and is separate from reviewed Project Knowledge."
        ),
        "read": {
            "tool": "project_search",
            "when": "Use when the relevant code location is unknown or when reviewing existing map coverage.",
        },
        "update": {
            **update_call,
            "when": (
                "Use after meaningful work established better navigation facts, when the user explicitly asks "
                "to update/review Project Map, or when Epic closure requires ProjectMapReconciled evidence."
            ),
            "rules": [
                "Reconcile only paths actually inspected or affected; do not rescan unrelated areas for ceremony.",
                "Scanner-owned paths/symbol structure cannot be overwritten by the agent.",
                "Canonical purpose/responsibilities/navigation_hints are concise English.",
                "Keep source identifiers exact; useful Russian/other wording belongs in domain_terms.",
                "If checked navigation is already accurate, use no_changes_reason instead of inventing entries.",
            ],
        },
        "source_of_truth": "Current repository source via host-native tools.",
        "do_not": [
            "grep repository documentation to discover what Project Map means",
            "create repository documentation just to describe Project Map",
            "invent semantic entries without current-source evidence",
        ],
    }


def project_map_bootstrap_line() -> str:
    return (
        "Project Map: `project_search` reads reusable navigation breadcrumbs; `project_map_reconcile` updates "
        "only semantic breadcrumbs actually established from current source. Use reconciliation after meaningful "
        "work or when the user explicitly asks to update/review the map. For Epic closure pass the completed "
        "Task key as `source_task_key` and a non-empty checked `scope_paths`; if the map is already accurate, "
        "record `no_changes_reason` instead of inventing entries."
    )
