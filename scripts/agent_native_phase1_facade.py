#!/usr/bin/env python3
"""Executable Phase 1 prototype for the future agent-facing façade contract.

Repository tooling only: this module is not imported by product runtime and does not register MCP
tools. It freezes a small public contract while the current MCP catalogue remains authoritative.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Required, TypedDict

CONTRACT_VERSION = 1
TOKEN_VERSION = "act1"
FACADE_CATALOG_MAX_BYTES = 7 * 1024
FACADE_RESPONSE_MAX_BYTES = 8 * 1024
FACADE_ACTION_RESPONSE_MAX_BYTES = 4 * 1024

PUBLIC_TOOLS = ("project_enter", "project_lookup", "work_continue", "work_finish")
PUBLIC_ACTIONS = ("native_engineering", "run_worker", "human_decision", "done")
FORBIDDEN_PUBLIC_FSM_TERMS = (
    "task_next",
    "task_stage_delegate",
    "task_stage_complete",
    "epic_next",
    "TaskStage",
)

Intent = Literal["start", "resume"]
Assurance = Literal["native", "reviewed"]
ActionKind = Literal["native_engineering", "run_worker", "human_decision", "done"]
WorkerKind = Literal["change", "independent_check", "correction"]
InternalDirective = Literal[
    "host_native",
    "worker_change",
    "worker_check",
    "worker_correction",
    "decision",
    "complete",
]
SubmissionDisposition = Literal[
    "advance",
    "idempotent_replay",
    "idempotency_conflict",
    "stale_action",
    "invalid_action_token",
]


class PublicProject(TypedDict):
    key: str


class PublicWork(TypedDict):
    key: str
    goal: str | None
    assurance: Assurance
    epic_attached: bool


class PublicNextAction(TypedDict, total=False):
    kind: Required[ActionKind]
    action_token: Required[str | None]
    state_version: Required[int]
    instruction: Required[str]
    worker_kind: WorkerKind
    choices: list[str]


class FacadeResponse(TypedDict):
    contract_version: int
    project: PublicProject
    work: PublicWork | None
    next_action: PublicNextAction


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def serialized_bytes(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8"))


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _string(*, max_length: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if max_length is not None:
        schema["maxLength"] = max_length
    return schema


TOKEN_SCHEMA = {"type": "string", "pattern": r"^act1_[A-Za-z0-9_-]{43}$"}

REPORT_SCHEMA = _object(
    {
        "kind": {
            "type": "string",
            "enum": [
                "native_result",
                "worker_result",
                "human_choice",
                "assurance_request",
            ],
        },
        "summary": _string(max_length=2000),
        "outcome": {
            "type": "string",
            "enum": [
                "completed",
                "blocked",
                "changes_required",
                "pass",
                "selected",
                "escalate",
            ],
        },
        "selection": _string(),
        "evidence": {
            "type": "array",
            "items": _string(max_length=500),
            "maxItems": 12,
        },
    },
    ["kind", "summary"],
)

WORK_SCHEMA = _object(
    {
        "key": _string(),
        "goal": {"anyOf": [_string(max_length=2000), {"type": "null"}]},
        "assurance": {"type": "string", "enum": ["native", "reviewed"]},
        "epic_attached": {"type": "boolean"},
    },
    ["key", "goal", "assurance", "epic_attached"],
)

NEXT_ACTION_SCHEMA = _object(
    {
        "kind": {"type": "string", "enum": list(PUBLIC_ACTIONS)},
        "action_token": {"anyOf": [TOKEN_SCHEMA, {"type": "null"}]},
        "state_version": {"type": "integer", "minimum": 1},
        "instruction": _string(max_length=2000),
        "worker_kind": {
            "type": "string",
            "enum": ["change", "independent_check", "correction"],
        },
        "choices": {"type": "array", "items": _string(max_length=100), "maxItems": 8},
    },
    ["kind", "action_token", "state_version", "instruction"],
)

ACTION_RESPONSE_SCHEMA = _object(
    {
        "contract_version": {"type": "integer", "const": CONTRACT_VERSION},
        "project": _object({"key": _string()}, ["key"]),
        "work": {"anyOf": [WORK_SCHEMA, {"type": "null"}]},
        "next_action": NEXT_ACTION_SCHEMA,
    },
    ["contract_version", "project", "work", "next_action"],
)

LOOKUP_RESPONSE_SCHEMA = _object(
    {
        "contract_version": {"type": "integer", "const": CONTRACT_VERSION},
        "query": _string(max_length=1000),
        "breadcrumbs": {
            "type": "array",
            "maxItems": 8,
            "items": _object(
                {
                    "path": _string(max_length=500),
                    "kind": {
                        "type": "string",
                        "enum": ["source", "test", "knowledge", "decision"],
                    },
                    "reason": _string(max_length=1000),
                },
                ["path", "kind", "reason"],
            ),
        },
        "source_truth_required": {"type": "boolean", "const": True},
    },
    ["contract_version", "query", "breadcrumbs", "source_truth_required"],
)

TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "project_enter",
        "description": "Start or resume durable project work and return one public next action.",
        "inputSchema": _object(
            {
                "project_root": _string(),
                "intent": {"type": "string", "enum": ["start", "resume"]},
                "goal": _string(max_length=2000),
                "assurance": {
                    "type": "string",
                    "enum": ["native", "reviewed"],
                    "default": "native",
                },
                "work_key": _string(),
            },
            ["project_root", "intent"],
        ),
        "outputSchema": ACTION_RESPONSE_SCHEMA,
    },
    {
        "name": "project_lookup",
        "description": "Return bounded Project Intelligence breadcrumbs for unknown locations.",
        "inputSchema": _object(
            {
                "project_root": _string(),
                "query": _string(max_length=1000),
                "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
            },
            ["project_root", "query"],
        ),
        "outputSchema": LOOKUP_RESPONSE_SCHEMA,
    },
    {
        "name": "work_continue",
        "description": "Report the completed public action and request the next public action.",
        "inputSchema": _object(
            {"action_token": TOKEN_SCHEMA, "report": REPORT_SCHEMA},
            ["action_token", "report"],
        ),
        "outputSchema": ACTION_RESPONSE_SCHEMA,
    },
    {
        "name": "work_finish",
        "description": "Record the durable Work outcome after the server says it is done.",
        "inputSchema": _object(
            {
                "action_token": TOKEN_SCHEMA,
                "summary": _string(max_length=2000),
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed", "abandoned"],
                    "default": "completed",
                },
                "verification": {
                    "type": "array",
                    "items": _string(max_length=500),
                    "maxItems": 12,
                },
                "map_disposition": {
                    "type": "string",
                    "enum": [
                        "reconciled",
                        "checked_no_change",
                        "not_applicable",
                        "deferred",
                    ],
                },
            },
            ["action_token", "summary"],
        ),
        "outputSchema": ACTION_RESPONSE_SCHEMA,
    },
)


@dataclass(frozen=True, slots=True)
class ActionBinding:
    project_key: str
    work_key: str | None
    state_version: int
    action_kind: ActionKind


@dataclass(frozen=True, slots=True)
class EnterScenario:
    project_key: str
    intent: Intent
    goal: str | None
    assurance: Assurance
    active_work_keys: tuple[str, ...] = ()
    selected_work_key: str | None = None
    new_work_key: str | None = None
    state_version: int = 1
    current_directive: InternalDirective = "host_native"
    dirty_worktree: bool = False
    epic_attached: bool = False


def tool_definition(name: str) -> dict[str, Any]:
    for definition in TOOL_DEFINITIONS:
        if definition["name"] == name:
            return definition
    raise KeyError(name)


def _matches_top_level_schema(arguments: Mapping[str, Any], schema: Mapping[str, Any]) -> bool:
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        return False
    if schema.get("additionalProperties") is False and not set(arguments).issubset(properties):
        return False
    return all(name in arguments for name in required)


def matching_tools(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(definition["name"])
        for definition in TOOL_DEFINITIONS
        if _matches_top_level_schema(arguments, definition["inputSchema"])
    )


def validate_tool_arguments(name: str, arguments: Mapping[str, Any]) -> tuple[str, ...]:
    schema = tool_definition(name)["inputSchema"]
    if not _matches_top_level_schema(arguments, schema):
        return ("top_level_shape",)

    errors: list[str] = []
    if name == "project_enter":
        intent = arguments.get("intent")
        goal = arguments.get("goal")
        work_key = arguments.get("work_key")
        if intent == "start" and not isinstance(goal, str):
            errors.append("start_requires_goal")
        if intent == "start" and work_key is not None:
            errors.append("start_rejects_work_key")
        if intent == "resume" and goal is not None:
            errors.append("resume_rejects_goal")
    elif name in {"work_continue", "work_finish"}:
        token = arguments.get("action_token")
        if not isinstance(token, str) or not action_token_shape_valid(token):
            errors.append("invalid_action_token")
    return tuple(errors)


def issue_action_token(binding: ActionBinding, *, secret: bytes) -> str:
    if not secret:
        raise ValueError("secret must not be empty")
    if binding.state_version < 1:
        raise ValueError("state_version must be positive")
    payload = canonical_json(asdict(binding)).encode("utf-8")
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{TOKEN_VERSION}_{encoded}"


def action_token_shape_valid(token: str) -> bool:
    return bool(re.fullmatch(r"act1_[A-Za-z0-9_-]{43}", token))


def report_fingerprint(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()


def classify_submission(
    *,
    current_token: str,
    consumed_reports: Mapping[str, str],
    submitted_token: str,
    report: Mapping[str, Any],
) -> SubmissionDisposition:
    if not action_token_shape_valid(submitted_token):
        return "invalid_action_token"
    fingerprint = report_fingerprint(report)
    consumed = consumed_reports.get(submitted_token)
    if consumed is not None:
        return "idempotent_replay" if consumed == fingerprint else "idempotency_conflict"
    return "advance" if submitted_token == current_token else "stale_action"


def promotion_strategy(*, dirty_worktree: bool) -> str:
    return "dirty_baseline_adopt" if dirty_worktree else "fresh_managed_attachment"


def _directive_to_action(directive: InternalDirective) -> tuple[ActionKind, WorkerKind | None]:
    mapping: dict[InternalDirective, tuple[ActionKind, WorkerKind | None]] = {
        "host_native": ("native_engineering", None),
        "worker_change": ("run_worker", "change"),
        "worker_check": ("run_worker", "independent_check"),
        "worker_correction": ("run_worker", "correction"),
        "decision": ("human_decision", None),
        "complete": ("done", None),
    }
    return mapping[directive]


def make_next_action(
    *,
    project_key: str,
    work_key: str | None,
    state_version: int,
    directive: InternalDirective,
    secret: bytes,
    instruction: str,
    choices: tuple[str, ...] = (),
) -> PublicNextAction:
    kind, worker_kind = _directive_to_action(directive)
    binding = ActionBinding(project_key, work_key, state_version, kind)
    action: PublicNextAction = {
        "kind": kind,
        "action_token": issue_action_token(binding, secret=secret),
        "state_version": state_version,
        "instruction": instruction,
    }
    if worker_kind is not None:
        action["worker_kind"] = worker_kind
    if choices:
        action["choices"] = list(choices)
    return action


def resolve_enter(scenario: EnterScenario, *, secret: bytes) -> FacadeResponse:
    if scenario.state_version < 1:
        raise ValueError("state_version must be positive")

    if scenario.intent == "start":
        if not scenario.goal or not scenario.new_work_key:
            raise ValueError("start requires goal and server-supplied new_work_key")
        work_key = scenario.new_work_key
        directive: InternalDirective = (
            "worker_change" if scenario.assurance == "reviewed" else "host_native"
        )
        instruction = (
            "Run the reviewed change worker."
            if directive == "worker_change"
            else "Use native repository tools to implement and verify the requested change."
        )
    else:
        candidates = scenario.active_work_keys
        if scenario.selected_work_key is not None:
            if scenario.selected_work_key not in candidates:
                raise ValueError("selected_work_key is not active")
            work_key = scenario.selected_work_key
        elif len(candidates) == 1:
            work_key = candidates[0]
        elif len(candidates) > 1:
            work_key = candidates[0]
            return _enter_response(
                scenario,
                work_key=None,
                action=make_next_action(
                    project_key=scenario.project_key,
                    work_key=None,
                    state_version=scenario.state_version,
                    directive="decision",
                    secret=secret,
                    instruction="Choose which active Work to resume.",
                    choices=candidates,
                ),
            )
        else:
            return _enter_response(
                scenario,
                work_key=None,
                action={
                    "kind": "done",
                    "action_token": None,
                    "state_version": scenario.state_version,
                    "instruction": "No active Work exists to resume.",
                },
            )
        directive = scenario.current_directive
        instruction = "Resume the server-selected action for this Work."

    response = _enter_response(
        scenario,
        work_key=work_key,
        action=make_next_action(
            project_key=scenario.project_key,
            work_key=work_key,
            state_version=scenario.state_version,
            directive=directive,
            secret=secret,
            instruction=instruction,
        ),
    )
    return response


def _enter_response(
    scenario: EnterScenario,
    *,
    work_key: str | None,
    action: PublicNextAction,
) -> FacadeResponse:
    work: PublicWork | None = None
    if work_key is not None:
        work = {
            "key": work_key,
            "goal": scenario.goal,
            "assurance": scenario.assurance,
            "epic_attached": scenario.epic_attached,
        }
    return {
        "contract_version": CONTRACT_VERSION,
        "project": {"key": scenario.project_key},
        "work": work,
        "next_action": action,
    }


def _step(tool: str, action: ActionKind | None = None) -> dict[str, str]:
    return {"tool": tool, **({"returns": action} if action is not None else {})}


def build_target_journeys() -> dict[str, dict[str, Any]]:
    return {
        "A_short_ordinary_change": {
            "steps": [
                _step("project_enter", "native_engineering"),
                _step("project_lookup"),
                _step("work_finish", "done"),
            ],
            "invariants": {
                "lookup_optional": True,
                "managed_task_required": False,
            },
        },
        "B_long_ordinary_optional_review": {
            "steps": [
                _step("project_enter", "native_engineering"),
                _step("work_continue", "run_worker"),
                _step("work_continue", "run_worker"),
                _step("work_continue", "done"),
                _step("work_finish", "done"),
            ],
            "invariants": {"promotion_same_work": True},
        },
        "C_explicit_standard_change": {
            "steps": [
                _step("project_enter", "run_worker"),
                _step("work_continue", "run_worker"),
                _step("work_continue", "run_worker"),
                _step("work_continue", "done"),
                _step("work_finish", "done"),
            ],
            "invariants": {"managed_from_start": True},
        },
        "D_continue_after_restart": {
            "steps": [
                _step("project_enter", "native_engineering"),
                _step("work_finish", "done"),
            ],
            "invariants": {"resume_single_entrypoint": True},
        },
        "E_epic_continuation": {
            "steps": [
                _step("project_enter", "run_worker"),
                _step("work_continue", "run_worker"),
                _step("work_continue", "done"),
                _step("work_finish", "done"),
            ],
            "invariants": {
                "epic_attached_work": True,
                "internal_epic_navigation_hidden": True,
            },
        },
        "F_mid_native_escalation": {
            "steps": [
                _step("project_enter", "native_engineering"),
                _step("work_continue", "run_worker"),
                _step("work_continue", "done"),
                _step("work_finish", "done"),
            ],
            "invariants": {
                "same_work_before_after_escalation": True,
                "dirty_promotion_safe": True,
            },
        },
    }


def representative_responses(*, secret: bytes) -> dict[str, dict[str, Any]]:
    work: PublicWork = {
        "key": "W-0042",
        "goal": "Update request routing and verify it",
        "assurance": "native",
        "epic_attached": False,
    }
    return {
        "project_enter": resolve_enter(
            EnterScenario(
                project_key="demo",
                intent="start",
                goal=work["goal"],
                assurance=work["assurance"],
                new_work_key=work["key"],
            ),
            secret=secret,
        ),
        "project_lookup": {
            "contract_version": CONTRACT_VERSION,
            "query": "request routing",
            "breadcrumbs": [
                {
                    "path": "src/example/router.py",
                    "kind": "source",
                    "reason": "Likely entrypoint; inspect current source before editing.",
                },
                {
                    "path": "tests/test_router.py",
                    "kind": "test",
                    "reason": "Likely verification coverage for the routing behavior.",
                },
            ],
            "source_truth_required": True,
        },
        "work_continue": {
            "contract_version": CONTRACT_VERSION,
            "project": {"key": "demo"},
            "work": dict(work),
            "next_action": make_next_action(
                project_key="demo",
                work_key=work["key"],
                state_version=2,
                directive="worker_check",
                secret=secret,
                instruction="Run an independent check of the current Work delta.",
            ),
        },
        "work_finish": {
            "contract_version": CONTRACT_VERSION,
            "project": {"key": "demo"},
            "work": dict(work),
            "next_action": {
                "kind": "done",
                "action_token": None,
                "state_version": 3,
                "instruction": "Durable Work outcome recorded.",
            },
        },
    }


def build_contract_fixture() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "agent_native_phase1_prototype_only",
        "runtime": {
            "current_mcp_default_unchanged": True,
            "facade_registered": False,
            "installer_default_unchanged": True,
            "legacy_tools_removed": False,
        },
        "public_tools": list(PUBLIC_TOOLS),
        "public_actions": list(PUBLIC_ACTIONS),
        "schemas": {
            "tool_inputs": {
                str(definition["name"]): definition["inputSchema"]
                for definition in TOOL_DEFINITIONS
            },
            "action_response": ACTION_RESPONSE_SCHEMA,
            "lookup_response": LOOKUP_RESPONSE_SCHEMA,
        },
        "action_token": {
            "format": "act1_<43 base64url chars>",
            "opaque": True,
            "binds": ["project_key", "work_key", "state_version", "action_kind"],
            "production_requirement": "server-generated unguessable token",
            "retry_semantics": {
                "same_token_same_report": "idempotent_replay",
                "same_token_different_report": "idempotency_conflict",
                "noncurrent_unconsumed_token": "stale_action",
            },
        },
        "promotion": {
            "clean": "fresh_managed_attachment",
            "dirty": "dirty_baseline_adopt",
            "dirty_prohibits": ["reset", "rebase", "stash", "discard"],
        },
        "budgets": {
            "catalog_bytes": FACADE_CATALOG_MAX_BYTES,
            "response_bytes": FACADE_RESPONSE_MAX_BYTES,
            "action_response_bytes": FACADE_ACTION_RESPONSE_MAX_BYTES,
        },
        "target_journeys": build_target_journeys(),
    }


def main() -> int:
    print(json.dumps(build_contract_fixture(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
