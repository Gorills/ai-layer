from __future__ import annotations

from pathlib import Path

from ai_layer.integrations.service import (
    global_bootstrap_status,
    global_integration_status,
    integration_status,
)
from ai_layer.projections.dashboard_common import entry_for_key, project_options

_PROVIDER_ORDER = ("cursor", "codex", "antigravity", "claude-code")
_BOOTSTRAP_KEYS = {
    "cursor": "cursor",
    "codex": "codex",
    "antigravity": "antigravity-gemini",
    "claude-code": "claude-code",
}


def _native_ready(state: dict) -> bool | None:
    value = state.get("native_skills")
    if isinstance(value, dict):
        return bool(value.get("ready"))
    if value is None:
        return None
    return bool(value)


def _global_provider(name: str, integrations: dict, bootstrap: dict) -> dict:
    state = integrations.get(name) or {}
    bootstrap_state = bootstrap.get(_BOOTSTRAP_KEYS[name]) or {}
    mcp_ready = state.get("mcp_ready")
    native_ready = _native_ready(state)
    ready = (
        bool(state.get("ready"))
        if name != "claude-code"
        else bool(bootstrap_state.get("ready"))
    )
    return {
        "name": name,
        "ready": ready,
        "bootstrap_ready": bool(bootstrap_state.get("ready")),
        "mcp_ready": bool(mcp_ready) if mcp_ready is not None else None,
        "native_skills_ready": native_ready,
        "runtime_acceptance_required": bool(
            bootstrap_state.get("runtime_acceptance_required")
        ),
    }


def _project_provider(name: str, state: dict) -> dict:
    mcp_ready = state.get("mcp")
    native_ready = _native_ready(state)
    return {
        "name": name,
        "ready": bool(state.get("ready")),
        "bootstrap_ready": bool(state.get("bootstrap")),
        "mcp_ready": bool(mcp_ready) if mcp_ready is not None else None,
        "native_skills_ready": native_ready,
        "runtime_acceptance_required": bool(
            state.get("runtime_acceptance_required")
        ),
    }


def monitoring_payload(project_key_value: str | None = None) -> dict | None:
    integrations = global_integration_status()
    bootstrap = global_bootstrap_status()
    providers = [
        _global_provider(name, integrations, bootstrap)
        for name in _PROVIDER_ORDER
        if name in integrations or name == "claude-code"
    ]

    selected = None
    if project_key_value:
        entry = entry_for_key(project_key_value)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
        state = integration_status(root)
        project_providers = state.get("providers") or {}
        selected = {
            "key": project_key_value,
            "name": entry.get("name") or root.name,
            "root": str(root),
            "mode": state.get("mode") or entry.get("mode") or "standard",
            "ready": bool(state.get("ready")),
            "mcp_executable_ready": bool(state.get("mcp_executable_ready")),
            "template_version": state.get("template_version"),
            "providers": [
                _project_provider(name, project_providers.get(name) or {})
                for name in _PROVIDER_ORDER
                if name in project_providers
            ],
        }

    return {
        "global": {
            "ready": all(
                item["ready"]
                for item in providers
                if item["name"] != "claude-code"
            ),
            "providers": providers,
        },
        "project": selected,
        "projects": project_options(),
    }
