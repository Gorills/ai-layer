from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_layer import __version__

ROOT = Path(__file__).resolve().parents[1]
_baseline = runpy.run_path(str(ROOT / "scripts" / "agent_native_baseline_lib.py"))
FIELD_RUN_HOSTS = _baseline["FIELD_RUN_HOSTS"]
OBSERVABILITY_CLASSES = _baseline["OBSERVABILITY_CLASSES"]
PHASE0_JOURNEYS = _baseline["PHASE0_JOURNEYS"]
build_baseline_report = _baseline["build_baseline_report"]
field_run_checklist = _baseline["field_run_checklist"]
finalize_journey = _baseline["finalize_journey"]
journey_event = _baseline["journey_event"]
new_journey_trace = _baseline["new_journey_trace"]
retrieval_usefulness = _baseline["retrieval_usefulness"]
runtime_catalog_snapshot = _baseline["runtime_catalog_snapshot"]
write_baseline_report = _baseline["write_baseline_report"]


def _tool(name: str, required: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=None,
        description=f"{name} description",
        parameters={
            "type": "object",
            "properties": {item: {"type": "string"} for item in required},
            "required": list(required),
        },
        output_schema=None,
        annotations=None,
        icons=None,
        meta=None,
    )


class _Manager:
    def __init__(self, tools):
        self._tools = tools

    def list_tools(self):
        return list(self._tools)


def test_runtime_catalog_profiles_registered_tool_schemas_and_definitions() -> None:
    server = SimpleNamespace(_tool_manager=_Manager([_tool("beta"), _tool("alpha", ("goal",))]))
    snapshot = runtime_catalog_snapshot(server, tool_handlers={"alpha": object(), "beta": object()})

    assert snapshot["tool_count"] == 2
    assert [item["name"] for item in snapshot["tools"]] == ["alpha", "beta"]
    alpha = snapshot["tools"][0]
    assert alpha["definition"]["inputSchema"]["required"] == ["goal"]
    assert alpha["input_schema_profile"]["utf8_bytes"] > 0
    assert (
        alpha["tool_definition_profile"]["utf8_bytes"] > alpha["input_schema_profile"]["utf8_bytes"]
    )
    assert snapshot["catalog_profile"]["estimated_tokens"] > 0


def test_runtime_catalog_fails_closed_when_runtime_and_handler_registry_diverge() -> None:
    server = SimpleNamespace(_tool_manager=_Manager([_tool("alpha")]))
    with pytest.raises(RuntimeError, match="differs from TOOL_HANDLERS"):
        runtime_catalog_snapshot(server, tool_handlers={"beta": object()})


def test_journey_trace_profiles_payloads_without_retaining_raw_prompt_or_source() -> None:
    trace = new_journey_trace("ordinary_unknown_location_change", "codex")
    first = journey_event(
        "ai_layer_call",
        "project_search",
        request_payload={"query": "API_TOKEN=secret-one"},
        response_payload={"content": "API_TOKEN=source-secret-one"},
        latency_ms=12.5,
        candidate_paths=["src/service.py"],
    )
    second = journey_event(
        "ai_layer_call",
        "project_search",
        request_payload={"query": "API_TOKEN=secret-two"},
        response_payload={"content": "API_TOKEN=source-secret-two"},
    )
    assert first["request_profile"]["sha256"] == second["request_profile"]["sha256"]
    assert first["response_profile"]["sha256"] == second["response_profile"]["sha256"]
    trace["events"].append(first)
    trace["events"].append(
        journey_event(
            "native_read",
            "open_file",
            relevant_source=True,
            reviewed_paths=["src/service.py"],
        )
    )
    trace["events"].append(
        journey_event("native_edit", "edit_file", changed_paths=["src/service.py"])
    )
    result = finalize_journey(trace)
    raw = json.dumps(result, sort_keys=True)

    assert "secret-one" not in raw
    assert "source-secret-one" not in raw
    assert result["metrics"]["ai_layer_call_count"] == 1
    assert result["metrics"]["native_search_read_before_first_relevant_source"] == 0
    assert result["metrics"]["retrieval_usefulness"]["candidate_to_changed_hit_rate"] == 1.0


