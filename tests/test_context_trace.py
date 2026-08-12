from __future__ import annotations

import json
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.observability import context_trace
from ai_layer.observability.context_report import build_report


def _prepare(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "user-home"))
    get_settings.cache_clear()
    register_project(repo, project_id="p-context", name="repo", mode="external")
    return repo, home


def test_context_trace_captures_redacted_memory_payload_and_skill_economy(
    monkeypatch, tmp_path: Path
):
    repo, home = _prepare(tmp_path, monkeypatch)

    def memory_context(task=None, project_root=None):
        return None

    payload = {
        "project_root": str(repo),
        "policy": "API_TOKEN=super-secret-value\nmandatory rule",
        "response_contract": {"max_words": 100},
        "task_runtime": {"active": False},
        "completion_requirements": {"managed": True},
        "tool_guidance": {"recommended_calls": []},
        "project_intelligence": {"signals": ["python"]},
        "task_evidence": [],
        "recent_change_evidence": [],
        "memory": [{"content": "payment service", "score": 0.9}],
        "skill_access": {
            "routing_owner": "host-native",
            "automatic_domain_skill_injection": False,
            "retrieval_tool": "skill_get",
        },
        "context_budget": {
            "policy_over_soft_target": False,
            "policy_chars": 42,
            "automatic_skill_chars": 0,
        },
    }
    context_trace.record_tool_delivery(
        memory_context,
        "memory_context",
        (),
        {"task": "Fix payment token=another-secret", "project_root": str(repo)},
        payload,
        mcp_instructions="critical instructions",
        mcp_tool_catalog=(
            {
                "name": "memory_context",
                "signature": "(task, project_root)",
                "description": "context",
            },
        ),
    )

    from ai_layer.observability.context_common import report_path, trace_path

    trace = trace_path(repo)
    report = report_path(repo)
    assert trace.is_file()
    assert report.is_file()
    assert str(trace).startswith(str(home / "projects" / "p-context"))
    assert not (repo / ".ai-layer" / "diagnostics").exists()

    raw = trace.read_text(encoding="utf-8")
    assert "super-secret-value" not in raw
    assert "another-secret" not in raw
    assert "<redacted>" in raw

    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["tool_calls"]["memory_context"] == 1
    event = data["events"][0]
    assert event["breakdown"]["automatic_domain_skill_injection"] is False
    assert event["result"]["skill_access"]["routing_owner"] == "host-native"
    assert data["skill_flow"]["ai_layer_runtime_planner_active"] is False
    assert data["skill_flow"]["automatic_domain_skill_estimated_tokens_current"] == 0
    assert data["coverage"]["HOST_HIDDEN"]
    assert (
        data["latest_configured_context"]["mcp_server_instructions"]["content"]
        == "critical instructions"
    )
    assert data["latest_configured_context"]["mcp_tool_catalog"]["tool_count"] == 1
    assert data["summary"]["configured_context_estimated_tokens"]["mcp_tool_catalog"] > 0


def test_context_trace_flags_full_and_repeated_skill_fetch(monkeypatch, tmp_path: Path):
    repo, _ = _prepare(tmp_path, monkeypatch)

    def memory_context(task=None, project_root=None):
        return None

    context_trace.record_tool_delivery(
        memory_context,
        "memory_context",
        (),
        {"task": "Fix API", "project_root": str(repo)},
        {
            "project_root": str(repo),
            "policy": "p",
            "skill_access": {
                "routing_owner": "host-native",
                "automatic_domain_skill_injection": False,
            },
            "memory": [],
            "context_budget": {"policy_over_soft_target": False, "automatic_skill_chars": 0},
        },
        mcp_instructions="mcp",
    )

    def skill_get(slug=None, section=None, project_root=None):
        return None

    for _ in range(2):
        context_trace.record_tool_delivery(
            skill_get,
            "skill_get",
            (),
            {"slug": "testing", "project_root": str(repo)},
            {
                "slug": "testing",
                "section": "full",
                "content": "X" * 4000,
                "project_root": str(repo),
            },
        )

    report = build_report(repo)
    codes = [item["code"] for item in report["findings"]]
    assert "FULL_SKILL_FETCH" in codes
    assert "REPEATED_SKILL_FETCH" in codes
    assert report["summary"]["tool_calls"]["skill_get"] == 2
    assert report["summary"]["dynamic_tool_result_estimated_tokens_total"] > 0


