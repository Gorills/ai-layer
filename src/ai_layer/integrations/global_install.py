from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ai_layer import __version__
from ai_layer.agents.policy import install_cursor_profiles, remove_cursor_profiles
from ai_layer.core.config import get_settings
from ai_layer.core.paths import project_local_path
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
from ai_layer.integrations.install_journal import (
    INSTALL_OPERATION,
    INSTALL_PHASES,
    REMOVE_OPERATION,
    REMOVE_PHASES,
    begin_journal,
    complete_journal,
    fail_journal,
    journal_is_complete,
    record_phase,
)
from ai_layer.integrations.runtime_config import _global_bootstrap_workflow, _mcp_command, _server
from ai_layer.integrations.status import _json_ai_layer_server
from ai_layer.integrations.versioning import (
    GLOBAL_BOOTSTRAP_MARKER,
    GLOBAL_BOOTSTRAP_VERSION,
)
from ai_layer.skills.native import (
    assert_native_targets_available,
    remove_global_native_skills,
    sync_global_native_skills,
)
from ai_layer.skills.native_files import GLOBAL_NATIVE_ROOT_PARTS
from ai_layer.skills.service import list_skills

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _home_path(home: Path, *parts: str) -> Path:
    return project_local_path(home, *parts)


def _skip_symlink_home_path(home: Path, *parts: str) -> Path | None:
    try:
        return project_local_path(home, *parts)
    except RuntimeError as exc:
        if "symlink" not in str(exc).casefold():
            raise
        return None


def _cursor_plugin_owned(root: Path) -> bool:
    if root.is_symlink():
        return False
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


def _is_install_temp(path: Path) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and (path.name.startswith(".plugin.json.") or path.name.startswith(".ai-layer.mdc."))
    )


def _plugin_tree_reclaimable(root: Path) -> bool:
    if not root.exists():
        return True
    if root.is_symlink() or not root.is_dir():
        return False
    try:
        children = list(root.iterdir())
    except OSError:
        return False
    allowed = {".cursor-plugin", "rules"}
    for child in children:
        if _is_install_temp(child):
            continue
        if child.name not in allowed or child.is_symlink() or not child.is_dir():
            return False
        try:
            nested = list(child.iterdir())
        except OSError:
            return False
        for item in nested:
            if _is_install_temp(item):
                continue
            if item.is_symlink() or not item.is_file() or item.stat().st_size > 0:
                return False
    return True


def _cleanup_plugin_install_temps(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        return
    for path in (root, *root.rglob("*")):
        if _is_install_temp(path):
            path.unlink(missing_ok=True)


def _assert_cursor_plugin_safe(root: Path) -> None:
    if root.is_symlink():
        raise RuntimeError(f"Refusing AI Layer path redirected by symlink: {root}")
    if root.exists() and not _cursor_plugin_owned(root) and not _plugin_tree_reclaimable(root):
        raise RuntimeError(
            f"Integration ownership conflict: Cursor plugin directory {root} already exists and "
            "is not recognizably AI Layer-owned. It was left untouched."
        )


def _write_cursor_global_plugin(workflow: str, home: Path) -> Path:
    root = _home_path(home, ".cursor", "plugins", "local", "ai-layer-bootstrap")
    _assert_cursor_plugin_safe(root)
    _cleanup_plugin_install_temps(root)
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
        _home_path(
            home,
            ".cursor",
            "plugins",
            "local",
            "ai-layer-bootstrap",
            ".cursor-plugin",
            "plugin.json",
        ),
        json.dumps(manifest, indent=2) + "\n",
    )
    # No description: Cursor versions before 3.6 had a bug where a described alwaysApply plugin
    # rule could be downgraded to requestable. Keep this intentionally minimal.
    rule = "---\nalwaysApply: true\n---\n\n" + workflow
    _atomic_write_text(
        _home_path(
            home, ".cursor", "plugins", "local", "ai-layer-bootstrap", "rules", "ai-layer.mdc"
        ),
        rule,
    )
    return root


