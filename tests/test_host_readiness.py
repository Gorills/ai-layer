from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ai_layer.core.config import get_settings
from ai_layer.integrations.config_files import MANAGED_START, MCP_OWNER_KEY, MCP_OWNER_VALUE
from ai_layer.integrations.service import (
    global_integration_status,
    install_global_integrations,
    integration_status,
)
from ai_layer.integrations.status import _native_skill_catalog_status, provider_install_status
from ai_layer.integrations.versioning import GLOBAL_BOOTSTRAP_MARKER
from ai_layer.projections import dashboard_monitoring
from ai_layer.projections.dashboard_monitoring import monitoring_payload


def _isolate_home(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    executable = tmp_path / "ai-layer-mcp"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(executable))
    monkeypatch.setattr(
        "ai_layer.integrations.global_install.shutil.which",
        lambda name: None if name == "claude" else None,
    )
    get_settings.cache_clear()
    return home, project, executable


def _write_stale_descriptor(root: Path, *, version: int, slug: str = "django") -> Path:
    target = root / slug / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\n"
        f"name: {slug}\n"
        "description: leftover native descriptor\n"
        "---\n"
        f"<!-- AI-LAYER NATIVE SKILL v{version} scope=global project=- canonical={slug} -->\n",
        encoding="utf-8",
    )
    return target


