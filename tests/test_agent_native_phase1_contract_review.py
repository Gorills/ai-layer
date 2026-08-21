from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_phase1 = runpy.run_path(str(ROOT / "scripts" / "agent_native_phase1_facade.py"))

ACTION_RESPONSE_SCHEMA = _phase1["ACTION_RESPONSE_SCHEMA"]
LOOKUP_RESPONSE_SCHEMA = _phase1["LOOKUP_RESPONSE_SCHEMA"]
representative_responses = _phase1["representative_responses"]
validate_tool_arguments = _phase1["validate_tool_arguments"]

SECRET = b"phase1-contract-review-tests"


def _assert_object_shape(value: Any, schema: dict[str, Any]) -> None:
    assert isinstance(value, dict)
    required = set(schema["required"])
    properties = set(schema["properties"])
    assert required.issubset(value)
    assert set(value).issubset(properties)


def test_start_rejects_caller_supplied_work_identity() -> None:
    assert validate_tool_arguments(
        "project_enter",
        {
            "project_root": "/repo",
            "intent": "start",
            "goal": "Fix the router",
            "work_key": "W-CALLER-SUPPLIED",
        },
    ) == ("start_rejects_work_key",)


def test_representative_action_responses_match_declared_output_shape() -> None:
    responses = representative_responses(secret=SECRET)
    work_schema = ACTION_RESPONSE_SCHEMA["properties"]["work"]["anyOf"][0]
    action_schema = ACTION_RESPONSE_SCHEMA["properties"]["next_action"]
    project_schema = ACTION_RESPONSE_SCHEMA["properties"]["project"]

    for name in ("project_enter", "work_continue", "work_finish"):
        response = responses[name]
        _assert_object_shape(response, ACTION_RESPONSE_SCHEMA)
        assert (
            response["contract_version"]
            == ACTION_RESPONSE_SCHEMA["properties"]["contract_version"]["const"]
        )
        _assert_object_shape(response["project"], project_schema)
        assert response["work"] is not None
        _assert_object_shape(response["work"], work_schema)
        _assert_object_shape(response["next_action"], action_schema)
        assert response["next_action"]["kind"] in action_schema["properties"]["kind"]["enum"]


def test_representative_lookup_response_matches_declared_output_shape() -> None:
    response = representative_responses(secret=SECRET)["project_lookup"]
    _assert_object_shape(response, LOOKUP_RESPONSE_SCHEMA)
    assert response["source_truth_required"] is True

    breadcrumb_schema = LOOKUP_RESPONSE_SCHEMA["properties"]["breadcrumbs"]["items"]
    for breadcrumb in response["breadcrumbs"]:
        _assert_object_shape(breadcrumb, breadcrumb_schema)
