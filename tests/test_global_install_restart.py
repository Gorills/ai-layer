from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_layer.core.config import get_settings
from ai_layer.integrations import global_install as gi
from ai_layer.integrations.global_install import (
    install_global_integrations,
    remove_global_integrations,
)
from ai_layer.integrations.install_journal import (
    INSTALL_OPERATION,
    REMOVE_OPERATION,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    journal_is_complete,
    read_journal,
)


def _isolate_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    monkeypatch.setattr(gi.shutil, "which", lambda name: None)
    get_settings.cache_clear()
    return home


def test_global_install_refuses_symlinked_native_root_before_mcp_writes(
    tmp_path: Path, monkeypatch
) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    outside = tmp_path / "outside-agents"
    outside.mkdir()
    (home / ".agents").symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(RuntimeError, match="symlink"):
            install_global_integrations()
        assert not (home / ".cursor" / "mcp.json").exists()
        assert list(outside.iterdir()) == []
        assert read_journal() == {}
    finally:
        get_settings.cache_clear()


def test_remove_does_not_delete_native_skills_through_parent_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    outside = tmp_path / "outside-claude"
    skill = outside / "skills" / "django" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: django\n---\n"
        "<!-- AI-LAYER NATIVE SKILL v2 scope=global project=- canonical=django -->\n",
        encoding="utf-8",
    )
    (home / ".claude").symlink_to(outside, target_is_directory=True)
    try:
        result = remove_global_integrations()
        assert result["ok"] is True
        assert skill.read_text(encoding="utf-8").startswith("---\nname: django")
    finally:
        get_settings.cache_clear()


def test_truncated_cursor_profile_is_reclaimed(tmp_path: Path, monkeypatch) -> None:
    from ai_layer.agents.policy import OWNED_MARKER, install_cursor_profiles

    home = _isolate_home(tmp_path, monkeypatch)
    path = home / ".cursor" / "agents" / "ai-layer-economy-write.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: ai-layer-economy-write\n", encoding="utf-8")
    try:
        result = install_cursor_profiles(home)
        assert str(path) in result["written"]
        assert OWNED_MARKER in path.read_text(encoding="utf-8")
    finally:
        get_settings.cache_clear()


def test_complete_unmanaged_cursor_profile_is_not_overwritten(tmp_path: Path, monkeypatch) -> None:
    from ai_layer.agents.policy import install_cursor_profiles

    home = _isolate_home(tmp_path, monkeypatch)
    path = home / ".cursor" / "agents" / "ai-layer-economy-write.md"
    path.parent.mkdir(parents=True)
    original = "---\nname: ai-layer-economy-write\ndescription: mine\n---\n\nuser body\n"
    path.write_text(original, encoding="utf-8")
    try:
        result = install_cursor_profiles(home)
        assert str(path) in result["skipped_unmanaged"]
        assert path.read_text(encoding="utf-8") == original
    finally:
        get_settings.cache_clear()


