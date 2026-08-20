from __future__ import annotations

import json
import runpy
from pathlib import Path

from ai_layer.mcp.runtime import TOOL_HANDLERS

ROOT = Path(__file__).resolve().parents[1]
_PHASE1_PATH = ROOT / "scripts" / "agent_native_phase1_facade.py"
_phase1 = runpy.run_path(str(_PHASE1_PATH))

ActionBinding = _phase1["ActionBinding"]
EnterScenario = _phase1["EnterScenario"]
ACTION_RESPONSE_SCHEMA = _phase1["ACTION_RESPONSE_SCHEMA"]
FACADE_ACTION_RESPONSE_MAX_BYTES = _phase1["FACADE_ACTION_RESPONSE_MAX_BYTES"]
FACADE_CATALOG_MAX_BYTES = _phase1["FACADE_CATALOG_MAX_BYTES"]
FACADE_RESPONSE_MAX_BYTES = _phase1["FACADE_RESPONSE_MAX_BYTES"]
FORBIDDEN_PUBLIC_FSM_TERMS = _phase1["FORBIDDEN_PUBLIC_FSM_TERMS"]
PUBLIC_ACTIONS = _phase1["PUBLIC_ACTIONS"]
PUBLIC_TOOLS = _phase1["PUBLIC_TOOLS"]
TOOL_DEFINITIONS = _phase1["TOOL_DEFINITIONS"]
action_token_shape_valid = _phase1["action_token_shape_valid"]
build_contract_fixture = _phase1["build_contract_fixture"]
build_target_journeys = _phase1["build_target_journeys"]
classify_submission = _phase1["classify_submission"]
issue_action_token = _phase1["issue_action_token"]
matching_tools = _phase1["matching_tools"]
make_next_action = _phase1["make_next_action"]
promotion_strategy = _phase1["promotion_strategy"]
report_fingerprint = _phase1["report_fingerprint"]
representative_responses = _phase1["representative_responses"]
resolve_enter = _phase1["resolve_enter"]
serialized_bytes = _phase1["serialized_bytes"]
validate_tool_arguments = _phase1["validate_tool_arguments"]

SECRET = b"phase1-contract-tests"


def _token(
    *,
    project_key: str = "alpha",
    work_key: str | None = "W-0001",
    state_version: int = 1,
    action_kind: str = "native_engineering",
) -> str:
    return issue_action_token(
        ActionBinding(project_key, work_key, state_version, action_kind),
        secret=SECRET,
    )


def test_public_tool_catalog_is_small_disjoint_and_not_registered() -> None:
    assert tuple(definition["name"] for definition in TOOL_DEFINITIONS) == PUBLIC_TOOLS
    assert set(PUBLIC_TOOLS).isdisjoint(TOOL_HANDLERS)
    assert serialized_bytes(TOOL_DEFINITIONS) <= FACADE_CATALOG_MAX_BYTES

    cases = {
        "project_enter": {
            "project_root": "/repo",
            "intent": "start",
            "goal": "Fix the router",
        },
        "project_lookup": {"project_root": "/repo", "query": "request router"},
        "work_continue": {
            "action_token": _token(),
            "report": {"kind": "native_result", "summary": "Implemented and tested"},
        },
        "work_finish": {
            "action_token": _token(action_kind="done"),
            "summary": "Completed and verified",
        },
    }
    for name, arguments in cases.items():
        assert matching_tools(arguments) == (name,)
        assert validate_tool_arguments(name, arguments) == ()

    assert (
        matching_tools(
            {
                "action_token": _token(),
                "report": {"kind": "native_result", "summary": "done"},
                "summary": "ambiguous extra terminal report",
            }
        )
        == ()
    )


def test_enter_semantics_reject_ambiguous_start_resume_payloads() -> None:
    assert validate_tool_arguments(
        "project_enter",
        {"project_root": "/repo", "intent": "start"},
    ) == ("start_requires_goal",)
    assert validate_tool_arguments(
        "project_enter",
        {"project_root": "/repo", "intent": "resume", "goal": "new request"},
    ) == ("resume_rejects_goal",)


def test_action_token_is_opaque_state_bound_and_retry_safe() -> None:
    binding = ActionBinding("alpha", "W-0001", 3, "native_engineering")
    token = issue_action_token(binding, secret=SECRET)
    assert action_token_shape_valid(token)
    assert "alpha" not in token
    assert "W-0001" not in token
    assert token == issue_action_token(binding, secret=SECRET)
    assert token != issue_action_token(
        ActionBinding("alpha", "W-0001", 4, "native_engineering"),
        secret=SECRET,
    )
    assert token != issue_action_token(binding, secret=b"other-secret")

    report = {"kind": "native_result", "summary": "implemented"}
    current = _token(state_version=4)
    consumed = {token: report_fingerprint(report)}
    assert (
        classify_submission(
            current_token=current,
            consumed_reports=consumed,
            submitted_token=token,
            report=report,
        )
        == "idempotent_replay"
    )
    assert (
        classify_submission(
            current_token=current,
            consumed_reports=consumed,
            submitted_token=token,
            report={"kind": "native_result", "summary": "different result"},
        )
        == "idempotency_conflict"
    )
    assert (
        classify_submission(
            current_token=current,
            consumed_reports={},
            submitted_token=_token(state_version=2),
            report=report,
        )
        == "stale_action"
    )
    assert (
        classify_submission(
            current_token=current,
            consumed_reports={},
            submitted_token=current,
            report=report,
        )
        == "advance"
    )
    assert (
        classify_submission(
            current_token=current,
            consumed_reports={},
            submitted_token="not-a-token",
            report=report,
        )
        == "invalid_action_token"
    )


