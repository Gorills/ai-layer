from __future__ import annotations

import re
import runpy
import venv
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"runner replacement mismatch: {path}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def rewrite(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"generated test rewrite mismatch: {path}: {pattern[:80]}")
    file.write_text(updated, encoding="utf-8")


# The repository fast gate requires a real CPython 3.12 repository venv. The workflow already
# installs the branch's dev dependencies into the runner interpreter; expose them to the temporary
# venv instead of downloading the dependency graph twice.
venv.EnvBuilder(system_site_packages=True, with_pip=False).create(".venv")

helper = Path(".github/zero_footprint_migrate.py")
text = helper.read_text(encoding="utf-8")
old = r"def _archive_external_local_residue\(root: Path\) -> list\[str\]:.*?\n\ndef _archive_overlapping_state"
new = r"def _archive_external_local_residue\(root: Path\) -> list\[str\]:.*?\n\ndef repair_project"
if text.count(old) != 1:
    raise SystemExit("repair helper pattern marker mismatch")
helper.write_text(text.replace(old, new, 1), encoding="utf-8")
runpy.run_path(str(helper), run_name="__main__")

# The regex above consumes only the function name, leaving its signature in place. Put the name
# back before format/lint parse the generated source.
replace_once(
    "src/ai_layer/core/repair.py",
    "\n\n\n(root: str | Path, *, sync: bool = True) -> dict:\n",
    "\n\n\ndef repair_project(root: str | Path, *, sync: bool = True) -> dict:\n",
)

# The original materializer predates these tests and writes their embedded newline literals via
# ordinary triple-quoted strings. Rewrite only those generated functions with literal backslashes.
rewrite(
    "tests/test_integrations.py",
    r"def test_codex_legacy_project_disabled_mcp_does_not_override_global_config\(.*?\n\ndef test_codex_status_reads_active_codex_home",
    r'''def test_codex_legacy_project_disabled_mcp_does_not_override_global_config(
    tmp_path: Path, monkeypatch
):
    _home, project = _installed_health_fixture(tmp_path, monkeypatch)
    config = project / ".codex" / "config.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("args = []\n", "enabled = false\nargs = []\n", 1), encoding="utf-8"
    )

    state = integration_status(project)
    codex = state["providers"]["codex"]
    assert state["mode"] == "standard"
    assert state["repository_writes"] is False
    assert codex["ready"] is True
    assert codex["configuration_ready"] is True
    assert codex.get("mcp_reason") != "mcp_disabled"
    assert state["ready"] is True
    get_settings.cache_clear()


def test_codex_status_reads_active_codex_home''',
)
rewrite(
    "tests/test_integrations.py",
    r"def test_standard_sync_removes_legacy_repository_bindings\(.*?\n\ndef test_remove_project_integrations_preserves_user_content",
    r'''def test_standard_sync_removes_legacy_repository_bindings(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core import service as project_service
    from ai_layer.core.registry import register_project

    home = tmp_path / "home"
    project = tmp_path / "standard-project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(home / "bin" / "ai-layer-mcp"))
    (home / "bin").mkdir()
    (home / "bin" / "ai-layer-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
    (home / "bin" / "ai-layer-mcp").chmod(0o755)
    get_settings.cache_clear()
    try:
        register_project(project, "standard-id", "standard", mode="standard", provenance="allow")
        state_dir = home / ".ai-layer" / "projects" / "standard-id"
        state_dir.mkdir(parents=True)
        (state_dir / "project.yaml").write_text(
            "version: 2\n"
            "project_id: standard-id\n"
            "name: standard\n"
            f"root: {project.resolve()}\n"
            "mode: standard\n"
            "provenance: allow\n",
            encoding="utf-8",
        )
        install_global_integrations()
        install_project_integrations(project)
        assert (project / ".cursor" / "mcp.json").exists()
        assert (project / ".mcp.json").exists()

        monkeypatch.setattr(
            project_service,
            "sync_project_native_skills",
            lambda _root: {
                "repository_writes": False,
                "scope": "namespaced-global-zero-footprint",
            },
        )
        synced = project_service.sync_project_integrations(project)

        assert synced["mode"] == "standard"
        assert synced["repository_writes"] is False
        for rel in [".mcp.json", ".codex/config.toml", ".agents/mcp_config.json"]:
            assert not (project / rel).exists(), rel
        cursor = project / ".cursor" / "mcp.json"
        if cursor.exists():
            assert "ai-layer" not in json.loads(cursor.read_text(encoding="utf-8")).get(
                "mcpServers", {}
            )
        state = integration_status(project)
        assert state["mode"] == "standard"
        assert state["repository_writes"] is False
        assert state["ready"] is True
    finally:
        get_settings.cache_clear()


def test_remove_project_integrations_preserves_user_content''',
)
rewrite(
    "tests/test_privacy.py",
    r"def test_standard_state_is_external_to_repository\(.*?\n\ndef test_privacy_check_blocks_provenance_but_allows_legitimate_ai_domain_content",
    r'''def test_standard_state_is_external_to_repository(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "standard-project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project,
            "standard-project-id",
            "standard",
            mode="standard",
            provenance="allow",
        )
        meta = project_meta_dir(project)
        assert meta == (home / ".ai-layer" / "projects" / "standard-project-id").resolve()
        assert project not in meta.parents and meta != project
        assert not (project / ".ai-layer").exists()
    finally:
        get_settings.cache_clear()


def test_privacy_check_blocks_provenance_but_allows_legitimate_ai_domain_content''',
)
rewrite(
    "tests/test_repair.py",
    r"def test_repair_migrates_legacy_standard_state_and_removes_project_bindings\(.*?\n\ndef test_repair_moves_verified_strict_private_local_residue_out_of_repository",
    r'''def test_repair_migrates_legacy_standard_state_and_removes_project_bindings(
    tmp_path: Path, monkeypatch
):
    from ai_layer.integrations.service import install_project_integrations

    home = tmp_path / "home"
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(root, "p-standard", "repo", mode="standard", provenance="allow")
        local = root / ".ai-layer"
        (local / "memory").mkdir(parents=True)
        (local / "project.yaml").write_text(
            _project_yaml(root, "p-standard", mode="standard", provenance="allow"),
            encoding="utf-8",
        )
        (local / "memory" / "keep.txt").write_text("durable\n", encoding="utf-8")
        cursor = root / ".cursor" / "mcp.json"
        cursor.parent.mkdir(parents=True)
        cursor.write_text(
            '{"mcpServers":{"existing":{"command":"keep"}}}\n', encoding="utf-8"
        )
        install_project_integrations(root)

        result = repair_project(root, sync=False)

        destination = home / ".ai-layer" / "projects" / "p-standard"
        assert result["ok"] is True
        assert result["state_destination"] == str(destination)
        assert not local.exists()
        assert (destination / "project.yaml").exists()
        assert (destination / "memory" / "keep.txt").read_text(encoding="utf-8") == "durable\n"
        cursor_data = __import__("json").loads(cursor.read_text(encoding="utf-8"))
        assert cursor_data == {"mcpServers": {"existing": {"command": "keep"}}}
        assert not (root / ".mcp.json").exists()
        assert not (root / ".codex" / "config.toml").exists()
        assert not (root / ".agents" / "mcp_config.json").exists()
    finally:
        get_settings.cache_clear()


def test_repair_moves_verified_strict_private_local_residue_out_of_repository''',
)

replace_once(
    "src/ai_layer/core/repair.py",
    "from ai_layer.core.paths import project_config_path, project_local_path, project_mode\n",
    "from ai_layer.core.paths import project_local_path, project_mode\n",
)
