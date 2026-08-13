from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ai_layer import __version__
from ai_layer.agents.policy import install_cursor_profiles, remove_cursor_profiles
from ai_layer.core.config import get_settings
from ai_layer.integrations.config_files import (
    MCP_OWNER_KEY,
    MCP_OWNER_VALUE,
    TOML_START,
    _assert_codex_merge_safe,
    _assert_json_mcp_merge_safe,
    _atomic_write_text,
    _merge_mcp_json,
    _remove_codex_mcp,
    _remove_json_mcp,
    _remove_managed_markdown,
    _server_is_owned,
    _upsert_managed_markdown,
    _write_owned_text,
)
from ai_layer.integrations.config_files import (
    _merge_codex_config as _merge_codex_config_file,
)
from ai_layer.integrations.runtime_config import _global_bootstrap_workflow, _mcp_command, _server
from ai_layer.integrations.status import _json_ai_layer_server
from ai_layer.integrations.versioning import (
    GLOBAL_BOOTSTRAP_MARKER,
    GLOBAL_BOOTSTRAP_VERSION,
)
from ai_layer.skills.native import remove_global_native_skills, sync_global_native_skills

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _cursor_plugin_owned(root: Path) -> bool:
    manifest_path = root / ".cursor-plugin" / "plugin.json"
    if not root.exists():
        return True
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        manifest.get("name") == "ai-layer-bootstrap"
        and (manifest.get("author") or {}).get("name") == "Local AI Development Layer"
    )


def _assert_cursor_plugin_safe(root: Path) -> None:
    if root.exists() and not _cursor_plugin_owned(root):
        raise RuntimeError(
            f"Integration ownership conflict: Cursor plugin directory {root} already exists and "
            "is not recognizably AI Layer-owned. It was left untouched."
        )


def _write_cursor_global_plugin(workflow: str) -> Path:
    root = Path.home() / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    _assert_cursor_plugin_safe(root)
    manifest = {
        "name": "ai-layer-bootstrap",
        "displayName": "AI Layer Bootstrap",
        "version": __version__,
        "description": "Global bootstrap rule for registered Local AI Development Layer projects.",
        "author": {"name": "Local AI Development Layer"},
        "license": "UNLICENSED",
        "category": "developer-tools",
        "rules": "./rules/",
    }
    _atomic_write_text(
        root / ".cursor-plugin" / "plugin.json", json.dumps(manifest, indent=2) + "\n"
    )
    # No description: Cursor versions before 3.6 had a bug where a described alwaysApply plugin
    # rule could be downgraded to requestable. Keep this intentionally minimal.
    rule = "---\nalwaysApply: true\n---\n\n" + workflow
    _atomic_write_text(root / "rules" / "ai-layer.mdc", rule)
    return root


def _install_global_bootstrap_files() -> dict:
    workflow = GLOBAL_BOOTSTRAP_MARKER + "\n" + _global_bootstrap_workflow()
    home = Path.home()
    codex = home / ".codex" / "AGENTS.md"
    claude = home / ".claude" / "CLAUDE.md"
    gemini = home / ".gemini" / "GEMINI.md"
    _upsert_managed_markdown(codex, workflow)
    _upsert_managed_markdown(claude, workflow)
    _upsert_managed_markdown(gemini, workflow)
    cursor_plugin = _write_cursor_global_plugin(workflow)
    return {
        "version": GLOBAL_BOOTSTRAP_VERSION,
        "codex": str(codex),
        "claude-code": str(claude),
        "antigravity-gemini": str(gemini),
        "cursor_plugin": str(cursor_plugin),
        "cursor_requires_runtime_acceptance": True,
    }


def _merge_codex_config(
    path: Path,
    project_root: Path | None = None,
    *,
    command: str | None = None,
    client: str = "codex",
    backup: bool = False,
) -> None:
    _merge_codex_config_file(
        path,
        project_root,
        command=command or _mcp_command(),
        client=client,
        backup=backup,
    )


def _write_cursor_rule(path: Path, workflow: str) -> None:
    content = (
        "---\ndescription: Local AI Development Layer control plane\nalwaysApply: true\n---\n\n"
        + workflow
    )
    _write_owned_text(path, content)


def _claude_mcp_is_owned_output(output: str) -> bool:
    """Recognize current ownership markers and the exact legacy AI Layer launcher signature.

    v0.6.1 and earlier registered Claude's user-scope ``ai-layer`` server before the
    ``AI_LAYER_MANAGED_BY`` marker existed. During upgrade, that entry is still ours if
    ``claude mcp get ai-layer`` points at the stable/release AI Layer launcher. Treating it
    as an arbitrary same-name user collision makes a safe upgrade impossible.

    Unknown commands remain conflicts; only the product's launcher signature is adopted.
    """
    cleaned = _ANSI_ESCAPE_RE.sub("", output or "")
    if MCP_OWNER_KEY in cleaned and MCP_OWNER_VALUE in cleaned:
        return True

    command_values: set[str] = set()
    for pattern in (
        r'(?im)^\s*command\s*:\s*["\']?([^"\'\r\n]+?)["\']?\s*$',
        r'(?i)["\']command["\']\s*[:=]\s*["\']([^"\']+)["\']',
    ):
        command_values.update(
            match.strip() for match in re.findall(pattern, cleaned) if match.strip()
        )

    expected_commands = {
        _mcp_command(),
        str(get_settings().stable_mcp_executable),
        "ai-layer-mcp",
    }
    if command_values & expected_commands:
        return True

    # Older/dev installs could have stored an immutable release launcher instead of the
    # stable ``current`` symlink. This path is still unambiguously an AI Layer-owned binary.
    release_launcher = re.compile(
        r"^[^\s]*\.local/share/ai-layer/(?:current|releases/[^/\s]+)/bin/ai-layer-mcp$"
    )
    return any(release_launcher.match(command) for command in command_values)