def test_finalize_journey_rejects_unknown_raw_fields_even_if_caller_bypasses_builder() -> None:
    trace = new_journey_trace("ordinary_known_location_change", "codex")
    trace["events"] = [
        {
            **journey_event("ai_layer_call", "project_status", request_payload={"goal": "safe"}),
            "raw_prompt": "must never survive",
        }
    ]
    with pytest.raises(ValueError, match="unknown fields.*raw_prompt"):
        finalize_journey(trace)


def test_failed_journey_events_require_stable_failure_class() -> None:
    with pytest.raises(ValueError, match="require failure_class"):
        journey_event("ai_layer_call", "project_status", ok=False)
    event = journey_event(
        "ai_layer_call",
        "project_status",
        ok=False,
        failure_class="tool_error",
    )
    assert event["failure_class"] == "tool_error"


def test_journey_event_rejects_truthy_non_boolean_flags_and_invalid_latency() -> None:
    with pytest.raises(ValueError, match="ok must be boolean"):
        journey_event("ai_layer_call", "project_status", ok="false")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="relevant_source must be boolean"):
        journey_event("native_read", "open_file", relevant_source=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="correction_retry must be boolean"):
        journey_event("ai_layer_call", "project_status", correction_retry="yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative number"):
        journey_event("ai_layer_call", "project_status", latency_ms=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative number"):
        journey_event("ai_layer_call", "project_status", latency_ms=-0.1)


def test_journey_paths_are_portable_and_require_a_real_sequence() -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        journey_event("native_read", "open_file", reviewed_paths=["/tmp/repo/source.py"])
    with pytest.raises(ValueError, match="traverse"):
        journey_event("native_read", "open_file", reviewed_paths=["../source.py"])
    with pytest.raises(ValueError, match="repository-relative"):
        journey_event("native_read", "open_file", reviewed_paths=[r"C:\repo\source.py"])
    with pytest.raises(ValueError, match="must be strings"):
        journey_event("native_read", "open_file", reviewed_paths=[123])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="sequence of strings"):
        journey_event("native_read", "open_file", reviewed_paths="src/service.py")  # type: ignore[arg-type]


def test_finalize_journey_rejects_forged_negative_profile_counters() -> None:
    event = journey_event("ai_layer_call", "project_status", request_payload={"goal": "safe"})
    event["request_profile"] = dict(event["request_profile"])
    event["request_profile"]["utf8_bytes"] = -1
    trace = new_journey_trace("ordinary_known_location_change", "codex")
    trace["events"] = [event]

    with pytest.raises(ValueError, match="utf8_bytes must be a non-negative integer"):
        finalize_journey(trace)


def test_journey_metrics_count_duplicates_retries_checks_and_latency() -> None:
    request = {"project_root": "/redacted", "goal": "profiled only"}
    events = [
        journey_event(
            "ai_layer_call",
            "project_status",
            request_payload=request,
            response_payload={"ok": True},
            latency_ms=10,
        ),
        journey_event(
            "ai_layer_call",
            "project_status",
            request_payload=request,
            response_payload={"ok": True},
            latency_ms=40,
            correction_retry=True,
            failure_class="workflow_correction",
        ),
        journey_event("native_search", "grep"),
        journey_event("native_read", "open_file", relevant_source=True),
        journey_event("check", "pytest"),
        journey_event("native_edit", "edit_file"),
    ]
    trace = new_journey_trace("ordinary_known_location_change", "cursor")
    trace["events"] = events
    metrics = finalize_journey(trace)["metrics"]

    assert metrics["ai_layer_call_count"] == 2
    assert metrics["duplicate_control_plane_call_count"] == 1
    assert metrics["workflow_correction_retry_count"] == 1
    assert metrics["workflow_correction_retry_rate"] == 0.5
    assert metrics["failure_classes"] == {"workflow_correction": 1}
    assert metrics["engineering_check_count"] == 1
    assert metrics["mcp_latency_sample_count"] == 2
    assert metrics["mcp_latency_ms_p50"] == 10.0
    assert metrics["mcp_latency_ms_p95"] == 40.0
    assert metrics["observability_class_counts"] == {
        "configured": 0,
        "observed": 6,
        "unsupported": 0,
    }
    assert metrics["native_search_read_before_first_relevant_source"] == 1
    assert metrics["native_search_read_before_first_edit"] == 2


