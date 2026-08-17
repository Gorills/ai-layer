from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ai_layer.cli.doctor import _machine_issues
from ai_layer.core.config import get_settings
from ai_layer.integrations.service import (
    global_bootstrap_status,
    global_integration_status,
    install_global_integrations,
    install_project_integrations,
    integration_status,
)


def _runtime_home(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    executable = home / ".local" / "share" / "ai-layer" / "current" / "bin" / "ai-layer-mcp"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(executable))
    get_settings.cache_clear()
    return home, project


def test_cursor_configuration_stays_ready_but_runtime_is_unverified(tmp_path: Path, monkeypatch):
    _home, project = _runtime_home(tmp_path, monkeypatch)
    try:
        install_global_integrations()
        install_project_integrations(project)
        state = integration_status(project)
        cursor = state["providers"]["cursor"]

        assert cursor["configuration_ready"] is True
        assert cursor["ready"] is True
        assert cursor["ready_semantics"] == "configuration_only"
        assert cursor["runtime_assurance"] == "unknown"
        assert cursor["operational_status"] == "configured_unverified"
        assert state["configuration_ready"] is True
        assert state["ready"] is True
        assert state["operational_status"] == "configured_unverified"
    finally:
        get_settings.cache_clear()


def test_codex_nonempty_global_override_is_reported_as_blocking_bootstrap(
    tmp_path: Path, monkeypatch
):
    home, project = _runtime_home(tmp_path, monkeypatch)
    try:
        install_global_integrations()
        install_project_integrations(project)
        override = home / ".codex" / "AGENTS.override.md"
        override.write_text("# Temporary override\n", encoding="utf-8")

        bootstrap = global_bootstrap_status()["codex"]
        assert bootstrap["configuration_ready"] is True
        assert bootstrap["runtime_assurance"] == "blocked"
        assert bootstrap["runtime_reason"] == "shadowed_by_agents_override"
        assert bootstrap["operational_status"] == "blocked"

        provider = integration_status(project)["providers"]["codex"]
        assert provider["configuration_ready"] is True
        assert provider["operational_status"] == "blocked"
    finally:
        get_settings.cache_clear()


def test_codex_status_uses_codex_home_instead_of_false_positive_default_home(
    tmp_path: Path, monkeypatch
):
    home, _project = _runtime_home(tmp_path, monkeypatch)
    custom_codex_home = tmp_path / "custom-codex-home"
    monkeypatch.setenv("CODEX_HOME", str(custom_codex_home))
    try:
        install_global_integrations()
        bootstrap = global_bootstrap_status()["codex"]
        integrations = global_integration_status()["codex"]

        assert bootstrap["path"] == str(custom_codex_home.resolve() / "AGENTS.md")
        assert bootstrap["configuration_ready"] is False
        assert (home / ".codex" / "AGENTS.md").is_file()
        assert integrations["mcp_ready"] is False
    finally:
        get_settings.cache_clear()


def test_codex_enabled_false_is_not_reported_as_mcp_ready(tmp_path: Path, monkeypatch):
    home, _project = _runtime_home(tmp_path, monkeypatch)
    try:
        install_global_integrations()
        config = home / ".codex" / "config.toml"
        text = config.read_text(encoding="utf-8")
        config.write_text(
            text.replace("required = true\n", "required = true\nenabled = false\n", 1),
            encoding="utf-8",
        )

        assert global_integration_status()["codex"]["mcp_ready"] is False
    finally:
        get_settings.cache_clear()


def test_project_claude_mcp_without_host_probe_is_configured_unverified(
    tmp_path: Path, monkeypatch
):
    import ai_layer.integrations.global_install as global_install

    _home, project = _runtime_home(tmp_path, monkeypatch)
    monkeypatch.setattr(global_install.shutil, "which", lambda _name: None)
    try:
        install_global_integrations()
        install_project_integrations(project)
        provider = integration_status(project)["providers"]["claude-code"]

        assert provider["configuration_ready"] is True
        assert provider["runtime_assurance"] == "unknown"
        assert provider["runtime_reason"] == "project_mcp_requires_host_approval"
        assert provider["operational_status"] == "configured_unverified"
    finally:
        get_settings.cache_clear()


def test_doctor_distinguishes_runtime_unverified_from_known_bootstrap_block():
    machine = {
        "docker_compose": {"available": True},
        "global_integrations": {
            "cursor": {"configuration_ready": True, "ready": True},
            "codex": {"configuration_ready": True, "ready": True},
        },
        "global_bootstrap": {
            "cursor": {
                "configuration_ready": True,
                "ready": True,
                "operational_status": "configured_unverified",
                "runtime_reason": "host_runtime_acceptance_required",
            },
            "codex": {
                "configuration_ready": True,
                "ready": True,
                "operational_status": "blocked",
                "runtime_reason": "shadowed_by_agents_override",
            },
        },
        "mcp_processes": [],
        "service": {},
    }

    issues = _machine_issues(
        SimpleNamespace(version="0.14.0"),
        machine,
        runtime_ready=True,
        db_ready=True,
    )

    cursor = next(item for item in issues if "cursor bootstrap" in item["problem"])
    codex = next(item for item in issues if "codex bootstrap" in item["problem"])
    assert cursor["severity"] == "warning"
    assert codex["severity"] == "error"
    assert codex["details"]["reason"] == "shadowed_by_agents_override"
