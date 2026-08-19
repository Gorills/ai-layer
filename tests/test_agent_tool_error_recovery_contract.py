from ai_layer.domain.agent_contract import agent_runtime_bootstrap_line, agent_runtime_contract
from ai_layer.domain.orchestrator import critical_orchestrator_contract, native_bootstrap_markdown


def test_tool_errors_are_fail_closed_until_required_call_succeeds() -> None:
    contract = agent_runtime_contract()
    errors = contract["tool_errors"]

    assert "did not succeed" in errors["success_precondition"]
    assert "retry the same tool" in errors["validation"]
    assert "Do not continue until the required call succeeds" in errors["validation"]
    assert "copy its project_root verbatim" in errors["project_context"]
    assert "project_status(project_root=<host workspace root>)" in errors["project_context"]
    assert "skill_get requires the argument slug, not skill_name" in errors["schema"]
    assert "validation errors are not availability failures" in errors["availability"]


def test_native_and_mcp_bootstraps_explain_recovery_sequence() -> None:
    native = native_bootstrap_markdown()
    fallback = agent_runtime_bootstrap_line()

    for text in (native, fallback):
        lowered = text.casefold()
        assert "failed ai layer tool call" in lowered or "failed tool call" in lowered
        assert "retry the same tool" in lowered
        assert "project_context_ambiguous" in lowered
        assert "project_status(project_root=<host workspace root>)" in text
        assert "skill_get" in lowered
        assert "skill_name" in lowered
        assert "slug" in lowered

    assert "pass it verbatim to every later project-scoped AI Layer tool call" in native
    assert "validation failures must be repaired" in fallback


def test_orchestrator_contract_distinguishes_validation_from_unavailability() -> None:
    contract = critical_orchestrator_contract()

    assert "retry the same tool" in contract["tool_error_rule"]
    assert "Validation and PROJECT_CONTEXT_* failures must be repaired" in contract["failure_rule"]
