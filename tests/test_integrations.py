import json
import tomllib
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.integrations.service import (
    INTEGRATION_TEMPLATE_VERSION,
    install_global_integrations,
    install_project_integrations,
    integration_status,
)


def test_provider_bootstrap_is_native_idempotent_and_preserves_existing(
    tmp_path: Path, monkeypatch
):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv(
        "AI_LAYER_MCP_EXECUTABLE", str(home / ".local/share/ai-layer/current/bin/ai-layer-mcp")
    )
    get_settings.cache_clear()

    (project / "AGENTS.md").write_text("# Existing Codex instructions\n", encoding="utf-8")
    (project / "CLAUDE.md").write_text("# Existing Claude instructions\n", encoding="utf-8")

    cursor_mcp = project / ".cursor" / "mcp.json"
    cursor_mcp.parent.mkdir(parents=True)
    cursor_mcp.write_text(
        json.dumps({"mcpServers": {"existing": {"command": "demo"}}}), encoding="utf-8"
    )

    codex_cfg = project / ".codex" / "config.toml"
    codex_cfg.parent.mkdir(parents=True)
    codex_cfg.write_text('model = "gpt-5.6"\n', encoding="utf-8")

    install_global_integrations()
    install_project_integrations(project)
    install_project_integrations(project)

    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# Existing Codex instructions\n"
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "# Existing Claude instructions\n"
    assert not (project / ".cursor" / "rules" / "ai-layer.mdc").exists()
    assert not (project / ".agents" / "rules" / "ai-layer.md").exists()

    expected_mcp = str(home / ".local/share/ai-layer/current/bin/ai-layer-mcp")
    cursor = json.loads(cursor_mcp.read_text(encoding="utf-8"))
    assert cursor["mcpServers"]["existing"]["command"] == "demo"
    assert cursor["mcpServers"]["ai-layer"]["command"] == expected_mcp
    assert cursor["mcpServers"]["ai-layer"]["env"]["AI_LAYER_PROJECT_ROOT"] == str(
        project.resolve()
    )
    assert cursor["mcpServers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "cursor"

    claude = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
    assert claude["mcpServers"]["ai-layer"]["command"] == expected_mcp
    assert claude["mcpServers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "claude-code"

    antigravity_workspace = json.loads(
        (project / ".agents" / "mcp_config.json").read_text(encoding="utf-8")
    )
    assert antigravity_workspace["mcpServers"]["ai-layer"]["command"] == expected_mcp
    assert antigravity_workspace["mcpServers"]["ai-layer"]["env"]["AI_LAYER_PROJECT_ROOT"] == str(
        project.resolve()
    )
    assert (
        antigravity_workspace["mcpServers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "antigravity"
    )

    with codex_cfg.open("rb") as handle:
        codex = tomllib.load(handle)
    assert codex["model"] == "gpt-5.6"
    assert codex["mcp_servers"]["ai-layer"]["command"] == expected_mcp
    assert codex["mcp_servers"]["ai-layer"]["required"] is True
    assert codex["mcp_servers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "codex"

    assert not (project / ".cursor" / "skills" / "ai-layer" / "SKILL.md").exists()
    assert not (project / ".claude" / "skills" / "ai-layer" / "SKILL.md").exists()
    assert not (project / ".agents" / "skills" / "ai-layer" / "SKILL.md").exists()
    shared_skill = home / ".agents" / "skills" / "django" / "SKILL.md"
    antigravity_skill = home / ".gemini" / "config" / "skills" / "django" / "SKILL.md"
    assert shared_skill.is_file()
    assert antigravity_skill.is_file()
    assert "name: django" in shared_skill.read_text(encoding="utf-8")
    shared_skill_text = shared_skill.read_text(encoding="utf-8")
    assert "## Core contract" in shared_skill_text
    assert "## Decision rules" in shared_skill_text
    assert "## Migrations" in shared_skill_text

    antigravity = json.loads(
        (home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8")
    )
    assert antigravity["mcpServers"]["ai-layer"]["command"] == expected_mcp
    assert antigravity["mcpServers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "antigravity"
    global_cursor = json.loads((home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert global_cursor["mcpServers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "cursor"
    assert (
        global_cursor["mcpServers"]["ai-layer"]["env"]["AI_LAYER_MANAGED_BY"]
        == "local-ai-development-layer"
    )
    for global_rule in [
        home / ".codex" / "AGENTS.md",
        home / ".claude" / "CLAUDE.md",
        home / ".gemini" / "GEMINI.md",
    ]:
        text = global_rule.read_text(encoding="utf-8")
        assert "project_status" in text
        assert "project_search" in text
        assert "host-native" in text.casefold()
        assert "memory_context(task=<actual user task>" not in text
        assert "Never stash, reset, restore, discard or commit user changes" in text
        assert "Current repository source is authoritative" in text
    cursor_plugin = home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    manifest = json.loads(
        (cursor_plugin / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "ai-layer-bootstrap"
    assert manifest["rules"] == "./rules/"
    assert "alwaysApply: true" in (cursor_plugin / "rules" / "ai-layer.mdc").read_text(
        encoding="utf-8"
    )

    state = integration_status(project)
    assert state["template_version"] == INTEGRATION_TEMPLATE_VERSION
    assert all(provider["ready"] for provider in state["providers"].values())
    assert state["ready_semantics"] == "configuration"
    cursor_state = state["providers"]["cursor"]
    assert cursor_state["ready"] is True
    assert cursor_state["configuration_ready"] is True
    assert cursor_state["runtime_assurance"]["state"] == "unverified"
    assert cursor_state["operational_status"] == "configured_unverified"
    get_settings.cache_clear()


def _installed_health_fixture(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    executable = home / "bin" / "ai-layer-mcp"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(executable))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    get_settings.cache_clear()
    install_global_integrations()
    install_project_integrations(project)
    return home, project


def test_codex_override_blocks_runtime_without_reclassifying_configuration(
    tmp_path: Path, monkeypatch
):
    home, project = _installed_health_fixture(tmp_path, monkeypatch)
    override = home / ".codex" / "AGENTS.override.md"
    override.write_text("# temporary override\n", encoding="utf-8")

    state = integration_status(project)
    codex = state["providers"]["codex"]
    assert codex["ready"] is True
    assert codex["configuration_ready"] is True
    assert codex["runtime_assurance"]["state"] == "blocked"
    assert codex["runtime_assurance"]["reason"] == "agents_override_shadows_global_bootstrap"
    assert codex["operational_status"] == "degraded"
    assert state["ready"] is True
    assert state["operational_status"] == "degraded"

    override.write_text("   \n", encoding="utf-8")
    recovered = integration_status(project)["providers"]["codex"]
    assert recovered["runtime_assurance"]["state"] == "unverified"
    get_settings.cache_clear()


def test_codex_project_disabled_mcp_is_not_masked_by_global_config(tmp_path: Path, monkeypatch):
    _home, project = _installed_health_fixture(tmp_path, monkeypatch)
    config = project / ".codex" / "config.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("args = []\n", "enabled = false\nargs = []\n", 1), encoding="utf-8"
    )

    state = integration_status(project)
    codex = state["providers"]["codex"]
    assert codex["ready"] is False
    assert codex["configuration_ready"] is False
    assert codex["mcp_reason"] == "mcp_disabled"
    assert codex["runtime_assurance"]["state"] == "blocked"
    assert state["ready"] is False
    get_settings.cache_clear()


def test_codex_status_reads_active_codex_home(tmp_path: Path, monkeypatch):
    home, project = _installed_health_fixture(tmp_path, monkeypatch)
    active = home / "custom-codex-home"
    active.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(active))

    state = integration_status(project)
    codex = state["providers"]["codex"]
    assert state["bootstrap"]["codex"]["path"] == str(active / "AGENTS.md")
    assert codex["bootstrap"] is False
    assert codex["configuration_ready"] is False
    get_settings.cache_clear()


def test_global_merge_preserves_unrelated_servers_and_creates_backup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    get_settings.cache_clear()
    cursor = home / ".cursor" / "mcp.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text(
        json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}), encoding="utf-8"
    )

    install_global_integrations()
    data = json.loads(cursor.read_text(encoding="utf-8"))
    assert data["mcpServers"]["github"]["command"] == "gh-mcp"
    assert data["mcpServers"]["ai-layer"]["command"] == "/stable/ai-layer-mcp"
    assert (cursor.parent / "mcp.json.ai-layer.bak").exists()
    get_settings.cache_clear()


def test_global_mcp_backup_is_private_and_preserves_existing_credentials(tmp_path: Path):
    from ai_layer.integrations.service import _merge_mcp_json

    target = tmp_path / "mcp.json"
    original = {
        "mcpServers": {
            "existing": {
                "command": "other-mcp",
                "env": {"SERVICE_TOKEN": "sensitive-existing-token"},
            }
        }
    }
    target.write_text(json.dumps(original), encoding="utf-8")

    _merge_mcp_json(target, {"command": "ai-layer-mcp", "args": [], "env": {}}, backup=True)

    backup = target.with_name("mcp.json.ai-layer.bak")
    backup_data = json.loads(backup.read_text(encoding="utf-8"))
    merged = json.loads(target.read_text(encoding="utf-8"))
    assert backup_data == original
    assert backup.stat().st_mode & 0o077 == 0
    assert merged["mcpServers"]["existing"] == original["mcpServers"]["existing"]
    assert merged["mcpServers"]["ai-layer"]["command"] == "ai-layer-mcp"


def test_unchanged_global_config_repairs_legacy_backup_permissions(tmp_path: Path):
    from ai_layer.integrations.service import _merge_mcp_json

    target = tmp_path / "mcp.json"
    server = {"command": "ai-layer-mcp", "args": [], "env": {}}
    content = {"mcpServers": {"ai-layer": server}}
    target.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    backup = target.with_name("mcp.json.ai-layer.bak")
    backup.write_text('{"secret":"legacy"}\n', encoding="utf-8")
    backup.chmod(0o644)

    _merge_mcp_json(target, server, backup=True)

    assert backup.read_text(encoding="utf-8") == '{"secret":"legacy"}\n'
    assert backup.stat().st_mode & 0o077 == 0


def test_global_bootstrap_is_complete_and_project_text_bridge_is_legacy_only(tmp_path: Path):
    from ai_layer.integrations.service import _workflow
    from ai_layer.integrations.templates import global_bootstrap_workflow

    legacy_bridge = _workflow(tmp_path)
    global_rule = global_bootstrap_workflow()
    assert "project binding (legacy compatibility)" in legacy_bridge
    assert "Mandatory engineering discipline" not in legacy_bridge
    assert "## AI Layer control-plane boundary" not in legacy_bridge
    assert "project_status" in global_rule
    assert "project_search" in global_rule
    assert "Current repository source is authoritative" in global_rule
    assert "Never stash, reset, restore, discard or commit user changes" in global_rule
    assert (
        "native read/edit/search/shell/test/subagent capabilities remain available"
        in global_rule.casefold()
    )
    assert "memory_context(task=<actual user task>" not in global_rule


def test_project_integrations_do_not_touch_user_agents_symlink(tmp_path: Path):
    from ai_layer.integrations.service import install_project_integrations

    outside = tmp_path.parent / "outside-agents.md"
    marker = "OUTSIDE_FILE_MUST_NOT_BE_COPIED"
    outside.write_text(marker + "\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").symlink_to(outside)

    install_project_integrations(tmp_path)
    assert outside.read_text(encoding="utf-8") == marker + "\n"
    assert (tmp_path / "AGENTS.md").is_symlink()
    assert (tmp_path / ".agents" / "mcp_config.json").exists()


def test_strict_private_integration_uses_global_bootstrap_and_no_project_files(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core.registry import register_project
    from ai_layer.integrations.service import remove_project_integrations

    home = tmp_path / "home"
    project = tmp_path / "private-project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(home / "bin" / "ai-layer-mcp"))
    (home / "bin").mkdir()
    (home / "bin" / "ai-layer-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
    get_settings.cache_clear()
    try:
        register_project(
            project, "private-id", "private", mode="strict-private", provenance="forbid"
        )
        install_global_integrations()
        remove_project_integrations(project)
        state = integration_status(project)
        assert state["mode"] == "strict-private"
        assert state["repository_writes"] is False
        assert state["providers"]["cursor"]["bootstrap"] is True
        assert state["providers"]["codex"]["bootstrap"] is True
        assert state["providers"]["antigravity"]["bootstrap"] is True
        assert state["cursor_runtime_acceptance_required"] is True
        for rel in [
            "AGENTS.md",
            "CLAUDE.md",
            ".cursor/rules/ai-layer.mdc",
            ".mcp.json",
            ".codex/config.toml",
            ".agents/rules/ai-layer.md",
        ]:
            assert not (project / rel).exists()
    finally:
        get_settings.cache_clear()


def test_remove_project_integrations_preserves_user_content(tmp_path: Path):
    from ai_layer.integrations.service import remove_project_integrations

    project = tmp_path / "project-cleanup"
    project.mkdir()
    (project / "AGENTS.md").write_text("# User rules\n", encoding="utf-8")
    install_project_integrations(project)
    remove_project_integrations(project)
    assert (project / "AGENTS.md").read_text(encoding="utf-8").strip() == "# User rules"
    assert not (project / ".cursor" / "rules" / "ai-layer.mdc").exists()


def test_remove_project_integrations_rejects_symlink_escape_before_mutation(tmp_path: Path):
    from ai_layer.integrations.service import remove_project_integrations

    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    marker = outside / "mcp.json"
    marker.write_text('{"mcpServers":{"ai-layer":{"command":"keep"}}}\n', encoding="utf-8")
    (project / ".cursor").symlink_to(outside, target_is_directory=True)

    import pytest

    with pytest.raises(RuntimeError, match="symlink"):
        remove_project_integrations(project)
    assert marker.read_text(encoding="utf-8") == '{"mcpServers":{"ai-layer":{"command":"keep"}}}\n'


def test_same_name_user_mcp_collision_is_never_overwritten(tmp_path: Path):
    from ai_layer.integrations.service import _merge_mcp_json

    target = tmp_path / "mcp.json"
    original = {"mcpServers": {"ai-layer": {"command": "user-owned-server", "args": []}}}
    target.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")

    try:
        _merge_mcp_json(target, {"command": "ai-layer-mcp", "args": [], "env": {}})
    except RuntimeError as exc:
        assert "ownership conflict" in str(exc).lower()
    else:
        raise AssertionError("same-name unmanaged MCP entry must block installation")

    assert json.loads(target.read_text(encoding="utf-8")) == original


def test_codex_same_name_user_table_is_not_duplicated(tmp_path: Path):
    from ai_layer.integrations.service import _merge_codex_config

    target = tmp_path / "config.toml"
    original = '[mcp_servers.ai-layer]\ncommand = "user-mcp"\n'
    target.write_text(original, encoding="utf-8")

    try:
        _merge_codex_config(target, command="ai-layer-mcp")
    except RuntimeError as exc:
        assert "ownership conflict" in str(exc).lower()
    else:
        raise AssertionError("unmanaged Codex ai-layer table must block installation")

    assert target.read_text(encoding="utf-8") == original
    with target.open("rb") as handle:
        assert tomllib.load(handle)["mcp_servers"]["ai-layer"]["command"] == "user-mcp"


def test_user_owned_legacy_rule_is_preserved_and_not_reserved(tmp_path: Path):
    from ai_layer.integrations.service import install_project_integrations

    rule = tmp_path / ".cursor" / "rules" / "ai-layer.mdc"
    rule.parent.mkdir(parents=True)
    rule.write_text("user-owned rule\n", encoding="utf-8")

    result = install_project_integrations(tmp_path)
    assert rule.read_text(encoding="utf-8") == "user-owned rule\n"
    assert result["rules"] == []
    assert (tmp_path / ".cursor" / "mcp.json").exists()


def test_project_remove_is_symmetric_and_cleans_antigravity_rule(tmp_path: Path, monkeypatch):
    from ai_layer.integrations.service import remove_project_integrations

    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    get_settings.cache_clear()
    try:
        (project / "AGENTS.md").write_text("# User AGENTS\n", encoding="utf-8")
        (project / "CLAUDE.md").write_text("# User CLAUDE\n", encoding="utf-8")
        install_project_integrations(project)
        assert (project / ".agents" / "mcp_config.json").exists()
        assert not (project / ".agents" / "rules" / "ai-layer.md").exists()

        remove_project_integrations(project)

        assert (project / "AGENTS.md").read_text(encoding="utf-8").strip() == "# User AGENTS"
        assert (project / "CLAUDE.md").read_text(encoding="utf-8").strip() == "# User CLAUDE"
        for rel in [
            ".cursor/rules/ai-layer.mdc",
            ".cursor/skills/ai-layer/SKILL.md",
            ".claude/skills/ai-layer/SKILL.md",
            ".agents/rules/ai-layer.md",
            ".agents/skills/ai-layer/SKILL.md",
        ]:
            assert not (project / rel).exists(), rel
        if (project / ".cursor" / "mcp.json").exists():
            assert (
                "ai-layer"
                not in json.loads((project / ".cursor" / "mcp.json").read_text())["mcpServers"]
            )
        assert not (project / ".mcp.json").exists()
        assert not (project / ".codex" / "config.toml").exists()
        assert not (project / ".agents" / "mcp_config.json").exists()
    finally:
        get_settings.cache_clear()


def test_global_remove_is_symmetric_and_preserves_unrelated_content(tmp_path: Path, monkeypatch):
    from ai_layer.integrations import service as integrations

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    monkeypatch.setattr(
        integrations.shutil, "which", lambda name: None if name == "claude" else None
    )
    get_settings.cache_clear()
    try:
        cursor = home / ".cursor" / "mcp.json"
        cursor.parent.mkdir(parents=True)
        cursor.write_text(
            json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}), encoding="utf-8"
        )
        codex = home / ".codex" / "config.toml"
        codex.parent.mkdir(parents=True)
        codex.write_text('model = "gpt-5.6"\n', encoding="utf-8")
        agents = home / ".codex" / "AGENTS.md"
        agents.write_text("# User global rules\n", encoding="utf-8")

        install_global_integrations()
        assert integrations.global_integration_status()["cursor"]["ready"] is True
        assert (home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap").exists()

        integrations.remove_global_integrations()

        cursor_data = json.loads(cursor.read_text(encoding="utf-8"))
        assert cursor_data == {"mcpServers": {"github": {"command": "gh-mcp"}}}
        assert codex.read_text(encoding="utf-8").strip() == 'model = "gpt-5.6"'
        assert agents.read_text(encoding="utf-8").strip() == "# User global rules"
        assert not (home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap").exists()
        assert integrations.global_integration_status()["cursor"]["ready"] is False
    finally:
        get_settings.cache_clear()


def test_unowned_legacy_rule_does_not_count_as_ai_layer_bootstrap(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    get_settings.cache_clear()
    try:
        rule = project / ".cursor" / "rules" / "ai-layer.mdc"
        rule.parent.mkdir(parents=True)
        rule.write_text("user-owned rule\n", encoding="utf-8")
        state = integration_status(project)
        assert state["providers"]["cursor"]["bootstrap"] is False
        assert state["providers"]["cursor"]["ready"] is False
        assert rule.read_text(encoding="utf-8") == "user-owned rule\n"
    finally:
        get_settings.cache_clear()


def test_integration_status_requires_an_actual_executable(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    candidate = tmp_path / "ai-layer-mcp"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(candidate))
    get_settings.cache_clear()
    try:
        candidate.mkdir()
        assert integration_status(project)["mcp_executable_ready"] is False
        candidate.rmdir()
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o600)
        assert integration_status(project)["mcp_executable_ready"] is False
        candidate.chmod(0o700)
        assert integration_status(project)["mcp_executable_ready"] is True
    finally:
        get_settings.cache_clear()


def test_integration_status_fails_closed_on_invalid_utf8_managed_files(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    executable = tmp_path / "ai-layer-mcp"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(executable))
    get_settings.cache_clear()
    try:
        install_global_integrations()
        install_project_integrations(project)
        (project / ".codex" / "config.toml").write_bytes(b"\xff\xfe\x00")
        state = integration_status(project)
        assert state["providers"]["claude-code"]["bootstrap"] is True
        assert state["providers"]["codex"]["mcp"] is True  # global MCP remains a valid fallback
        assert state["providers"]["cursor"]["bootstrap"] is True
    finally:
        get_settings.cache_clear()


def test_global_upgrade_adopts_legacy_claude_ai_layer_entry(tmp_path: Path, monkeypatch):
    """Pre-marker v0.6.1 Claude entries must upgrade instead of being treated as user collisions."""
    from types import SimpleNamespace

    from ai_layer.integrations import service as integrations

    home = tmp_path / "home"
    home.mkdir()
    stable = home / ".local/share/ai-layer/current/bin/ai-layer-mcp"
    stable.parent.mkdir(parents=True)
    stable.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(stable))
    monkeypatch.setattr(
        integrations.shutil, "which", lambda name: "/fake/claude" if name == "claude" else None
    )
    get_settings.cache_clear()

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:4] == ["mcp", "get", "ai-layer"]:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "ai-layer:\n"
                    "  Scope: User\n"
                    f"  Command: {stable}\n"
                    "  Environment:\n"
                    "    AI_LAYER_CLIENT=claude-code\n"
                ),
                stderr="",
            )
        if command[1:4] == ["mcp", "add-json", "ai-layer"]:
            payload = json.loads(command[4])
            assert payload["command"] == str(stable)
            assert payload["env"]["AI_LAYER_CLIENT"] == "claude-code"
            assert payload["env"]["AI_LAYER_MANAGED_BY"] == "local-ai-development-layer"
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(integrations.subprocess, "run", fake_run)
    try:
        result = integrations.install_global_integrations()
        assert result["claude_code"]["installed"] is True
        assert any(call[1:4] == ["mcp", "add-json", "ai-layer"] for call in calls)
    finally:
        get_settings.cache_clear()


def test_claude_same_name_unknown_command_still_blocks_upgrade(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from ai_layer.integrations import service as integrations

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    monkeypatch.setattr(
        integrations.shutil, "which", lambda name: "/fake/claude" if name == "claude" else None
    )
    get_settings.cache_clear()

    def fake_run(command, **kwargs):
        if command[1:4] == ["mcp", "get", "ai-layer"]:
            return SimpleNamespace(
                returncode=0,
                stdout="ai-layer:\n  Command: /opt/user/custom-server\n",
                stderr="",
            )
        raise AssertionError("unknown Claude entry must block before add-json")

    monkeypatch.setattr(integrations.subprocess, "run", fake_run)
    try:
        import pytest

        with pytest.raises(RuntimeError, match="ownership conflict"):
            integrations.install_global_integrations()
    finally:
        get_settings.cache_clear()


def test_remove_global_integrations_can_clean_legacy_claude_entry(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from ai_layer.integrations import service as integrations

    home = tmp_path / "home"
    home.mkdir()
    stable = home / ".local/share/ai-layer/current/bin/ai-layer-mcp"
    stable.parent.mkdir(parents=True)
    stable.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(stable))
    monkeypatch.setattr(
        integrations.shutil, "which", lambda name: "/fake/claude" if name == "claude" else None
    )
    get_settings.cache_clear()

    removed = False

    def fake_run(command, **kwargs):
        nonlocal removed
        if command[1:4] == ["mcp", "get", "ai-layer"]:
            return SimpleNamespace(returncode=0, stdout=f"Command: {stable}\n", stderr="")
        if command[1:4] == ["mcp", "remove", "ai-layer"]:
            removed = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(integrations.subprocess, "run", fake_run)
    try:
        result = integrations.remove_global_integrations()
        assert result["claude_code"]["removed"] is True
        assert removed is True
    finally:
        get_settings.cache_clear()


def test_external_integration_uses_machine_bootstrap_without_project_files(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core.registry import register_project
    from ai_layer.integrations.service import remove_project_integrations

    home = tmp_path / "home-external"
    project = tmp_path / "external-project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(home / "bin" / "ai-layer-mcp"))
    (home / "bin").mkdir()
    executable = home / "bin" / "ai-layer-mcp"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    get_settings.cache_clear()
    try:
        register_project(project, "external-id", "external", mode="external", provenance="allow")
        install_global_integrations()
        remove_project_integrations(project)
        state = integration_status(project)
        assert state["mode"] == "external"
        assert state["repository_writes"] is False
        assert state["providers"]["cursor"]["bootstrap"] is True
        assert state["providers"]["codex"]["bootstrap"] is True
        assert state["providers"]["antigravity"]["bootstrap"] is True
        for rel in [
            "AGENTS.md",
            "CLAUDE.md",
            ".cursor/rules/ai-layer.mdc",
            ".mcp.json",
            ".codex/config.toml",
        ]:
            assert not (project / rel).exists()
    finally:
        get_settings.cache_clear()