def _write_owned_mcp(path: Path, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "ai-layer": {
                        "command": command,
                        "env": {MCP_OWNER_KEY: MCP_OWNER_VALUE},
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _write_claude_bootstrap(home: Path) -> None:
    path = home / ".claude" / "CLAUDE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{MANAGED_START}\n{GLOBAL_BOOTSTRAP_MARKER}\nbootstrap only\n", encoding="utf-8"
    )


def test_one_stale_native_descriptor_is_not_catalog_ready(tmp_path: Path, monkeypatch) -> None:
    home, _project, _executable = _isolate_home(tmp_path, monkeypatch)
    try:
        catalog_root = home / ".agents" / "skills"
        _write_stale_descriptor(catalog_root, version=2)
        catalog = _native_skill_catalog_status(catalog_root)
        assert catalog["owned_descriptors"] == 1
        assert catalog["expected_descriptors"] > 1
        assert catalog["ready"] is False
        assert catalog["status"] == "degraded"
    finally:
        get_settings.cache_clear()


def test_stale_v1_descriptor_does_not_count_as_current_catalog(tmp_path: Path, monkeypatch) -> None:
    home, _project, _executable = _isolate_home(tmp_path, monkeypatch)
    try:
        catalog_root = home / ".agents" / "skills"
        _write_stale_descriptor(catalog_root, version=1)
        catalog = _native_skill_catalog_status(catalog_root)
        assert catalog["owned_descriptors"] == 0
        assert catalog["expected_descriptors"] > 1
        assert catalog["ready"] is False
        assert catalog["status"] == "not_installed"
    finally:
        get_settings.cache_clear()


def test_one_stale_descriptor_does_not_make_cursor_ready(tmp_path: Path, monkeypatch) -> None:
    home, _project, executable = _isolate_home(tmp_path, monkeypatch)
    try:
        _write_owned_mcp(home / ".cursor" / "mcp.json", str(executable))
        _write_stale_descriptor(home / ".agents" / "skills", version=2)
        state = global_integration_status()
        native = state["cursor"]["native_skills"]
        assert native["owned_descriptors"] == 1
        assert native["expected_descriptors"] > 1
        assert native["ready"] is False
        assert state["cursor"]["mcp_ready"] is True
        assert state["cursor"]["ready"] is False
        assert state["cursor"]["status"] == "degraded"
    finally:
        get_settings.cache_clear()


def test_claude_bootstrap_only_is_not_ready(tmp_path: Path, monkeypatch) -> None:
    home, project, _executable = _isolate_home(tmp_path, monkeypatch)
    try:
        _write_claude_bootstrap(home)
        state = integration_status(project)
        claude = state["providers"]["claude-code"]
        assert claude["bootstrap"] is True
        assert claude["mcp"] is False
        assert claude["native_skills"] is False
        assert claude["ready"] is False
        assert claude["status"] == "degraded"
        assert claude["cli_available"] is False
    finally:
        get_settings.cache_clear()


def test_claude_bootstrap_plus_user_mcp_without_skills_is_not_ready(
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


def test_missing_optional_claude_cli_degrades_claude_not_other_hosts(
    tmp_path: Path, monkeypatch
) -> None:
    _home, project, _executable = _isolate_home(tmp_path, monkeypatch)
    try:
        installed = install_global_integrations()
        assert installed["claude_code"]["available"] is False
        assert installed["claude_code"]["installed"] is False
        state = global_integration_status()
        assert state["cursor"]["ready"] is True
        assert state["codex"]["ready"] is True
        assert state["antigravity"]["ready"] is True
        assert state["cursor"]["status"] == "ready"
        claude = state["claude-code"]
        assert claude["cli_available"] is False
        assert claude["mcp_ready"] is False
        assert claude["native_skills"]["ready"] is True
        assert claude["ready"] is False
        assert claude["status"] == "degraded"
        project_state = integration_status(project)
        assert project_state["providers"]["cursor"]["ready"] is True
        assert project_state["providers"]["codex"]["ready"] is True
        assert project_state["providers"]["antigravity"]["ready"] is True
        assert project_state["providers"]["claude-code"]["status"] == "degraded"
        assert project_state["providers"]["claude-code"]["ready"] is False
        assert project_state["ready"] is True
    finally:
        get_settings.cache_clear()


def test_empty_home_is_not_installed(tmp_path: Path, monkeypatch) -> None:
    _home, project, _executable = _isolate_home(tmp_path, monkeypatch)
    try:
        state = integration_status(project)
        for name in ("cursor", "codex", "antigravity", "claude-code"):
            provider = state["providers"][name]
            assert provider["ready"] is False
            assert provider["status"] == "not_installed"
        assert state["global"]["claude-code"]["status"] == "not_installed"
    finally:
        get_settings.cache_clear()


def test_provider_install_status_treats_none_as_absence() -> None:
    assert provider_install_status(True, None, None) == "degraded"
    assert provider_install_status(None, None, None) == "not_installed"
    assert provider_install_status(True, True, True) == "ready"
    assert provider_install_status(True, False, {"ready": True}) == "degraded"


def test_dashboard_does_not_mark_claude_ready_from_bootstrap_alone(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_monitoring,
        "global_integration_status",
        lambda: {
            "cursor": {"mcp_ready": False, "native_skills": {"ready": False}},
            "codex": {"mcp_ready": False, "native_skills": {"ready": False}},
            "antigravity": {"mcp_ready": False, "native_skills": {"ready": False}},
        },
    )
    monkeypatch.setattr(
        dashboard_monitoring,
        "global_bootstrap_status",
        lambda: {
            "cursor": {"ready": False},
            "codex": {"ready": False},
            "antigravity-gemini": {"ready": False},
            "claude-code": {"ready": True},
        },
    )
    monkeypatch.setattr(dashboard_monitoring, "project_options", lambda: [])
    payload = monitoring_payload()
    claude = next(item for item in payload["global"]["providers"] if item["name"] == "claude-code")
    assert claude["bootstrap_ready"] is True
    assert claude["mcp_ready"] is False
    assert claude["native_skills_ready"] is False
    assert claude["ready"] is False
    assert claude["status"] == "degraded"


def test_dashboard_core_hosts_stay_ready_when_claude_cli_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_monitoring,
        "global_integration_status",
        lambda: {
            "cursor": {"mcp_ready": True, "native_skills": {"ready": True}, "ready": True},
            "codex": {"mcp_ready": True, "native_skills": {"ready": True}, "ready": True},
            "antigravity": {"mcp_ready": True, "native_skills": {"ready": True}, "ready": True},
            "claude-code": {
                "mcp_ready": False,
                "native_skills": {"ready": True},
                "cli_available": False,
                "ready": False,
            },
        },
    )
    monkeypatch.setattr(
        dashboard_monitoring,
        "global_bootstrap_status",
        lambda: {
            "cursor": {"ready": True, "runtime_acceptance_required": True},
            "codex": {"ready": True},
            "antigravity-gemini": {"ready": True},
            "claude-code": {"ready": True},
        },
    )
    monkeypatch.setattr(dashboard_monitoring, "project_options", lambda: [])
    payload = monitoring_payload()
    by_name = {item["name"]: item for item in payload["global"]["providers"]}
    assert payload["global"]["ready"] is True
    assert by_name["cursor"]["status"] == "ready"
    assert by_name["codex"]["status"] == "ready"
    assert by_name["antigravity"]["status"] == "ready"
    assert by_name["claude-code"]["status"] == "degraded"
    assert by_name["claude-code"]["ready"] is False


def test_owned_claude_cli_mcp_can_make_claude_mcp_ready(tmp_path: Path, monkeypatch) -> None:
    home, project, executable = _isolate_home(tmp_path, monkeypatch)
    from ai_layer.integrations import global_install

    monkeypatch.setattr(global_install.shutil, "which", lambda name: "/fake/claude")

    def fake_run(command, **_kwargs):
        if command[1:4] == ["mcp", "get", "ai-layer"]:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    f"ai-layer:\n  Command: {executable}\n  {MCP_OWNER_KEY}: {MCP_OWNER_VALUE}\n"
                ),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr(global_install.subprocess, "run", fake_run)
    try:
        _write_claude_bootstrap(home)
        state = integration_status(project)
        claude = state["providers"]["claude-code"]
        assert claude["mcp"] is True
        assert claude["native_skills"] is False
        assert claude["status"] == "degraded"
        assert claude["cli_available"] is True
        assert state["global"]["claude-code"]["mcp_ready"] is True
    finally:
        get_settings.cache_clear()