def test_estimate_tokens_is_explicitly_approximate_and_unicode_aware():
    assert context_trace.estimate_tokens("abcd") == 1
    assert context_trace.estimate_tokens("тест") >= 2


def test_mcp_execution_boundary_records_successful_tool_delivery(monkeypatch):
    from ai_layer.mcp import runtime as mcp_runtime

    seen = {}

    def fake_record(
        func,
        tool,
        args,
        kwargs,
        result,
        *,
        mcp_instructions=None,
        mcp_tool_catalog=None,
        resolved_project_root=None,
    ):
        seen.update(
            {
                "tool": tool,
                "args": args,
                "kwargs": kwargs,
                "result": result,
                "instructions": mcp_instructions,
                "catalog": mcp_tool_catalog,
                "resolved_project_root": resolved_project_root,
            }
        )

    monkeypatch.setattr(context_trace, "record_tool_delivery", fake_record)
    result = mcp_runtime._execute_local_tool(
        lambda value=1: {"value": value}, "project_info", (), {"value": 7}
    )
    assert result == {"value": 7}
    assert seen["tool"] == "project_info"
    assert seen["kwargs"] == {"value": 7}
    assert "project_status" in seen["instructions"]
    assert "native host reads/edits/tests/subagents" in seen["instructions"]


def test_mcp_boundary_resolves_bound_project_for_telemetry(monkeypatch, tmp_path: Path):
    from ai_layer.mcp import runtime as mcp_runtime
    from ai_layer.mcp.context import bind_project_root, reset_project_bindings_for_tests

    reset_project_bindings_for_tests()
    root = str((tmp_path / "repo").resolve())
    bind_project_root(root)
    seen = {}

    def fake_record(
        func,
        tool,
        args,
        kwargs,
        result,
        *,
        mcp_instructions=None,
        mcp_tool_catalog=None,
        resolved_project_root=None,
    ):
        seen["root"] = resolved_project_root

    def scoped_tool(project_root=None):
        return {"ok": True}

    monkeypatch.setattr(context_trace, "record_tool_delivery", fake_record)
    mcp_runtime._execute_local_tool(scoped_tool, "skill_get", (), {})
    assert seen["root"] == root
    reset_project_bindings_for_tests()


def test_context_report_cli_exports_one_portable_file(monkeypatch, tmp_path: Path):
    from typer.testing import CliRunner

    from ai_layer.cli.app import app

    repo, _ = _prepare(tmp_path, monkeypatch)

    def memory_context(task=None, project_root=None):
        return None

    context_trace.record_tool_delivery(
        memory_context,
        "memory_context",
        (),
        {"task": "Inspect token economy", "project_root": str(repo)},
        {
            "project_root": str(repo),
            "policy": "policy",
            "skill_access": {
                "routing_owner": "host-native",
                "automatic_domain_skill_injection": False,
            },
            "memory": [],
        },
        mcp_instructions="mcp",
    )
    exported = tmp_path / "portable-context-report.json"
    result = CliRunner().invoke(
        app,
        ["context-report", "--path", str(repo), "--output", str(exported)],
    )
    assert result.exit_code == 0, result.output
    assert exported.is_file()
    payload = json.loads(exported.read_text(encoding="utf-8"))
    assert payload["project"]["project_id"] == "p-context"
    assert payload["summary"]["tool_calls"]["memory_context"] == 1
