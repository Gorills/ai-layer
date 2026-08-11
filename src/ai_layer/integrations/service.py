from __future__ import annotations

from pathlib import Path

from ai_layer import __version__
from ai_layer.core.paths import project_local_path, project_mode
from ai_layer.integrations.config_files import (
    MANAGED_START,
    OWNED_FILE_MARKER,
    TOML_END,
    TOML_START,
    _assert_codex_merge_safe,
    _assert_json_mcp_merge_safe,
    _legacy_owned_file,
    _merge_mcp_json,
    _remove_codex_mcp,
    _remove_json_mcp,
    _remove_managed_markdown,
    _server_is_owned,
)
from ai_layer.integrations.global_install import (
    _cursor_plugin_owned,
    _merge_codex_config,
)
from ai_layer.integrations.runtime_config import _mcp_command, _server
from ai_layer.integrations.status import (
    IntegrationStatusDependencies,
)
from ai_layer.integrations.status import (
    global_bootstrap_status as _global_bootstrap_status,
)
from ai_layer.integrations.status import (
    global_integration_status as _global_integration_status,
)
from ai_layer.integrations.status import (
    integration_status as _integration_status,
)
from ai_layer.skills.native import (
    remove_legacy_project_bridge,
    remove_project_native_skills,
    sync_project_native_skills,
)

INTEGRATION_TEMPLATE_VERSION = 22
GLOBAL_BOOTSTRAP_VERSION = 9

LEGACY_PROJECT_RULE_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".cursor/rules/ai-layer.mdc",
    ".agents/rules/ai-layer.md",
)
PROJECT_MCP_PATHS = (
    ".cursor/mcp.json",
    ".mcp.json",
    ".codex/config.toml",
    ".agents/mcp_config.json",
)
PROJECT_INTEGRATION_PATHS = PROJECT_MCP_PATHS


def _preflight_project_integrations(
    root: Path, cursor_server: dict, claude_server: dict, antigravity_server: dict
) -> None:
    _assert_json_mcp_merge_safe(root / ".cursor" / "mcp.json", cursor_server)
    _assert_json_mcp_merge_safe(root / ".mcp.json", claude_server)
    _assert_codex_merge_safe(root / ".codex" / "config.toml")
    _assert_json_mcp_merge_safe(root / ".agents" / "mcp_config.json", antigravity_server)


def preflight_project_integrations(project_root: str | Path) -> None:
    """Validate reserved project integration targets without mutating the repository."""
    root = Path(project_root).expanduser().resolve()
    for relative in PROJECT_INTEGRATION_PATHS:
        project_local_path(root, relative)
    cursor_server = _server(project_root=root, client="cursor")
    claude_server = _server(project_root=root, client="claude-code")
    antigravity_server = _server(project_root=root, client="antigravity")
    _preflight_project_integrations(root, cursor_server, claude_server, antigravity_server)


def _remove_legacy_project_rule_bridges(root: Path) -> list[str]:
    removed: list[str] = []
    for relative in ("AGENTS.md", "CLAUDE.md", ".agents/rules/ai-layer.md"):
        target = root / relative
        before = target.exists()
        _remove_managed_markdown(target)
        if before and (
            not target.exists() or MANAGED_START not in target.read_text(encoding="utf-8")
        ):
            removed.append(relative)
    cursor_rule = root / ".cursor" / "rules" / "ai-layer.mdc"
    if cursor_rule.exists() and not cursor_rule.is_symlink():
        content = cursor_rule.read_text(encoding="utf-8")
        if OWNED_FILE_MARKER in content or _legacy_owned_file(cursor_rule, content):
            cursor_rule.unlink()
            removed.append(".cursor/rules/ai-layer.mdc")
    return removed


