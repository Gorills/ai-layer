from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_layer.integrations.codex_status import active_codex_home as _active_codex_home
from ai_layer.integrations.codex_status import codex_mcp_status as _codex_mcp_status
from ai_layer.integrations.codex_status import nonempty_file as _nonempty_file
from ai_layer.integrations.health_contract import (
    HEALTH_DEGRADED as _PROVIDER_HEALTH_DEGRADED,
)
from ai_layer.integrations.health_contract import (
    HEALTH_NOT_INSTALLED as _PROVIDER_HEALTH_NOT_INSTALLED,
)
from ai_layer.integrations.health_contract import HEALTH_READY as _PROVIDER_HEALTH_READY
from ai_layer.integrations.health_contract import (
    RUNTIME_BLOCKED as _RUNTIME_BLOCKED,
)
from ai_layer.integrations.health_contract import (
    RUNTIME_UNVERIFIED as _RUNTIME_UNVERIFIED,
)
from ai_layer.integrations.health_contract import (
    RUNTIME_VERIFIED as _RUNTIME_VERIFIED,
)
from ai_layer.integrations.health_contract import STATUS_CONTRACT_VERSION, provider_install_status
from ai_layer.integrations.health_contract import (
    apply_status_contract as _apply_status_contract,
)
from ai_layer.integrations.health_contract import operational_status as _operational_status
from ai_layer.integrations.health_contract import runtime_assurance as _runtime_assurance
from ai_layer.skills.common import builtin_skill_dir
from ai_layer.skills.native_descriptor import NATIVE_MARKER
from ai_layer.skills.native_files import descriptor_metadata
from ai_layer.skills.registry import disabled_global_skill_slugs

_CORE_PROVIDERS = ("cursor", "codex", "antigravity")


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


def _apply_provider_health(state: dict) -> dict:
    health = provider_install_status(
        state.get("bootstrap"),
        state.get("mcp"),
        state.get("native_skills"),
    )
    assurance = state.get("runtime_assurance") or _runtime_assurance(
        _RUNTIME_UNVERIFIED, "filesystem", "host_runtime_not_observed"
    )
    return _apply_status_contract(state, health=health, runtime_assurance=assurance)


def _host_mcp_skills_state(
    *,
    path: Path,
    mcp_ready: bool,
    native_skills: dict,
    runtime_assurance: dict | None = None,
    extra: dict | None = None,
    optional: bool = False,
) -> dict:
    health = provider_install_status(mcp_ready, native_skills)
    payload = {
        "path": str(path),
        "mcp_ready": mcp_ready,
        "native_skills": native_skills,
    }
    if extra:
        payload.update(extra)
    if optional:
        payload["optional"] = True
    assurance = runtime_assurance or _runtime_assurance(
        _RUNTIME_UNVERIFIED, "filesystem", "host_runtime_not_observed"
    )
    return _apply_status_contract(payload, health=health, runtime_assurance=assurance)


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


def _bootstrap_payload(
    *,
    path: Path,
    ready: bool,
    verified_by: str,
    runtime_assurance: dict,
    extra: dict | None = None,
) -> dict:
    payload = {"path": str(path), "verified_by": verified_by}
    if extra:
        payload.update(extra)
    health = _PROVIDER_HEALTH_READY if ready else _PROVIDER_HEALTH_NOT_INSTALLED
    return _apply_status_contract(payload, health=health, runtime_assurance=runtime_assurance)


