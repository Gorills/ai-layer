from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_layer.skills.common import builtin_skill_dir
from ai_layer.skills.native_descriptor import NATIVE_MARKER
from ai_layer.skills.native_files import descriptor_metadata
from ai_layer.skills.registry import disabled_global_skill_slugs

_CORE_PROVIDERS = ("cursor", "codex", "antigravity")
_PROVIDER_HEALTH_READY = "ready"
_PROVIDER_HEALTH_DEGRADED = "degraded"
_PROVIDER_HEALTH_NOT_INSTALLED = "not_installed"


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
    global_bootstrap_marker: str
    project_integration_paths: tuple[str, ...]
    claude_user_mcp_status: Callable[[], dict]


def provider_install_status(*parts: object) -> str:
    """Classify host presence. ``None`` is absence, not success."""
    present = [_presence(part) for part in parts]
    if present and all(present):
        return _PROVIDER_HEALTH_READY
    if any(present):
        return _PROVIDER_HEALTH_DEGRADED
    return _PROVIDER_HEALTH_NOT_INSTALLED


def _presence(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return bool(value.get("ready"))
    return bool(value)


def _apply_provider_health(state: dict) -> dict:
    health = provider_install_status(
        state.get("bootstrap"),
        state.get("mcp"),
        state.get("native_skills"),
    )
    state["status"] = health
    state["ready"] = health == _PROVIDER_HEALTH_READY
    return state


def _host_mcp_skills_state(
    *,
    path: Path,
    mcp_ready: bool,
    native_skills: dict,
    extra: dict | None = None,
) -> dict:
    health = provider_install_status(mcp_ready, native_skills)
    payload = {
        "path": str(path),
        "mcp_ready": mcp_ready,
        "native_skills": native_skills,
        "status": health,
        "ready": health == _PROVIDER_HEALTH_READY,
    }
    if extra:
        payload.update(extra)
    return payload


def _bootstrap_file_status(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
        return deps.managed_start in text and deps.global_bootstrap_marker in text
    except (OSError, UnicodeDecodeError):
        return False


def _bootstrap_version_current(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        return deps.global_bootstrap_marker in path.read_text(encoding="utf-8")
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
            "ready": deps.cursor_plugin_owned(plugin)
            and cursor_manifest.exists()
            and _bootstrap_version_current(cursor_rule, deps),
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


def _expected_global_native_slugs() -> frozenset[str]:
    try:
        disabled = disabled_global_skill_slugs()
    except RuntimeError:
        return frozenset()
    slugs: set[str] = set()
    bundled = builtin_skill_dir()
    if not bundled.exists():
        return frozenset()
    for item in bundled.iterdir():
        name = str(item.name)
        if name.endswith(".md"):
            slug = name[: -len(".md")]
            if slug and slug not in disabled:
                slugs.add(slug)
    return frozenset(slugs)


def _current_owned_global_slug(child: Path) -> str | None:
    if not child.is_dir() or child.is_symlink():
        return None
    target = child / "SKILL.md"
    metadata = descriptor_metadata(target)
    if not metadata or metadata.get("scope") != "global":
        return None
    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if NATIVE_MARKER not in content:
        return None
    slug = str(metadata.get("canonical") or "").strip()
    return slug or None


def _native_skill_catalog_status(root: Path) -> dict:
    expected = _expected_global_native_slugs()
    expected_count = len(expected)
    found: set[str] = set()
    if root.is_dir() and not root.is_symlink():
        for child in root.iterdir():
            slug = _current_owned_global_slug(child)
            if slug is not None and slug in expected:
                found.add(slug)
    owned = len(found)
    ready = expected_count > 0 and owned == expected_count
    if ready:
        catalog_status = _PROVIDER_HEALTH_READY
    elif owned:
        catalog_status = _PROVIDER_HEALTH_DEGRADED
    else:
        catalog_status = _PROVIDER_HEALTH_NOT_INSTALLED
    return {
        "path": str(root),
        "ready": ready,
        "owned_descriptors": owned,
        "expected_descriptors": expected_count,
        "status": catalog_status,
    }


def global_integration_status(deps: IntegrationStatusDependencies) -> dict:
    home = Path.home()
    targets = {
        "cursor": home / ".cursor" / "mcp.json",
        "antigravity": home / ".gemini" / "config" / "mcp_config.json",
        "codex": home / ".codex" / "config.toml",
        "claude-code": home / ".claude",
    }
    shared_native = _native_skill_catalog_status(home / ".agents" / "skills")
    antigravity_native = _native_skill_catalog_status(home / ".gemini" / "config" / "skills")
    claude_native = _native_skill_catalog_status(home / ".claude" / "skills")
    cursor_mcp = _json_has_ai_layer(targets["cursor"], deps)
    antigravity_mcp = _json_has_ai_layer(targets["antigravity"], deps)
    codex_mcp = _codex_has_ai_layer(targets["codex"], deps)
    claude_mcp = deps.claude_user_mcp_status()
    claude_mcp_ready = bool(claude_mcp.get("owned"))
    claude_cli_available = bool(claude_mcp.get("cli_available"))
    claude_extra = {
        "cli_available": claude_cli_available,
        "mcp_reason": claude_mcp.get("reason"),
    }
    if not claude_cli_available:
        claude_extra["note"] = (
            "optional Claude CLI is not installed; Claude MCP is degraded, not a global install failure"
        )
    return {
        "cursor": _host_mcp_skills_state(
            path=targets["cursor"], mcp_ready=cursor_mcp, native_skills=shared_native
        ),
        "antigravity": _host_mcp_skills_state(
            path=targets["antigravity"],
            mcp_ready=antigravity_mcp,
            native_skills=antigravity_native,
        ),
        "codex": _host_mcp_skills_state(
            path=targets["codex"], mcp_ready=codex_mcp, native_skills=shared_native
        ),
        "claude-code": _host_mcp_skills_state(
            path=targets["claude-code"],
            mcp_ready=claude_mcp_ready,
            native_skills=claude_native,
            extra=claude_extra,
        ),
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


def _core_hosts_ready(providers: dict, *, executable_ready: bool) -> bool:
    return executable_ready and all(providers[name]["ready"] for name in _CORE_PROVIDERS)


def _external_status(
    root: Path,
    deps: IntegrationStatusDependencies,
    *,
    mode: str,
    executable: str,
    executable_ready: bool,
    global_state: dict,
) -> dict:
    bootstrap = global_bootstrap_status(deps)
    claude_state = global_state["claude-code"]
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
        "claude-code": {
            "bootstrap": bootstrap["claude-code"]["ready"],
            "mcp": bool(claude_state.get("mcp_ready")),
            "native_skills": claude_state["native_skills"]["ready"],
            "cli_available": bool(claude_state.get("cli_available")),
        },
    }
    if claude_state.get("note"):
        providers["claude-code"]["note"] = claude_state["note"]
    for state in providers.values():
        _apply_provider_health(state)
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
        "ready": _core_hosts_ready(providers, executable_ready=executable_ready),
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
            root,
            deps,
            mode=mode,
            executable=executable,
            executable_ready=executable_ready,
            global_state=global_state,
        )
    try:
        targets = {
            relative: deps.project_local_path(root, relative)
            for relative in deps.project_integration_paths
        }
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
    claude_state = global_state["claude-code"]
    providers = {
        "cursor": {
            "bootstrap": bootstrap["cursor"]["ready"],
            "mcp": _json_has_ai_layer(targets[".cursor/mcp.json"], deps)
            or global_state["cursor"]["mcp_ready"],
            "native_skills": global_state["cursor"]["native_skills"]["ready"],
        },
        "claude-code": {
            "bootstrap": bootstrap["claude-code"]["ready"],
            "mcp": _json_has_ai_layer(targets[".mcp.json"], deps)
            or bool(claude_state.get("mcp_ready")),
            "native_skills": claude_state["native_skills"]["ready"],
            "cli_available": bool(claude_state.get("cli_available")),
        },
        "codex": {
            "bootstrap": bootstrap["codex"]["ready"],
            "mcp": _codex_has_ai_layer(targets[".codex/config.toml"], deps)
            or global_state["codex"]["mcp_ready"],
            "native_skills": global_state["codex"]["native_skills"]["ready"],
        },
        "antigravity": {
            "bootstrap": bootstrap["antigravity-gemini"]["ready"],
            "mcp": _json_has_ai_layer(targets[".agents/mcp_config.json"], deps)
            or global_state["antigravity"]["mcp_ready"],
            "native_skills": global_state["antigravity"]["native_skills"]["ready"],
        },
    }
    if claude_state.get("note"):
        providers["claude-code"]["note"] = claude_state["note"]
    for state in providers.values():
        _apply_provider_health(state)
    return {
        "project_root": str(root),
        "mcp_executable": executable,
        "mcp_executable_ready": executable_ready,
        "template_version": deps.integration_template_version,
        "global": global_state,
        "providers": providers,
        "ready": _core_hosts_ready(providers, executable_ready=executable_ready),
    }