def test_retrieval_usefulness_is_path_based_and_deterministic() -> None:
    result = retrieval_usefulness(
        ["src/b.py", "src/a.py", "src/a.py"],
        reviewed_paths=["src/a.py", "tests/test_a.py"],
        changed_paths=["src/a.py"],
    )
    assert result["candidate_count"] == 2
    assert result["inspected_hit_paths"] == ["src/a.py"]
    assert result["changed_hit_paths"] == ["src/a.py"]
    assert result["candidate_to_inspected_hit_rate"] == 0.5


def test_phase0_field_run_checklist_is_truthful_about_host_observation() -> None:
    checklist = field_run_checklist()
    assert tuple(item["host"] for item in checklist["hosts"]) == FIELD_RUN_HOSTS
    assert set(OBSERVABILITY_CLASSES) == set(checklist["observability_classes"])
    for host in checklist["hosts"]:
        assert host["journeys"] == list(PHASE0_JOURNEYS)
        assert set(host["capabilities"].values()) <= set(OBSERVABILITY_CLASSES)
        assert host["capabilities"]["session_lifecycle_hooks"] == "unsupported"
        assert host["capabilities"]["subagent_lifecycle_hooks"] == "unsupported"
        assert host["capabilities"]["native_tool_lifecycle_hooks"] == "unsupported"
        assert "observed" not in host["capabilities"].values()


def test_baseline_report_is_deterministic_and_measurement_only(tmp_path: Path) -> None:
    server = SimpleNamespace(_tool_manager=_Manager([_tool("project_status"), _tool("work_begin")]))
    report = build_baseline_report(
        server,
        tool_handlers={"project_status": object(), "work_begin": object()},
        mcp_instructions="mcp bootstrap",
        bootstrap_text="native bootstrap",
        skill_documents={"testing.md": "---\nname: testing\n---\nbody"},
    )
    first = write_baseline_report(tmp_path / "first.json", report).read_text(encoding="utf-8")
    second = write_baseline_report(tmp_path / "second.json", report).read_text(encoding="utf-8")

    assert first == second
    payload = json.loads(first)
    assert payload["package_version"] == __version__
    assert payload["scope"] == "agent_native_phase0_measurement_only"
    assert payload["configured_context"]["bootstrap_profile"]["utf8_bytes"] > 0
    assert payload["configured_context"]["skill_document_profiles"]["testing.md"]["utf8_bytes"] > 0
    assert payload["privacy"] == {
        "raw_prompt": "not_recorded",
        "raw_source_body": "not_recorded",
        "repository_locations": "relative_paths_only",
        "request_response": "profile_only",
    }


def test_real_runtime_baseline_report_is_generated_from_registered_catalog(tmp_path: Path) -> None:
    from ai_layer.domain.orchestrator import native_bootstrap_markdown
    from ai_layer.mcp.runtime import MCP_INSTRUCTIONS, TOOL_HANDLERS
    from ai_layer.mcp.server import mcp

    skills_root = ROOT / "src" / "ai_layer" / "builtin_skills"
    skills = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(skills_root.glob("*.md"))
    }
    report = build_baseline_report(
        mcp,
        tool_handlers=TOOL_HANDLERS,
        mcp_instructions=MCP_INSTRUCTIONS,
        bootstrap_text=native_bootstrap_markdown(),
        skill_documents=skills,
    )
    output = write_baseline_report(tmp_path / "agent-native-baseline.json", report)
    payload = json.loads(output.read_text(encoding="utf-8"))
    names = [item["name"] for item in payload["catalog"]["tools"]]

    assert len(names) == len(TOOL_HANDLERS)
    assert set(names) == set(TOOL_HANDLERS)
    assert {"project_status", "project_search", "work_begin", "task_next", "epic_next"} <= set(
        names
    )
    assert payload["catalog"]["catalog_profile"]["utf8_bytes"] > 0
    assert payload["configured_context"]["mcp_instructions_profile"]["utf8_bytes"] > 0
    assert payload["configured_context"]["bootstrap_profile"]["utf8_bytes"] > 0
    assert payload["configured_context"]["skill_document_profiles"]