def test_multiple_active_work_requires_explicit_human_decision() -> None:
    response = resolve_enter(
        EnterScenario(
            project_key="alpha",
            intent="resume",
            goal=None,
            assurance="native",
            active_work_keys=("W-0001", "W-0002"),
        ),
        secret=SECRET,
    )
    action = response["next_action"]
    assert response["work"] is None
    assert action["kind"] == "human_decision"
    assert action["choices"] == ["W-0001", "W-0002"]
    assert action_token_shape_valid(action["action_token"])


def test_existing_managed_and_epic_work_resume_without_exposing_internal_navigators() -> None:
    response = resolve_enter(
        EnterScenario(
            project_key="alpha",
            intent="resume",
            goal="Ship the API change",
            assurance="reviewed",
            active_work_keys=("W-0007",),
            state_version=8,
            current_directive="worker_check",
            epic_attached=True,
        ),
        secret=SECRET,
    )
    assert response["work"]["key"] == "W-0007"
    assert response["work"]["epic_attached"] is True
    assert response["next_action"]["kind"] == "run_worker"
    assert response["next_action"]["worker_kind"] == "independent_check"
    assert all(term not in json.dumps(response) for term in FORBIDDEN_PUBLIC_FSM_TERMS)


def test_new_unrelated_request_gets_new_work_instead_of_hijacking_active_work() -> None:
    response = resolve_enter(
        EnterScenario(
            project_key="alpha",
            intent="start",
            goal="Investigate a separate regression",
            assurance="native",
            active_work_keys=("W-0001", "W-0002"),
            new_work_key="W-0003",
        ),
        secret=SECRET,
    )
    assert response["work"]["key"] == "W-0003"
    assert response["next_action"]["kind"] == "native_engineering"


def test_clean_and_dirty_review_promotion_are_distinct_and_non_destructive() -> None:
    assert promotion_strategy(dirty_worktree=False) == "fresh_managed_attachment"
    assert promotion_strategy(dirty_worktree=True) == "dirty_baseline_adopt"

    reviewed = resolve_enter(
        EnterScenario(
            project_key="alpha",
            intent="start",
            goal="Escalate verification",
            assurance="reviewed",
            new_work_key="W-0004",
            dirty_worktree=True,
        ),
        secret=SECRET,
    )
    assert reviewed["next_action"]["kind"] == "run_worker"
    assert "promotion" not in reviewed

    fixture = build_contract_fixture()
    promotion = fixture["promotion"]
    assert promotion["dirty"] == "dirty_baseline_adopt"
    assert promotion["dirty_prohibits"] == ["reset", "rebase", "stash", "discard"]


def test_done_action_carries_finish_token_without_exposing_fsm_state() -> None:
    action = make_next_action(
        project_key="alpha",
        work_key="W-0009",
        state_version=11,
        directive="complete",
        secret=SECRET,
        instruction="Managed assurance is complete; record the durable Work outcome.",
    )
    assert action["kind"] == "done"
    assert action_token_shape_valid(action["action_token"])
    assert action["state_version"] == 11
    assert all(term not in json.dumps(action) for term in FORBIDDEN_PUBLIC_FSM_TERMS)


def test_all_six_target_journeys_fit_four_tools_and_four_actions() -> None:
    journeys = build_target_journeys()
    assert len(journeys) == 6
    assert journeys["B_long_ordinary_optional_review"]["invariants"]["promotion_same_work"] is True
    assert journeys["E_epic_continuation"]["invariants"]["internal_epic_navigation_hidden"] is True
    assert (
        journeys["F_mid_native_escalation"]["invariants"]["same_work_before_after_escalation"]
        is True
    )

    for journey in journeys.values():
        for step in journey["steps"]:
            assert step["tool"] in PUBLIC_TOOLS
            if "returns" in step:
                assert step["returns"] in PUBLIC_ACTIONS

    serialized = json.dumps(journeys, sort_keys=True)
    for term in FORBIDDEN_PUBLIC_FSM_TERMS:
        assert term not in serialized


def test_facade_catalog_is_at_least_ninety_percent_smaller_than_phase0_runtime_catalog() -> None:
    baseline_path = ROOT / "docs" / "evidence" / "0.14.0-agent-native-phase0-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_bytes = baseline["catalog"]["catalog_profile"]["utf8_bytes"]
    facade_bytes = serialized_bytes(TOOL_DEFINITIONS)

    assert facade_bytes * 10 <= baseline_bytes


def test_representative_responses_stay_inside_public_context_budgets() -> None:
    responses = representative_responses(secret=SECRET)
    assert serialized_bytes(responses["project_enter"]) <= FACADE_RESPONSE_MAX_BYTES
    assert serialized_bytes(responses["project_lookup"]) <= FACADE_RESPONSE_MAX_BYTES
    assert serialized_bytes(responses["work_continue"]) <= FACADE_ACTION_RESPONSE_MAX_BYTES
    assert serialized_bytes(responses["work_finish"]) <= FACADE_ACTION_RESPONSE_MAX_BYTES
    assert serialized_bytes(ACTION_RESPONSE_SCHEMA) < FACADE_CATALOG_MAX_BYTES


def test_committed_golden_fixture_matches_executable_contract() -> None:
    fixture_path = ROOT / "tests" / "fixtures" / "agent_native_phase1_facade.json"
    committed = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert committed == build_contract_fixture()
