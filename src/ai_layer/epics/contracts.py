from __future__ import annotations

import re
from typing import Any

EPIC_OPEN_STATUSES = {
    "draft",
    "approved",
    "phase0",
    "planning",
    "running",
    "final_review",
    "blocked",
}
EPIC_EXECUTION_STATUSES = {"phase0", "planning", "running", "final_review", "blocked"}
EPIC_TERMINAL_STATUSES = {"completed", "archived", "cancelled"}
PLAN_ITEM_KINDS = {"phase0", "work", "final"}
PLAN_ITEM_STATUSES = {"pending", "active", "completed", "blocked", "cancelled"}
MAX_EPIC_SPEC_CHARS = 120_000
MAX_EPIC_TITLE_CHARS = 240
MAX_EPIC_PLAN_ITEMS = 60
MAX_EPIC_AUDIT_FINDINGS = 100

_REQUIRED_SPEC_HEADINGS = (
    "goal",
    "product outcome",
    "accepted decisions",
    "functional requirements",
    "acceptance criteria",
    "definition of done",
)

_INCOMPLETE_PATTERNS = (
    re.compile(r"\btemporary\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bstub\b", re.IGNORECASE),
    re.compile(r"\bfor now\b", re.IGNORECASE),
    re.compile(r"\blater we (?:can|will)\b", re.IGNORECASE),
    re.compile(r"\bpartial support\b", re.IGNORECASE),
    re.compile(r"\bhardcode(?:d)? until\b", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bвременно\b", re.IGNORECASE),
    re.compile(r"\bзаглуш", re.IGNORECASE),
    re.compile(r"\bпотом додела", re.IGNORECASE),
    re.compile(r"\bпока что\b", re.IGNORECASE),
)


def bounded_text(value: str | None, *, field: str, max_chars: int, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_chars:
        raise ValueError(f"{field} exceeds {max_chars} characters")
    return text


def epic_key(sequence: int) -> str:
    return f"E-{int(sequence):04d}"


def plan_item_key(ordinal: int) -> str:
    return f"P-{int(ordinal):03d}"


def spec_quality(markdown: str) -> dict[str, Any]:
    text = bounded_text(markdown, field="epic spec", max_chars=MAX_EPIC_SPEC_CHARS)
    lowered = text.casefold()
    missing = [heading for heading in _REQUIRED_SPEC_HEADINGS if heading not in lowered]
    warnings: list[str] = []
    for pattern in _INCOMPLETE_PATTERNS:
        if pattern.search(text):
            warnings.append(
                "Spec contains language that may hide a temporary/incomplete solution; Phase 0 must "
                "prove it is only a scope boundary, not deferred structural debt."
            )
            break
    return {
        "chars": len(text),
        "missing_recommended_sections": missing,
        "completeness_warnings": warnings,
        "ready_for_human_review": not missing,
    }


def phase0_contract(epic: dict) -> dict[str, Any]:
    return {
        "role": "epic_phase0_reviewer",
        "repository_mutation": "forbidden",
        "purpose": "reconcile the approved Epic specification with current source before implementation",
        "mandatory_checks": [
            "Treat current repository source as authoritative and verify every material architectural assumption.",
            "Detect stale facts, already-implemented capabilities, incompatible contracts, and missing constraints.",
            "Search for silent shortcuts: temporary, trial, placeholder, stub, partial, knowingly incomplete, or solutions that require later replacement inside the chosen MVP scope.",
            "MVP may limit scope, but every selected-scope solution must be production-quality and final for that scope.",
            "For non-branching corrections, update the execution spec without human interruption.",
            "For multiple options with one clearly superior durable recommendation, choose it, record rationale, and update the execution spec without human interruption.",
            "Stop for the human only when a material product/architecture trade-off remains genuinely unresolved.",
            "Do not create implementation Tasks yet; propose decomposition only after the spec is reconciled.",
        ],
        "epic": epic.get("key"),
        "spec_version": epic.get("approved_spec_version"),
    }


def final_task_contract(epic_key_value: str, spec_version: int) -> tuple[str, list[str], list[str]]:
    goal = (
        f"Finalize Epic {epic_key_value}: first reconcile project documentation and Project Knowledge with "
        f"the actually implemented product, then perform an independent full-Epic review against execution "
        f"spec v{spec_version}. The review scope is the whole Epic and relevant repository state, not only "
        "the documentation delta of this Task."
    )
    criteria = [
        "Relevant project documentation reflects the final implemented behavior and architecture; CURRENT_STATE.md is updated.",
        "At least one durable Project Knowledge card is drafted from current source evidence and the reviewer explicitly inspects the DRAFT cards before PASS.",
        "The independent reviewer verifies every Epic acceptance criterion and Definition of Done against current source and executable evidence where applicable.",
        "The reviewer checks integration across all Epic Tasks, regressions, migrations/compatibility, security/privacy, operational behavior, edge cases, dead code, TODOs, stubs, and incomplete/temporary solutions.",
        "Any actionable finding enters the existing FIX -> REVIEW loop; PASS is allowed only with no open findings and no material spec gap.",
    ]
    constraints = [
        f"Use epic_get for {epic_key_value} and execution spec v{spec_version}; do not rely on chat memory.",
        "IMPLEMENT may mutate only documentation/knowledge needed for closure unless a prior review finding explicitly requires code remediation.",
        "REVIEW is read-only and must inspect the whole Epic outcome, not merely files changed by this finalization Task.",
        "Do not mark a knowingly incomplete selected-scope solution as acceptable MVP.",
    ]
    return goal, criteria, constraints
