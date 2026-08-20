from __future__ import annotations

from collections.abc import Callable
from typing import Any

SOURCE_PATH = "src/ai_layer/mcp/runtime.py"
TEST_PATH = "tests/test_agent_facing_contracts.py"

_STEP_SPECS: dict[str, tuple[tuple[str, str, dict[str, Any]], ...]] = {
    "ordinary_known_location_change": (
        ("ai_layer_call", "project_status", {}),
        ("ai_layer_call", "work_begin", {}),
        (
            "native_read",
            "open_known_source",
            {"relevant_source": True, "reviewed_paths": [SOURCE_PATH]},
        ),
        ("native_edit", "edit_known_source", {"changed_paths": [SOURCE_PATH]}),
        ("check", "targeted_check", {}),
        ("ai_layer_call", "project_map_reconcile", {}),
        ("ai_layer_call", "work_complete", {}),
    ),
    "ordinary_unknown_location_change": (
        ("ai_layer_call", "project_status", {}),
        ("ai_layer_call", "work_begin", {}),
        ("ai_layer_call", "project_search", {"candidate_paths": [SOURCE_PATH, TEST_PATH]}),
        (
            "native_read",
            "open_search_candidate",
            {"relevant_source": True, "reviewed_paths": [SOURCE_PATH]},
        ),
        ("native_edit", "edit_discovered_source", {"changed_paths": [SOURCE_PATH]}),
        ("check", "targeted_check", {}),
        ("ai_layer_call", "project_map_reconcile", {}),
        ("ai_layer_call", "work_complete", {}),
    ),
    "explicit_standard_change": (
        ("ai_layer_call", "project_status", {}),
        ("ai_layer_call", "task_create", {}),
        ("ai_layer_call", "task_stage_delegate", {}),
        ("host_lifecycle", "implement_worker", {}),
        ("native_read", "worker_read", {"relevant_source": True, "reviewed_paths": [SOURCE_PATH]}),
        ("native_edit", "worker_edit", {"changed_paths": [SOURCE_PATH]}),
        ("check", "implementation_check", {}),
        ("ai_layer_call", "task_implementation_complete", {}),
        ("ai_layer_call", "task_next", {}),
        ("ai_layer_call", "task_stage_delegate", {}),
        ("review", "independent_review", {"reviewed_paths": [SOURCE_PATH, TEST_PATH]}),
        ("check", "review_check", {}),
        ("ai_layer_call", "task_review_complete", {}),
        ("ai_layer_call", "task_next", {}),
    ),
    "native_to_reviewed_escalation": (
        ("ai_layer_call", "project_status", {}),
        ("ai_layer_call", "work_begin", {}),
        ("native_read", "native_read", {"relevant_source": True, "reviewed_paths": [SOURCE_PATH]}),
        ("native_edit", "native_edit", {"changed_paths": [SOURCE_PATH]}),
        ("check", "native_check", {}),
        ("ai_layer_call", "task_adopt", {}),
        ("ai_layer_call", "task_next", {}),
        ("ai_layer_call", "task_stage_delegate", {}),
        ("review", "independent_review", {"reviewed_paths": [SOURCE_PATH, TEST_PATH]}),
        ("check", "review_check", {}),
        ("ai_layer_call", "task_review_complete", {}),
        ("ai_layer_call", "task_next", {}),
    ),
    "continue_after_restart": (
        ("ai_layer_call", "project_status", {}),
        ("ai_layer_call", "work_resume", {}),
        (
            "native_read",
            "reopen_current_focus",
            {"relevant_source": True, "reviewed_paths": [SOURCE_PATH]},
        ),
        ("native_edit", "continue_edit", {"changed_paths": [SOURCE_PATH]}),
        ("check", "targeted_check", {}),
        ("ai_layer_call", "project_map_reconcile", {}),
        ("ai_layer_call", "work_complete", {}),
    ),
    "epic_continuation": (
        ("ai_layer_call", "project_status", {}),
        ("ai_layer_call", "epic_next", {}),
        ("ai_layer_call", "epic_start_next", {}),
        ("ai_layer_call", "task_next", {}),
        ("ai_layer_call", "task_stage_delegate", {}),
        ("host_lifecycle", "implement_worker", {}),
        ("native_read", "worker_read", {"relevant_source": True, "reviewed_paths": [SOURCE_PATH]}),
        ("native_edit", "worker_edit", {"changed_paths": [SOURCE_PATH]}),
        ("check", "implementation_check", {}),
        ("ai_layer_call", "task_implementation_complete", {}),
        ("ai_layer_call", "task_next", {}),
        ("ai_layer_call", "task_stage_delegate", {}),
        ("review", "independent_review", {"reviewed_paths": [SOURCE_PATH, TEST_PATH]}),
        ("check", "review_check", {}),
        ("ai_layer_call", "task_review_complete", {}),
        ("ai_layer_call", "epic_next", {}),
    ),
}


def configured_journey_fixtures(
    *,
    event_builder: Callable[..., dict[str, Any]],
    trace_builder: Callable[[str, str], dict[str, Any]],
    finalizer: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic current-protocol fixtures without claiming host observation."""
    fixtures: list[dict[str, Any]] = []
    for journey, steps in _STEP_SPECS.items():
        trace = trace_builder(journey, "protocol-configured")
        for kind, operation, options in steps:
            kwargs = dict(options)
            kwargs["observability_class"] = "configured"
            if kind == "ai_layer_call":
                kwargs["request_payload"] = {"fixture": journey, "operation": operation}
                kwargs["response_payload"] = {"fixture": journey, "status": "configured"}
            trace["events"].append(event_builder(kind, operation, **kwargs))
        fixtures.append(finalizer(trace))
    return fixtures
