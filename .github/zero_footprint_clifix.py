from __future__ import annotations

import re
from pathlib import Path


def rewrite(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"cli-fix mismatch: {path}: {pattern[:100]!r}")
    file.write_text(updated, encoding="utf-8")


rewrite(
    "tests/test_cli.py",
    r"def test_audit_tail_cli_reads_privacy_minimal_events\(.*?\n\ndef test_audit_check_cli_validates_latest_completed_flow",
    r'''def test_audit_tail_cli_reads_privacy_minimal_events(tmp_path: Path, monkeypatch):
    from ai_layer.audit.service import mcp_audit
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    register_project(project, "audit-cli-tail", "audit-cli-tail")
    with mcp_audit(project, "memory_context", arg_keys=["task"]):
        pass
    result = CliRunner().invoke(app, ["audit", "tail", "--path", str(project), "--limit", "5"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["events"][0]["tool"] == "memory_context"
    assert payload["events"][0]["arg_keys"] == ["task"]


def test_audit_check_cli_validates_latest_completed_flow''',
)
rewrite(
    "tests/test_cli.py",
    r"def test_audit_check_cli_validates_latest_completed_flow\(.*?\n\ndef test_machine_upgrade_does_not_sync_projects_after_failed_migration",
    r'''def test_audit_check_cli_validates_latest_completed_flow(tmp_path: Path, monkeypatch):
    from ai_layer.audit.service import mcp_audit
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    register_project(project, "audit-cli-check", "audit-cli-check")
    with mcp_audit(project, "project_status", arg_keys=["task"]):
        pass
    with mcp_audit(project, "session_save", arg_keys=["goal", "current_state"]):
        pass
    result = CliRunner().invoke(app, ["audit", "check", "--path", str(project)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["flow_start_tool"] == "project_status"
    assert payload["project_status_calls"] == 1
    assert payload["memory_context_calls"] == 0
    assert payload["session_saved"] is True


def test_machine_upgrade_does_not_sync_projects_after_failed_migration''',
)
rewrite(
    "tests/test_cli.py",
    r"def test_audit_check_cli_treats_duplicate_context_as_tool_economy_warning\(.*?\n\ndef test_global_config_repairs_permissions_even_when_content_is_unchanged",
    r'''def test_audit_check_cli_treats_duplicate_context_as_tool_economy_warning(
    tmp_path: Path, monkeypatch
):
    from ai_layer.audit.service import mcp_audit
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    register_project(project, "audit-cli-economy", "audit-cli-economy")
    with mcp_audit(project, "project_status", arg_keys=[]):
        pass
    with mcp_audit(project, "memory_context", arg_keys=["task"]):
        pass
    with mcp_audit(project, "memory_context", arg_keys=["task"]):
        pass
    with mcp_audit(project, "session_save", arg_keys=["goal", "current_state"]):
        pass

    result = CliRunner().invoke(app, ["audit", "check", "--path", str(project)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["warnings"][0]["code"] == "tool_economy"


def test_global_config_repairs_permissions_even_when_content_is_unchanged''',
)