def _assert_claude_user_mcp_safe() -> None:
    executable = shutil.which("claude")
    if not executable:
        return
    try:
        probe = subprocess.run(
            [executable, "mcp", "get", "ai-layer"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if probe.returncode != 0:
        return
    combined = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if not _claude_mcp_is_owned_output(combined):
        raise RuntimeError(
            "Integration ownership conflict: Claude already has an unmanaged MCP entry named "
            "ai-layer. AI Layer will not overwrite it."
        )


def _install_claude_user_mcp(server: dict) -> dict:
    executable = shutil.which("claude")
    if not executable:
        return {"installed": False, "available": False, "reason": "claude executable not found"}
    _assert_claude_user_mcp_safe()
    payload = {
        "type": "stdio",
        "command": server["command"],
        "args": server.get("args", []),
        "env": server.get("env", {}),
    }
    try:
        proc = subprocess.run(
            [
                executable,
                "mcp",
                "add-json",
                "ai-layer",
                json.dumps(payload, separators=(",", ":")),
                "--scope",
                "user",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "installed": False,
            "available": True,
            "executable": executable,
            "error": type(exc).__name__,
        }
    return {
        "installed": proc.returncode == 0,
        "available": True,
        "executable": executable,
        "error": proc.stderr.strip() if proc.returncode else None,
    }


def install_global_integrations() -> dict:
    """Install user-level MCP registrations that do not need per-project paths.

    These configs use the stable absolute launcher path so GUI applications do not depend on
    the shell PATH inherited by the desktop process.
    """
    home = Path.home()
    cursor_server = _server(client="cursor")
    antigravity_server = _server(client="antigravity")
    codex_server = _server(client="codex")
    claude_server = _server(client="claude-code")
    cursor = home / ".cursor" / "mcp.json"
    antigravity = home / ".gemini" / "config" / "mcp_config.json"
    codex = home / ".codex" / "config.toml"
    _assert_json_mcp_merge_safe(cursor, cursor_server)
    _assert_json_mcp_merge_safe(antigravity, antigravity_server)
    _assert_codex_merge_safe(codex)
    _assert_claude_user_mcp_safe()
    _assert_cursor_plugin_safe(home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap")
    _merge_mcp_json(cursor, cursor_server, backup=True)
    _merge_mcp_json(antigravity, antigravity_server, backup=True)
    _merge_codex_config(codex, command=codex_server["command"], client="codex", backup=True)
    claude_user_mcp = _install_claude_user_mcp(claude_server)
    bootstrap = _install_global_bootstrap_files()
    cursor_agents = install_cursor_profiles(home)
    native_skills = sync_global_native_skills(home=home)
    return {
        "cursor": str(cursor),
        "antigravity": str(antigravity),
        "codex": str(codex),
        "mcp_command": cursor_server["command"],
        "claude_code": claude_user_mcp,
        "bootstrap": bootstrap,
        "cursor_agent_profiles": cursor_agents,
        "native_skills": native_skills,
    }


def _remove_cursor_global_plugin() -> dict:
    root = Path.home() / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    if not root.exists():
        return {"removed": False, "reason": "missing"}
    if not _cursor_plugin_owned(root):
        return {"removed": False, "reason": "ownership-conflict", "path": str(root)}
    shutil.rmtree(root)
    return {"removed": True, "path": str(root)}


def _remove_claude_user_mcp() -> dict:
    executable = shutil.which("claude")
    if not executable:
        return {"removed": False, "available": False, "reason": "claude executable not found"}
    try:
        probe = subprocess.run(
            [executable, "mcp", "get", "ai-layer"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"removed": False, "available": True, "error": type(exc).__name__}
    combined = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if probe.returncode != 0:
        return {"removed": False, "available": True, "reason": "missing-or-unreadable"}
    if not _claude_mcp_is_owned_output(combined):
        return {
            "removed": False,
            "available": True,
            "reason": "ownership-conflict",
            "detail": "Claude MCP entry named ai-layer is neither marked nor recognizably legacy AI Layer-owned.",
        }
    try:
        proc = subprocess.run(
            [executable, "mcp", "remove", "ai-layer", "--scope", "user"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"removed": False, "available": True, "error": type(exc).__name__}
    return {
        "removed": proc.returncode == 0,
        "available": True,
        "error": proc.stderr.strip() if proc.returncode else None,
    }


def remove_global_integrations() -> dict:
    """Remove only globally installed material that carries AI Layer ownership evidence."""
    home = Path.home()
    cursor = home / ".cursor" / "mcp.json"
    antigravity = home / ".gemini" / "config" / "mcp_config.json"
    codex = home / ".codex" / "config.toml"
    before = {
        "cursor_owned": _server_is_owned(_json_ai_layer_server(cursor)),
        "antigravity_owned": _server_is_owned(_json_ai_layer_server(antigravity)),
        "codex_owned": codex.exists() and TOML_START in codex.read_text(encoding="utf-8"),
    }
    _remove_json_mcp(cursor)
    _remove_json_mcp(antigravity)
    _remove_codex_mcp(codex)
    for path in [
        home / ".codex" / "AGENTS.md",
        home / ".claude" / "CLAUDE.md",
        home / ".gemini" / "GEMINI.md",
    ]:
        _remove_managed_markdown(path)
    return {
        "removed": before,
        "cursor_plugin": _remove_cursor_global_plugin(),
        "cursor_agent_profiles": remove_cursor_profiles(home),
        "native_skills": remove_global_native_skills(home=home),
        "claude_code": _remove_claude_user_mcp(),
    }
