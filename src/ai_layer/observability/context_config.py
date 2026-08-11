from __future__ import annotations

from pathlib import Path

import yaml

from ai_layer.core.redaction import redact_secrets
from ai_layer.observability.context_common import profile_value, redact_value
from ai_layer.skills.native import native_catalog_files


def _native_skill_catalog_snapshot(project_root: Path) -> dict:
    hosts: dict[str, dict] = {}
    for host, paths in native_catalog_files(project_root).items():
        metadata_items: list[dict] = []
        descriptors: list[dict] = []
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta = {}
            if raw.startswith("---\n"):
                parts = raw.split("---\n", 2)
                if len(parts) == 3:
                    loaded = yaml.safe_load(parts[1]) or {}
                    meta = loaded if isinstance(loaded, dict) else {}
            item = {
                "name": str(meta.get("name") or path.parent.name),
                "description": str(meta.get("description") or ""),
                "path": str(path),
            }
            metadata_items.append(item)
            descriptors.append({**item, "descriptor_profile": profile_value(redact_secrets(raw))})
        hosts[host] = {
            "delivery_visibility": "AI_LAYER_CONFIGURED; host discovery/selection is HOST_HIDDEN",
            "descriptor_count": len(descriptors),
            "catalog_metadata_profile": profile_value(metadata_items),
            "descriptors": descriptors,
        }
    unique_paths = {item["path"] for host in hosts.values() for item in host["descriptors"]}
    return {
        "routing_owner": "host-native",
        "automatic_memory_context_skill_injection": False,
        "unique_descriptor_files": len(unique_paths),
        "hosts": hosts,
    }


def configured_context_snapshot(
    project_root: str,
    mcp_instructions: str | None,
    mcp_tool_catalog: tuple[dict, ...] | None,
) -> dict:
    root = Path(project_root).expanduser().resolve()
    cursor_global = (
        Path.home()
        / ".cursor"
        / "plugins"
        / "local"
        / "ai-layer-bootstrap"
        / "rules"
        / "ai-layer.mdc"
    )
    cursor_project = root / ".cursor" / "rules" / "ai-layer.mdc"

    def configured_file(path: Path, label: str) -> dict:
        try:
            exists = path.is_file() and not path.is_symlink()
            content = path.read_text(encoding="utf-8") if exists else ""
        except (OSError, UnicodeDecodeError):
            exists = False
            content = ""
        content = redact_secrets(content)
        return {
            "label": label,
            "path": str(path),
            "configured_file_present": exists,
            "delivery_visibility": "configured_not_runtime_verified",
            "profile": profile_value(content),
            "content": content,
        }

    snapshot: dict[str, object] = {
        "visibility_contract": {
            "ai_layer_observable": "AI Layer can prove what it configured and what its MCP tools returned.",
            "host_hidden": "Cursor system prompt, chat history, host-added context, exact tool-schema inclusion and final model tokenizer usage are not observable through AI Layer MCP.",
            "token_estimate": "ceil(UTF-8 bytes / 4); approximation only because the physical host/model tokenizer is unknown.",
        },
        "global_bootstrap": configured_file(cursor_global, "Cursor global alwaysApply bootstrap"),
        "project_rule": configured_file(cursor_project, "Cursor project alwaysApply workflow"),
        "native_skill_catalog": _native_skill_catalog_snapshot(root),
    }
    instructions = redact_secrets(mcp_instructions or "")
    snapshot["mcp_server_instructions"] = {
        "delivery_visibility": "server_defined_host_runtime_not_verified",
        "profile": profile_value(instructions),
        "content": instructions,
    }
    catalog = redact_value(list(mcp_tool_catalog or ()))
    snapshot["mcp_tool_catalog"] = {
        "delivery_visibility": "ai_layer_registered_contract_host_schema_inclusion_not_runtime_verified",
        "tool_count": len(catalog),
        "profile": profile_value(catalog),
        "tools": [
            {**item, "profile": profile_value(item)} for item in catalog if isinstance(item, dict)
        ],
    }
    agents_dir = Path.home() / ".cursor" / "agents"
    profiles = []
    if agents_dir.is_dir() and not agents_dir.is_symlink():
        for path in sorted(agents_dir.glob("ai-layer-*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                content = redact_secrets(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            profiles.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "delivery_visibility": "loaded_only_if_host_selects_this_worker_profile",
                    "profile": profile_value(content),
                    "content": content,
                }
            )
    snapshot["configured_worker_profiles"] = profiles
    return snapshot
