from __future__ import annotations

import os
import shutil
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.integrations.config_files import MCP_OWNER_KEY, MCP_OWNER_VALUE
from ai_layer.integrations.templates import global_bootstrap_workflow as global_bootstrap_workflow_template, workflow as workflow_template

def _mcp_command() -> str:
    override = os.getenv("AI_LAYER_MCP_EXECUTABLE")
    if override:
        return str(Path(override).expanduser())
    stable = get_settings().stable_mcp_executable
    if stable.exists():
        return str(stable)
    found = shutil.which("ai-layer-mcp")
    return found or "ai-layer-mcp"

def _workflow(project_root: Path) -> str:
    return workflow_template(project_root)

def _global_bootstrap_workflow() -> str:
    return global_bootstrap_workflow_template()

def _server(*, project_root: Path | None = None, client: str | None = None) -> dict:
    env: dict[str, str] = {}
    if project_root is not None:
        env["AI_LAYER_PROJECT_ROOT"] = str(project_root.resolve())
    if client:
        env["AI_LAYER_CLIENT"] = client
    env[MCP_OWNER_KEY] = MCP_OWNER_VALUE
    return {"command": _mcp_command(), "args": [], "env": env}
