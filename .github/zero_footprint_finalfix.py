from __future__ import annotations

import re
from pathlib import Path


def rewrite(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"final-fix mismatch: {path}: {pattern[:100]!r}")
    file.write_text(updated, encoding="utf-8")


rewrite(
    "tests/test_audit.py",
    r"def test_mcp_audit_records_call_without_argument_values\(.*?\n\ndef test_mcp_audit_records_error_type_and_reraises",
    r'''def test_mcp_audit_records_call_without_argument_values(monkeypatch, tmp_path: Path):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "audit-test", project.name)
    with mcp_audit(project, "memory_context", arg_keys=["task", "project_root"]):
        pass

    events = read_audit(project)
    assert len(events) == 1
    event = events[0]
    assert event["tool"] == "memory_context"
    assert event["ok"] is True
    assert event["arg_keys"] == ["project_root", "task"]
    path = audit_path(project)
    raw = path.read_text(encoding="utf-8")
    assert "secret prompt" not in raw
    assert ".ai-layer/projects/audit-test/audit/mcp.jsonl" in path.as_posix()
    assert not (project / ".ai-layer").exists()


def test_mcp_audit_records_error_type_and_reraises''',
)
rewrite(
    "tests/test_audit.py",
    r"def test_audit_event_identifies_server_version_and_pid\(.*?\n\ndef test_audit_check_fails_when_tool_error_occurs_inside_completed_flow",
    r'''def test_audit_event_identifies_server_version_and_pid(monkeypatch, tmp_path: Path):
    import os

    from ai_layer import __version__

    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project-version"
    project.mkdir()
    register_project(project, "audit-version", project.name)
    with mcp_audit(project, "memory_context", arg_keys=["task"]):
        pass
    event = read_audit(project)[0]
    assert event["server_version"] == __version__
    assert event["pid"] == os.getpid()


def test_audit_check_fails_when_tool_error_occurs_inside_completed_flow''',
)
rewrite(
    "tests/test_host_readiness.py",
    r"def test_claude_bootstrap_plus_mcp_without_skills_is_not_ready\(.*?\n\ndef test_missing_optional_claude_cli_degrades_claude_not_other_hosts",
    r'''def test_claude_bootstrap_plus_user_mcp_without_skills_is_not_ready(
    tmp_path: Path, monkeypatch
) -> None:
    home, project, _executable = _isolate_home(tmp_path, monkeypatch)
    try:
        _write_claude_bootstrap(home)
        monkeypatch.setattr(
            "ai_layer.integrations.service.claude_user_mcp_status",
            lambda: {
                "cli_available": True,
                "installed": True,
                "owned": True,
                "reason": None,
            },
        )
        state = integration_status(project)
        claude = state["providers"]["claude-code"]
        assert claude["bootstrap"] is True
        assert claude["mcp"] is True
        assert claude["native_skills"] is False
        assert claude["ready"] is False
        assert claude["status"] == "degraded"
        assert not (project / ".mcp.json").exists()
    finally:
        get_settings.cache_clear()


def test_missing_optional_claude_cli_degrades_claude_not_other_hosts''',
)
