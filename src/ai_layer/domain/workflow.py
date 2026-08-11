from __future__ import annotations

from dataclasses import dataclass

from ai_layer.domain.security import Capability


@dataclass(frozen=True, slots=True)
class StageDefinition:
    kind: str
    role: str
    readonly: bool
    mutating: bool
    completion_contract: str
    required_capabilities: frozenset[str]
    allowed_outcomes: frozenset[str]
    possible_next: frozenset[str]


STAGE_DEFINITIONS: dict[str, StageDefinition] = {
    "discovery": StageDefinition(
        kind="discovery",
        role="discovery",
        readonly=True,
        mutating=False,
        completion_contract="discovery_result",
        required_capabilities=frozenset({Capability.TASK_READ, Capability.WORKSPACE_READ}),
        allowed_outcomes=frozenset(
            {"ready_for_implementation", "analysis_complete", "no_change_needed", "blocked"}
        ),
        possible_next=frozenset({"implement"}),
    ),
    "implement": StageDefinition(
        kind="implement",
        role="implementer",
        readonly=False,
        mutating=True,
        completion_contract="implementation_result",
        required_capabilities=frozenset({Capability.TASK_START, Capability.FILE_MODIFY}),
        allowed_outcomes=frozenset({"done", "completed", "blocked"}),
        possible_next=frozenset({"review"}),
    ),
    "review": StageDefinition(
        kind="review",
        role="reviewer",
        readonly=True,
        mutating=False,
        completion_contract="review_verdict",
        required_capabilities=frozenset({Capability.TASK_READ, Capability.WORKSPACE_READ}),
        allowed_outcomes=frozenset({"pass", "changes_required", "blocked"}),
        possible_next=frozenset({"fix"}),
    ),
    "fix": StageDefinition(
        kind="fix",
        role="fixer",
        readonly=False,
        mutating=True,
        completion_contract="fix_result",
        required_capabilities=frozenset({Capability.TASK_START, Capability.FILE_MODIFY}),
        allowed_outcomes=frozenset({"done", "completed", "no_changes_needed", "blocked"}),
        possible_next=frozenset({"review"}),
    ),
}


def stage_definition(kind: str) -> StageDefinition:
    try:
        return STAGE_DEFINITIONS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported workflow stage: {kind}") from exc


def validate_workflow_registry() -> list[str]:
    errors: list[str] = []
    for kind, definition in STAGE_DEFINITIONS.items():
        if definition.kind != kind:
            errors.append(f"{kind}: registry key does not match definition.kind")
        if definition.readonly == definition.mutating:
            errors.append(f"{kind}: stage must be exactly one of read-only or mutating")
        if not definition.role:
            errors.append(f"{kind}: role is required")
        if not definition.completion_contract:
            errors.append(f"{kind}: completion contract is required")
        if not definition.required_capabilities:
            errors.append(f"{kind}: at least one capability is required")
        if not definition.allowed_outcomes:
            errors.append(f"{kind}: allowed outcomes are required")
        unknown = definition.possible_next - set(STAGE_DEFINITIONS)
        if unknown:
            errors.append(f"{kind}: unknown next stage(s): {sorted(unknown)}")
    return errors