def _install_global_bootstrap_files(home: Path) -> dict:
    workflow = GLOBAL_BOOTSTRAP_MARKER + "\n" + _global_bootstrap_workflow()
    codex = _home_path(home, ".codex", "AGENTS.md")
    claude = _home_path(home, ".claude", "CLAUDE.md")
    gemini = _home_path(home, ".gemini", "GEMINI.md")
    _upsert_managed_markdown(codex, workflow)
    _upsert_managed_markdown(claude, workflow)
    _upsert_managed_markdown(gemini, workflow)
    cursor_plugin = _write_cursor_global_plugin(workflow, home)
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


def claude_user_mcp_status() -> dict:
    """Read-only Claude user-scope MCP presence. Missing CLI is not an install failure."""
    executable = shutil.which("claude")
    if not executable:
        return {
            "cli_available": False,
            "installed": False,
            "owned": False,
            "reason": "claude executable not found",
        }
    try:
        probe = subprocess.run(
            [executable, "mcp", "get", "ai-layer"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "cli_available": True,
            "installed": False,
            "owned": False,
            "executable": executable,
            "reason": type(exc).__name__,
        }
    combined = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if probe.returncode != 0:
        return {
            "cli_available": True,
            "installed": False,
            "owned": False,
            "executable": executable,
            "reason": "missing-or-unreadable",
        }
    owned = _claude_mcp_is_owned_output(combined)
    return {
        "cli_available": True,
        "installed": True,
        "owned": owned,
        "executable": executable,
        "reason": None if owned else "ownership-conflict",
    }


def _install_targets(home: Path) -> dict[str, Path]:
    return {
        "cursor": _home_path(home, ".cursor", "mcp.json"),
        "antigravity": _home_path(home, ".gemini", "config", "mcp_config.json"),
        "codex": _home_path(home, ".codex", "config.toml"),
        "cursor_plugin": _home_path(home, ".cursor", "plugins", "local", "ai-layer-bootstrap"),
        "cursor_agents": _home_path(home, ".cursor", "agents"),
    }


def _preflight_global_install(home: Path, targets: dict[str, Path], servers: dict) -> None:
    _assert_json_mcp_merge_safe(targets["cursor"], servers["cursor"])
    _assert_json_mcp_merge_safe(targets["antigravity"], servers["antigravity"])
    _assert_codex_merge_safe(targets["codex"])
    _assert_claude_user_mcp_safe()
    _assert_cursor_plugin_safe(targets["cursor_plugin"])
    _home_path(home, ".codex", "AGENTS.md")
    _home_path(home, ".claude", "CLAUDE.md")
    _home_path(home, ".gemini", "GEMINI.md")
    _home_path(home, ".cursor", "agents")
    for parts in GLOBAL_NATIVE_ROOT_PARTS.values():
        _home_path(home, *parts)
    for skill in list_skills():
        slug = str(skill.get("slug") or "")
        if skill.get("scope") == "global" and slug:
            assert_native_targets_available(slug, scope="global", home=home)


def _apply_install_phases(home: Path, targets: dict[str, Path], servers: dict) -> dict:
    _merge_mcp_json(targets["cursor"], servers["cursor"], backup=True)
    record_phase("mcp_cursor")
    _merge_mcp_json(targets["antigravity"], servers["antigravity"], backup=True)
    record_phase("mcp_antigravity")
    _merge_codex_config(
        targets["codex"], command=servers["codex"]["command"], client="codex", backup=True
    )
    record_phase("mcp_codex")
    claude_user_mcp = _install_claude_user_mcp(servers["claude"])
    degraded = None
    if not claude_user_mcp.get("installed"):
        degraded = str(claude_user_mcp.get("reason") or claude_user_mcp.get("error") or "degraded")
    record_phase("mcp_claude", degraded=degraded)
    bootstrap = _install_global_bootstrap_files(home)
    record_phase("bootstrap")
    cursor_agents = install_cursor_profiles(home)
    record_phase("cursor_profiles")
    native_skills = sync_global_native_skills(home=home)
    record_phase("native_skills")
    return {
        "claude_code": claude_user_mcp,
        "bootstrap": bootstrap,
        "cursor_agent_profiles": cursor_agents,
        "native_skills": native_skills,
    }


def install_global_integrations() -> dict:
    """Install user-level MCP registrations that do not need per-project paths.

    These configs use the stable absolute launcher path so GUI applications do not depend on
    the shell PATH inherited by the desktop process.
    """
    home = Path.home().expanduser().resolve()
    servers = {
        "cursor": _server(client="cursor"),
        "antigravity": _server(client="antigravity"),
        "codex": _server(client="codex"),
        "claude": _server(client="claude-code"),
    }
    targets = _install_targets(home)
    _preflight_global_install(home, targets, servers)
    begin_journal(INSTALL_OPERATION, phases=INSTALL_PHASES)
    try:
        record_phase("preflight")
        applied = _apply_install_phases(home, targets, servers)
        journal = complete_journal()
    except Exception as exc:
        try:
            fail_journal(str(exc))
        except Exception:
            pass
        raise
    return {
        "ok": journal_is_complete(journal, operation=INSTALL_OPERATION),
        "cursor": str(targets["cursor"]),
        "antigravity": str(targets["antigravity"]),
        "codex": str(targets["codex"]),
        "mcp_command": servers["cursor"]["command"],
        "journal": journal,
        **applied,
    }


def _remove_cursor_global_plugin(home: Path) -> dict:
    path = str(home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap")
    safe = _skip_symlink_home_path(home, ".cursor", "plugins", "local", "ai-layer-bootstrap")
    if safe is None:
        return {"removed": False, "reason": "symlink", "path": path}
    if not safe.exists():
        return {"removed": False, "reason": "missing"}
    if safe.is_symlink() or not _cursor_plugin_owned(safe):
        reason = "symlink" if safe.is_symlink() else "ownership-conflict"
        return {"removed": False, "reason": reason, "path": str(safe)}
    shutil.rmtree(safe)
    return {"removed": True, "path": str(safe)}


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


def _owned_json_server(path: Path | None) -> bool:
    if path is None:
        return False
    return _server_is_owned(_json_ai_layer_server(path))


def _remove_managed_path(path: Path | None, remover) -> None:
    if path is not None:
        remover(path)


def remove_global_integrations() -> dict:
    """Remove only globally installed material that carries AI Layer ownership evidence."""
    home = Path.home().expanduser().resolve()
    cursor = _skip_symlink_home_path(home, ".cursor", "mcp.json")
    antigravity = _skip_symlink_home_path(home, ".gemini", "config", "mcp_config.json")
    codex = _skip_symlink_home_path(home, ".codex", "config.toml")
    before = {
        "cursor_owned": _owned_json_server(cursor),
        "antigravity_owned": _owned_json_server(antigravity),
        "codex_owned": bool(
            codex is not None and codex.exists() and TOML_START in codex.read_text(encoding="utf-8")
        ),
    }
    begin_journal(REMOVE_OPERATION, phases=REMOVE_PHASES)
    try:
        _remove_managed_path(cursor, _remove_json_mcp)
        record_phase("mcp_cursor")
        _remove_managed_path(antigravity, _remove_json_mcp)
        record_phase("mcp_antigravity")
        _remove_managed_path(codex, _remove_codex_mcp)
        record_phase("mcp_codex")
        for parts in ((".codex", "AGENTS.md"), (".claude", "CLAUDE.md"), (".gemini", "GEMINI.md")):
            _remove_managed_path(_skip_symlink_home_path(home, *parts), _remove_managed_markdown)
        record_phase("bootstrap")
        plugin = _remove_cursor_global_plugin(home)
        record_phase("cursor_plugin")
        profiles = remove_cursor_profiles(home)
        record_phase("cursor_profiles")
        native_skills = remove_global_native_skills(home=home)
        record_phase("native_skills")
        claude_code = _remove_claude_user_mcp()
        record_phase("mcp_claude")
        journal = complete_journal()
    except Exception as exc:
        try:
            fail_journal(str(exc))
        except Exception:
            pass
        raise
    return {
        "ok": journal_is_complete(journal, operation=REMOVE_OPERATION),
        "removed": before,
        "cursor_plugin": plugin,
        "cursor_agent_profiles": profiles,
        "native_skills": native_skills,
        "claude_code": claude_code,
        "journal": journal,
    }