def global_bootstrap_status(deps: IntegrationStatusDependencies) -> dict:
    home = Path.home()
    codex_home = _active_codex_home(home)
    codex_bootstrap = codex_home / "AGENTS.md"
    codex_override = codex_home / "AGENTS.override.md"
    codex_ready = _bootstrap_file_status(codex_bootstrap, deps)
    codex_shadowed = codex_ready and _nonempty_file(codex_override)
    plugin = home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap"
    cursor_manifest = plugin / ".cursor-plugin" / "plugin.json"
    cursor_rule = plugin / "rules" / "ai-layer.mdc"
    cursor_ready = (
        deps.cursor_plugin_owned(plugin)
        and cursor_manifest.exists()
        and _bootstrap_version_current(cursor_rule, deps)
    )
    return {
        "codex": _bootstrap_payload(
            path=codex_bootstrap,
            ready=codex_ready,
            verified_by="documented user-level AGENTS.md",
            runtime_assurance=_runtime_assurance(
                _RUNTIME_BLOCKED if codex_shadowed else _RUNTIME_UNVERIFIED,
                "filesystem+host_contract",
                "agents_override_shadows_global_bootstrap"
                if codex_shadowed
                else "host_runtime_not_observed",
            ),
            extra={
                "codex_home": str(codex_home),
                "override_path": str(codex_override),
                "override_shadowing": codex_shadowed,
            },
        ),
        "claude-code": _bootstrap_payload(
            path=home / ".claude" / "CLAUDE.md",
            ready=_bootstrap_file_status(home / ".claude" / "CLAUDE.md", deps),
            verified_by="documented user memory file",
            runtime_assurance=_runtime_assurance(
                _RUNTIME_UNVERIFIED, "host_contract", "host_runtime_not_observed"
            ),
        ),
        "antigravity-gemini": _bootstrap_payload(
            path=home / ".gemini" / "GEMINI.md",
            ready=_bootstrap_file_status(home / ".gemini" / "GEMINI.md", deps),
            verified_by="documented global context file",
            runtime_assurance=_runtime_assurance(
                _RUNTIME_UNVERIFIED, "host_contract", "host_runtime_not_observed"
            ),
        ),
        "cursor": _bootstrap_payload(
            path=plugin,
            ready=cursor_ready,
            verified_by="owned local plugin files present; runtime black-box acceptance required",
            runtime_assurance=_runtime_assurance(
                _RUNTIME_UNVERIFIED, "filesystem", "cursor_runtime_not_observed"
            ),
            extra={"runtime_acceptance_required": True},
        ),
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


def _claude_runtime_assurance(claude_state: dict) -> dict:
    if not claude_state.get("cli_available"):
        return _runtime_assurance(_RUNTIME_UNVERIFIED, "filesystem", "claude_cli_unavailable")
    if claude_state.get("mcp_ready"):
        return _runtime_assurance(
            _RUNTIME_UNVERIFIED,
            "host_cli+host_contract",
            "bootstrap_and_skills_runtime_not_observed",
        )
    return _runtime_assurance(
        _RUNTIME_UNVERIFIED, "host_cli", str(claude_state.get("mcp_reason") or "mcp_unverified")
    )


def global_integration_status(deps: IntegrationStatusDependencies) -> dict:
    home = Path.home()
    codex_home = _active_codex_home(home)
    targets = {
        "cursor": home / ".cursor" / "mcp.json",
        "antigravity": home / ".gemini" / "config" / "mcp_config.json",
        "codex": codex_home / "config.toml",
        "claude-code": home / ".claude",
    }
    shared_native = _native_skill_catalog_status(home / ".agents" / "skills")
    antigravity_native = _native_skill_catalog_status(home / ".gemini" / "config" / "skills")
    claude_native = _native_skill_catalog_status(home / ".claude" / "skills")
    cursor_mcp = _json_has_ai_layer(targets["cursor"], deps)
    antigravity_mcp = _json_has_ai_layer(targets["antigravity"], deps)
    codex_mcp_state = _codex_mcp_status(targets["codex"], deps)
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
    codex_runtime = (
        _runtime_assurance(_RUNTIME_BLOCKED, "host_config", "mcp_disabled")
        if codex_mcp_state.get("reason") == "mcp_disabled"
        else _runtime_assurance(_RUNTIME_UNVERIFIED, "host_contract", "host_runtime_not_observed")
    )
    return {
        "cursor": _host_mcp_skills_state(
            path=targets["cursor"],
            mcp_ready=cursor_mcp,
            native_skills=shared_native,
            runtime_assurance=_runtime_assurance(
                _RUNTIME_UNVERIFIED, "filesystem", "cursor_runtime_not_observed"
            ),
        ),
        "antigravity": _host_mcp_skills_state(
            path=targets["antigravity"],
            mcp_ready=antigravity_mcp,
            native_skills=antigravity_native,
            runtime_assurance=_runtime_assurance(
                _RUNTIME_UNVERIFIED, "host_contract", "host_runtime_not_observed"
            ),
        ),
        "codex": _host_mcp_skills_state(
            path=targets["codex"],
            mcp_ready=bool(codex_mcp_state.get("ready")),
            native_skills=shared_native,
            runtime_assurance=codex_runtime,
            extra={
                "mcp_reason": codex_mcp_state.get("reason"),
                "codex_home": str(codex_home),
            },
        ),
        "claude-code": _host_mcp_skills_state(
            path=targets["claude-code"],
            mcp_ready=claude_mcp_ready,
            native_skills=claude_native,
            runtime_assurance=_claude_runtime_assurance(
                {**claude_extra, "mcp_ready": claude_mcp_ready}
            ),
            extra=claude_extra,
            optional=True,
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


def _core_hosts_configured(providers: dict, *, executable_ready: bool) -> bool:
    return executable_ready and all(
        providers.get(name, {}).get(
            "configuration_ready", providers.get(name, {}).get("ready", False)
        )
        for name in _CORE_PROVIDERS
    )


def _aggregate_runtime_assurance(providers: dict) -> dict:
    states = {
        name: (providers.get(name, {}).get("runtime_assurance") or {}).get("state")
        for name in _CORE_PROVIDERS
    }
    blocked = sorted(name for name, state in states.items() if state == _RUNTIME_BLOCKED)
    if blocked:
        return _runtime_assurance(
            _RUNTIME_BLOCKED, "provider_aggregate", "blocked providers: " + ", ".join(blocked)
        )
    unverified = sorted(name for name, state in states.items() if state == _RUNTIME_UNVERIFIED)
    if unverified:
        return _runtime_assurance(
            _RUNTIME_UNVERIFIED,
            "provider_aggregate",
            "runtime acceptance not verified: " + ", ".join(unverified),
        )
    return _runtime_assurance(_RUNTIME_VERIFIED, "provider_aggregate", None)


def _finish_integration_status(payload: dict, *, providers: dict, executable_ready: bool) -> dict:
    configuration_ready = _core_hosts_configured(providers, executable_ready=executable_ready)
    assurance = _aggregate_runtime_assurance(providers)
    health = _PROVIDER_HEALTH_READY if configuration_ready else _PROVIDER_HEALTH_DEGRADED
    payload["status_contract_version"] = STATUS_CONTRACT_VERSION
    payload["configuration_ready"] = configuration_ready
    payload["ready"] = configuration_ready
    payload["ready_semantics"] = "configuration"
    payload["runtime_assurance"] = assurance
    payload["operational_status"] = _operational_status(health, assurance)
    return payload


def _global_project_status(
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
            "runtime_assurance": bootstrap["cursor"]["runtime_assurance"],
        },
        "codex": {
            "bootstrap": bootstrap["codex"]["ready"],
            "mcp": global_state["codex"]["mcp_ready"],
            "mcp_reason": global_state["codex"].get("mcp_reason"),
            "native_skills": global_state["codex"]["native_skills"]["ready"],
            "runtime_assurance": bootstrap["codex"]["runtime_assurance"],
        },
        "antigravity": {
            "bootstrap": bootstrap["antigravity-gemini"]["ready"],
            "mcp": global_state["antigravity"]["mcp_ready"],
            "native_skills": global_state["antigravity"]["native_skills"]["ready"],
            "runtime_assurance": bootstrap["antigravity-gemini"]["runtime_assurance"],
        },
        "claude-code": {
            "bootstrap": bootstrap["claude-code"]["ready"],
            "mcp": bool(claude_state.get("mcp_ready")),
            "native_skills": claude_state["native_skills"]["ready"],
            "cli_available": bool(claude_state.get("cli_available")),
            "runtime_assurance": _claude_runtime_assurance(claude_state),
            "optional": True,
        },
    }
    if claude_state.get("note"):
        providers["claude-code"]["note"] = claude_state["note"]
    if global_state["codex"].get("mcp_reason") == "mcp_disabled":
        providers["codex"]["runtime_assurance"] = _runtime_assurance(
            _RUNTIME_BLOCKED, "host_config", "mcp_disabled"
        )
    for state in providers.values():
        _apply_provider_health(state)
    payload = {
        "project_root": str(root),
        "mode": mode,
        "repository_writes": False,
        "mcp_executable": executable,
        "mcp_executable_ready": executable_ready,
        "template_version": deps.integration_template_version,
        "global": global_state,
        "bootstrap": bootstrap,
        "providers": providers,
        "cursor_runtime_acceptance_required": True,
    }
    return _finish_integration_status(
        payload, providers=providers, executable_ready=executable_ready
    )


def integration_status(deps: IntegrationStatusDependencies, project_root: str | Path) -> dict:
    root = Path(project_root).expanduser().resolve()
    global_state = global_integration_status(deps)
    executable = deps.mcp_command()
    executable_ready = _command_ready(executable)
    mode = deps.project_mode(root)
    if mode in {"standard", "external", "strict-private"}:
        return _global_project_status(
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
            "status_contract_version": STATUS_CONTRACT_VERSION,
            "configuration_ready": False,
            "ready": False,
            "ready_semantics": "configuration",
            "runtime_assurance": _runtime_assurance(
                _RUNTIME_UNVERIFIED, "none", "unsafe_project_integration_path"
            ),
            "operational_status": _PROVIDER_HEALTH_DEGRADED,
            "unsafe_path": str(exc),
        }

    bootstrap = global_bootstrap_status(deps)
    claude_state = global_state["claude-code"]
    project_codex = _codex_mcp_status(targets[".codex/config.toml"], deps)
    if project_codex.get("ready") or project_codex.get("reason") == "mcp_disabled":
        codex_mcp = bool(project_codex.get("ready"))
        codex_mcp_reason = project_codex.get("reason")
    else:
        codex_mcp = bool(global_state["codex"]["mcp_ready"])
        codex_mcp_reason = global_state["codex"].get("mcp_reason")
    codex_runtime = bootstrap["codex"]["runtime_assurance"]
    if codex_mcp_reason == "mcp_disabled":
        codex_runtime = _runtime_assurance(_RUNTIME_BLOCKED, "host_config", "mcp_disabled")
    providers = {
        "cursor": {
            "bootstrap": bootstrap["cursor"]["ready"],
            "mcp": _json_has_ai_layer(targets[".cursor/mcp.json"], deps)
            or global_state["cursor"]["mcp_ready"],
            "native_skills": global_state["cursor"]["native_skills"]["ready"],
            "runtime_acceptance_required": True,
            "runtime_assurance": bootstrap["cursor"]["runtime_assurance"],
        },
        "claude-code": {
            "bootstrap": bootstrap["claude-code"]["ready"],
            "mcp": _json_has_ai_layer(targets[".mcp.json"], deps)
            or bool(claude_state.get("mcp_ready")),
            "native_skills": claude_state["native_skills"]["ready"],
            "cli_available": bool(claude_state.get("cli_available")),
            "runtime_assurance": _claude_runtime_assurance(claude_state),
            "optional": True,
        },
        "codex": {
            "bootstrap": bootstrap["codex"]["ready"],
            "mcp": codex_mcp,
            "mcp_reason": codex_mcp_reason,
            "native_skills": global_state["codex"]["native_skills"]["ready"],
            "runtime_assurance": codex_runtime,
        },
        "antigravity": {
            "bootstrap": bootstrap["antigravity-gemini"]["ready"],
            "mcp": _json_has_ai_layer(targets[".agents/mcp_config.json"], deps)
            or global_state["antigravity"]["mcp_ready"],
            "native_skills": global_state["antigravity"]["native_skills"]["ready"],
            "runtime_assurance": bootstrap["antigravity-gemini"]["runtime_assurance"],
        },
    }
    if claude_state.get("note"):
        providers["claude-code"]["note"] = claude_state["note"]
    for state in providers.values():
        _apply_provider_health(state)
    payload = {
        "project_root": str(root),
        "mcp_executable": executable,
        "mcp_executable_ready": executable_ready,
        "template_version": deps.integration_template_version,
        "global": global_state,
        "bootstrap": bootstrap,
        "providers": providers,
        "cursor_runtime_acceptance_required": True,
    }
    return _finish_integration_status(
        payload, providers=providers, executable_ready=executable_ready
    )
