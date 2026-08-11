from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class IntegrationStatusDependencies:
    mcp_command: Callable[[], str]
    cursor_plugin_owned: Callable[[Path], bool]
    server_is_owned: Callable[[dict | None], bool]
    legacy_owned_file: Callable[[Path, str], bool]
    project_local_path: Callable[[Path, str], Path]
    project_mode: Callable[[Path], str]
    managed_start: str
    toml_start: str
    toml_end: str
    owned_file_marker: str
    integration_template_version: int
    project_integration_paths: tuple[str, ...]


def _bootstrap_file_status(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        return deps.managed_start in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def global_bootstrap_status(deps: IntegrationStatusDependencies) -> dict:
    home = Path.home()
    plugin = home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    cursor_manifest = plugin / ".cursor-plugin" / "plugin.json"
    cursor_rule = plugin / "rules" / "ai-layer.mdc"
    return {
        "codex": {
            "path": str(home / ".codex" / "AGENTS.md"),
            "ready": _bootstrap_file_status(home / ".codex" / "AGENTS.md", deps),
            "verified_by": "documented user-level AGENTS.md",
        },
        "claude-code": {
            "path": str(home / ".claude" / "CLAUDE.md"),
            "ready": _bootstrap_file_status(home / ".claude" / "CLAUDE.md", deps),
            "verified_by": "documented user memory file",
        },
        "antigravity-gemini": {
            "path": str(home / ".gemini" / "GEMINI.md"),
            "ready": _bootstrap_file_status(home / ".gemini" / "GEMINI.md", deps),
            "verified_by": "documented global context file",
        },
        "cursor": {
            "path": str(plugin),
            "ready": deps.cursor_plugin_owned(plugin) and cursor_manifest.exists() and cursor_rule.exists(),
            "verified_by": "owned local plugin files present; runtime black-box acceptance required",
            "runtime_acceptance_required": True,
        },
    }


def _json_ai_layer_server(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    server = data.get("mcpServers", {}).get("ai-layer")
    return server if isinstance(server, dict) else None


def _json_has_ai_layer(path: Path, deps: IntegrationStatusDependencies) -> bool:
    server = _json_ai_layer_server(path)
    return bool(server and server.get("command") and deps.server_is_owned(server))


def _codex_has_ai_layer(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return (
        deps.toml_start in text
        and deps.toml_end in text
        and "[mcp_servers.ai-layer]" in text
        and "command = " in text
    )


def _native_skill_catalog_status(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        return {"path": str(root), "ready": False, "owned_descriptors": 0}
    count = 0
    for child in root.iterdir():
        target = child / "SKILL.md" if child.is_dir() and not child.is_symlink() else None
        if target is None or not target.is_file() or target.is_symlink():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "<!-- AI-LAYER NATIVE SKILL v1 scope=global " in content:
            count += 1
    return {"path": str(root), "ready": count > 0, "owned_descriptors": count}


def global_integration_status(deps: IntegrationStatusDependencies) -> dict:
    home = Path.home()
    targets = {
        "cursor": home / ".cursor" / "mcp.json",
        "antigravity": home / ".gemini" / "config" / "mcp_config.json",
        "codex": home / ".codex" / "config.toml",
    }
    shared_native = _native_skill_catalog_status(home / ".agents" / "skills")
    antigravity_native = _native_skill_catalog_status(home / ".gemini" / "config" / "skills")
    cursor_mcp = _json_has_ai_layer(targets["cursor"], deps)
    antigravity_mcp = _json_has_ai_layer(targets["antigravity"], deps)
    codex_mcp = _codex_has_ai_layer(targets["codex"], deps)
    return {
        "cursor": {
            "path": str(targets["cursor"]),
            "mcp_ready": cursor_mcp,
            "native_skills": shared_native,
            "ready": bool(cursor_mcp and shared_native["ready"]),
        },
        "antigravity": {
            "path": str(targets["antigravity"]),
            "mcp_ready": antigravity_mcp,
            "native_skills": antigravity_native,
            "ready": bool(antigravity_mcp and antigravity_native["ready"]),
        },
        "codex": {
            "path": str(targets["codex"]),
            "mcp_ready": codex_mcp,
            "native_skills": shared_native,
            "ready": bool(codex_mcp and shared_native["ready"]),
        },
    }


def _owned_file_ready(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists() or path.is_symlink():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return deps.owned_file_marker in content or deps.legacy_owned_file(path, content)


def _managed_block_ready(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return deps.managed_start in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _command_ready(command: str) -> bool:
    candidate = Path(command).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        return candidate.is_file() and not candidate.is_symlink() and os.access(candidate, os.X_OK)
    return bool(shutil.which(command))


def _external_status(
    root: Path, deps: IntegrationStatusDependencies, *, mode: str, executable: str, executable_ready: bool, global_state: dict
) -> dict:
    bootstrap = global_bootstrap_status(deps)
    providers = {
        "cursor": {
            "bootstrap": bootstrap["cursor"]["ready"],
            "mcp": global_state["cursor"]["mcp_ready"],
            "native_skills": global_state["cursor"]["native_skills"]["ready"],
            "runtime_acceptance_required": True,
        },
        "codex": {
            "bootstrap": bootstrap["codex"]["ready"],
            "mcp": global_state["codex"]["mcp_ready"],
            "native_skills": global_state["codex"]["native_skills"]["ready"],
        },
        "antigravity": {
            "bootstrap": bootstrap["antigravity-gemini"]["ready"],
            "mcp": global_state["antigravity"]["mcp_ready"],
            "native_skills": global_state["antigravity"]["native_skills"]["ready"],
        },
        "claude-code": {"bootstrap": bootstrap["claude-code"]["ready"], "mcp": None, "note": "user-scope MCP is installed through the Claude CLI when available"},
    }
    for name, state in providers.items():
        if name == "claude-code":
            state["ready"] = bool(state["bootstrap"])
        else:
            state["ready"] = bool(state["bootstrap"] and state["mcp"] and state["native_skills"])
    return {
        "project_root": str(root),
        "mode": mode,
        "repository_writes": False,
        "mcp_executable": executable,
        "mcp_executable_ready": executable_ready,
        "template_version": deps.integration_template_version,
        "global": global_state,
        "bootstrap": bootstrap,
        "providers": providers,
        "ready": executable_ready and all(providers[name]["ready"] for name in ("cursor", "codex", "antigravity")),
        "cursor_runtime_acceptance_required": True,
    }


def integration_status(deps: IntegrationStatusDependencies, project_root: str | Path) -> dict:
    root = Path(project_root).expanduser().resolve()
    global_state = global_integration_status(deps)
    executable = deps.mcp_command()
    executable_ready = _command_ready(executable)
    mode = deps.project_mode(root)
    if mode in {"external", "strict-private"}:
        return _external_status(
            root, deps, mode=mode, executable=executable, executable_ready=executable_ready, global_state=global_state
        )
    try:
        targets = {relative: deps.project_local_path(root, relative) for relative in deps.project_integration_paths}
    except RuntimeError as exc:
        return {
            "project_root": str(root),
            "mcp_executable": executable,
            "mcp_executable_ready": executable_ready,
            "template_version": deps.integration_template_version,
            "global": global_state,
            "providers": {},
            "ready": False,
            "unsafe_path": str(exc),
        }

    bootstrap = global_bootstrap_status(deps)
    providers = {
        "cursor": {
            "bootstrap": bootstrap["cursor"]["ready"],
            "mcp": _json_has_ai_layer(targets[".cursor/mcp.json"], deps) or global_state["cursor"]["mcp_ready"],
            "native_skills": global_state["cursor"]["native_skills"]["ready"],
        },
        "claude-code": {
            "bootstrap": bootstrap["claude-code"]["ready"],
            "mcp": _json_has_ai_layer(targets[".mcp.json"], deps),
        },
        "codex": {
            "bootstrap": bootstrap["codex"]["ready"],
            "mcp": _codex_has_ai_layer(targets[".codex/config.toml"], deps) or global_state["codex"]["mcp_ready"],
            "native_skills": global_state["codex"]["native_skills"]["ready"],
        },
        "antigravity": {
            "bootstrap": bootstrap["antigravity-gemini"]["ready"],
            "mcp": _json_has_ai_layer(targets[".agents/mcp_config.json"], deps) or global_state["antigravity"]["mcp_ready"],
            "native_skills": global_state["antigravity"]["native_skills"]["ready"],
        },
    }
    for state in providers.values():
        state["ready"] = all(bool(value) for key, value in state.items() if key != "ready")
    return {
        "project_root": str(root),
        "mcp_executable": executable,
        "mcp_executable_ready": executable_ready,
        "template_version": deps.integration_template_version,
        "global": global_state,
        "providers": providers,
        "ready": executable_ready and all(state["ready"] for state in providers.values()),
    }