def install_project_integrations(project_root: str | Path) -> dict:
    """Install sparse workspace MCP bindings; static workflow is global-native, not duplicated per repository."""
    root = Path(project_root).expanduser().resolve()
    for relative in PROJECT_INTEGRATION_PATHS:
        project_local_path(root, relative)
    cursor_server = _server(project_root=root, client="cursor")
    claude_server = _server(project_root=root, client="claude-code")
    antigravity_server = _server(project_root=root, client="antigravity")
    _preflight_project_integrations(root, cursor_server, claude_server, antigravity_server)

    removed_rule_bridges = _remove_legacy_project_rule_bridges(root)
    _merge_mcp_json(root / ".cursor" / "mcp.json", cursor_server)
    _merge_mcp_json(root / ".mcp.json", claude_server)
    _merge_codex_config(
        root / ".codex" / "config.toml", root, command=cursor_server["command"], client="codex"
    )
    _merge_mcp_json(root / ".agents" / "mcp_config.json", antigravity_server)

    legacy_bridges_removed = remove_legacy_project_bridge(root)
    native_skills = sync_project_native_skills(root)
    return {
        "template_version": INTEGRATION_TEMPLATE_VERSION,
        "ai_layer_version": __version__,
        "bootstrap": "global-native",
        "rules": [],
        "removed_project_rule_bridges": removed_rule_bridges,
        "skills": native_skills,
        "legacy_skill_bridges_removed": legacy_bridges_removed,
        "mcp": [".cursor/mcp.json", ".mcp.json", ".codex/config.toml", ".agents/mcp_config.json"],
        "providers": ["cursor", "claude-code", "codex", "antigravity"],
        "mcp_command": cursor_server["command"],
    }


def remove_project_integrations(project_root: str | Path) -> dict:
    """Remove only AI Layer-owned project integration material, preserving user content.

    Resolve every managed path through project_local_path before the first mutation so cleanup
    cannot follow a repository-controlled symlink outside the selected project root.
    """
    root = Path(project_root).expanduser().resolve()
    targets = {
        relative: project_local_path(root, relative)
        for relative in PROJECT_MCP_PATHS + LEGACY_PROJECT_RULE_PATHS
    }
    _remove_managed_markdown(targets["AGENTS.md"])
    _remove_managed_markdown(targets["CLAUDE.md"])
    _remove_managed_markdown(targets[".agents/rules/ai-layer.md"])
    _remove_json_mcp(targets[".cursor/mcp.json"])
    _remove_json_mcp(targets[".mcp.json"])
    _remove_codex_mcp(targets[".codex/config.toml"])
    _remove_json_mcp(targets[".agents/mcp_config.json"])
    owned = [targets[".cursor/rules/ai-layer.mdc"]]
    for path in owned:
        if path.exists() and not path.is_symlink():
            content = path.read_text(encoding="utf-8")
            if OWNED_FILE_MARKER in content or _legacy_owned_file(path, content):
                path.unlink()
    # Remove only empty directories created solely for the bridge.
    for path in sorted({p.parent for p in owned}, key=lambda x: len(x.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    legacy_bridges = remove_legacy_project_bridge(root)
    native_skills = remove_project_native_skills(root)
    return {
        "root": str(root),
        "removed": True,
        "legacy_skill_bridges_removed": legacy_bridges,
        "native_skills": native_skills,
    }


def _status_dependencies() -> IntegrationStatusDependencies:
    return IntegrationStatusDependencies(
        mcp_command=_mcp_command,
        cursor_plugin_owned=_cursor_plugin_owned,
        server_is_owned=_server_is_owned,
        legacy_owned_file=_legacy_owned_file,
        project_local_path=project_local_path,
        project_mode=project_mode,
        managed_start=MANAGED_START,
        toml_start=TOML_START,
        toml_end=TOML_END,
        owned_file_marker=OWNED_FILE_MARKER,
        integration_template_version=INTEGRATION_TEMPLATE_VERSION,
        project_integration_paths=PROJECT_INTEGRATION_PATHS,
    )


def global_bootstrap_status() -> dict:
    return _global_bootstrap_status(_status_dependencies())


def global_integration_status() -> dict:
    return _global_integration_status(_status_dependencies())


def integration_status(project_root: str | Path) -> dict:
    return _integration_status(_status_dependencies(), project_root)