def test_foreign_cursor_plugin_manifest_is_not_reclaimed(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    plugin = home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    manifest = plugin / ".cursor-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    original = '{"name":"other-plugin"}\n'
    manifest.write_text(original, encoding="utf-8")
    try:
        with pytest.raises(RuntimeError, match="ownership"):
            install_global_integrations()
        assert manifest.read_text(encoding="utf-8") == original
        assert read_journal() == {}
    finally:
        get_settings.cache_clear()


def test_empty_plugin_dir_and_staging_temp_are_reclaimed(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    plugin = home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    staged = plugin / ".cursor-plugin" / ".plugin.json.partial"
    staged.parent.mkdir(parents=True)
    staged.write_text("partial\n", encoding="utf-8")
    try:
        result = install_global_integrations()
        assert result["ok"] is True
        assert (plugin / ".cursor-plugin" / "plugin.json").is_file()
        assert not staged.exists()
    finally:
        get_settings.cache_clear()


def test_global_install_refuses_symlinked_cursor_home(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / ".cursor").symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(RuntimeError, match="symlink"):
            install_global_integrations()
        assert list(outside.iterdir()) == []
        assert read_journal() == {}
    finally:
        get_settings.cache_clear()


def test_crash_mid_install_is_not_success_and_restart_completes(
    tmp_path: Path, monkeypatch
) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    real_merge = gi._merge_mcp_json

    def crash_after_cursor(path, server, backup=False):
        if path.name == "mcp_config.json":
            raise RuntimeError("injected crash")
        return real_merge(path, server, backup=backup)

    monkeypatch.setattr(gi, "_merge_mcp_json", crash_after_cursor)
    try:
        with pytest.raises(RuntimeError, match="injected crash"):
            install_global_integrations()
        cursor = json.loads((home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert "ai-layer" in cursor["mcpServers"]
        assert not (home / ".gemini" / "config" / "mcp_config.json").exists()
        journal = read_journal()
        assert journal["status"] == STATUS_FAILED
        assert journal["operation"] == INSTALL_OPERATION
        assert "mcp_cursor" in journal["completed_phases"]
        assert "mcp_antigravity" not in journal["completed_phases"]
        assert journal_is_complete(journal, operation=INSTALL_OPERATION) is False

        monkeypatch.setattr(gi, "_merge_mcp_json", real_merge)
        result = install_global_integrations()
        assert result["ok"] is True
        antigravity = json.loads(
            (home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8")
        )
        assert "ai-layer" in antigravity["mcpServers"]
        completed = read_journal()
        assert completed["status"] == STATUS_COMPLETE
        assert journal_is_complete(completed, operation=INSTALL_OPERATION) is True
    finally:
        get_settings.cache_clear()


def test_machine_upgrade_clears_success_before_global_install_mutates(monkeypatch) -> None:
    import importlib

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    writes: list[dict] = []
    monkeypatch.setattr(cli, "_install_global_files", lambda force=False: {})
    monkeypatch.setattr(
        cli, "write_install_state", lambda payload: writes.append(dict(payload)) or payload
    )
    monkeypatch.setattr(
        cli,
        "install_global_integrations",
        lambda: (_ for _ in ()).throw(RuntimeError("crash")),
    )
    with pytest.raises(RuntimeError, match="crash"):
        cli._machine_upgrade(force=False, skip_db=True, sync_projects=False)
    assert writes
    assert writes[0]["last_upgrade_ok"] is False
    assert writes[0]["global_install"] == STATUS_IN_PROGRESS


def test_machine_upgrade_is_not_ok_when_global_install_journal_is_incomplete(
    monkeypatch,
) -> None:
    import importlib

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    monkeypatch.setattr(cli, "_install_global_files", lambda force=False: {})
    monkeypatch.setattr(cli, "install_global_integrations", lambda: {"ok": False})
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(cli, "write_install_state", lambda payload: payload)
    result = cli._machine_upgrade(force=False, skip_db=True, sync_projects=False)
    assert result["machine_upgrade_ok"] is False
    assert result["install_state"]["last_upgrade_ok"] is False


def test_remove_does_not_delete_through_symlinked_plugin(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    outside = tmp_path / "outside-plugin"
    outside.mkdir()
    secret = outside / "user-secret.txt"
    secret.write_text("keep\n", encoding="utf-8")
    plugin = home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    plugin.parent.mkdir(parents=True)
    plugin.symlink_to(outside, target_is_directory=True)
    manifest = outside / ".cursor-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "name": "ai-layer-bootstrap",
                "author": {"name": "Local AI Development Layer"},
            }
        ),
        encoding="utf-8",
    )
    try:
        result = remove_global_integrations()
        assert result["ok"] is True
        assert result["cursor_plugin"]["reason"] == "symlink"
        assert secret.read_text(encoding="utf-8") == "keep\n"
        assert plugin.is_symlink()
        assert manifest.exists()
    finally:
        get_settings.cache_clear()


def test_crash_mid_remove_is_restartable(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(tmp_path, monkeypatch)
    try:
        installed = install_global_integrations()
        assert installed["ok"] is True
        real_remove = gi._remove_json_mcp

        def crash_after_cursor(path):
            if path.name == "mcp_config.json":
                raise RuntimeError("injected uninstall crash")
            return real_remove(path)

        monkeypatch.setattr(gi, "_remove_json_mcp", crash_after_cursor)
        with pytest.raises(RuntimeError, match="injected uninstall crash"):
            remove_global_integrations()
        cursor_path = home / ".cursor" / "mcp.json"
        if cursor_path.exists():
            cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
            assert "ai-layer" not in cursor.get("mcpServers", {})
        antigravity = json.loads(
            (home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8")
        )
        assert "ai-layer" in antigravity["mcpServers"]
        journal = read_journal()
        assert journal["status"] == STATUS_FAILED
        assert journal["operation"] == REMOVE_OPERATION
        assert journal_is_complete(journal, operation=REMOVE_OPERATION) is False

        monkeypatch.setattr(gi, "_remove_json_mcp", real_remove)
        result = remove_global_integrations()
        assert result["ok"] is True
        leftover_path = home / ".gemini" / "config" / "mcp_config.json"
        if leftover_path.exists():
            leftover = json.loads(leftover_path.read_text(encoding="utf-8"))
            assert "ai-layer" not in leftover.get("mcpServers", {})
        assert journal_is_complete(operation=REMOVE_OPERATION) is True
    finally:
        get_settings.cache_clear()
