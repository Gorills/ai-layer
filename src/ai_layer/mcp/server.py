"""MCP composition root. Tool adapters are registered by focused modules."""
from __future__ import annotations

import os

from ai_layer.core.mcp_process import registered_mcp_process
from ai_layer.mcp.runtime import MCP_INSTRUCTIONS, TOOL_HANDLERS, core_tool, execute_core_tool, mcp
from ai_layer.mcp.tools.project_context import (
    project_info, memory_search, memory_context,
)
from ai_layer.mcp.tools.tasks import (
    task_current, task_next, review_sandbox_prepare, review_check_run, verification_run, review_sandbox_cleanup, task_create, task_adopt, task_stage_delegate, task_discovery_complete, task_implementation_complete, task_review_complete, task_fix_complete, task_stage_complete, task_resume, task_cancel,
)
from ai_layer.mcp.tools.worker_control import task_worker_disconnected, task_worker_heartbeat
from ai_layer.mcp.tools.skills import (
    skill_list, skill_search, skill_get, skill_project_create, skill_import, skill_catalog, skill_install, skill_update, skill_set_enabled, skill_remove, skill_info,
)
from ai_layer.mcp.tools.sessions import (
    session_list, session_restore, session_save, decision_search,
)
from ai_layer.mcp.tools.knowledge import knowledge_list, knowledge_draft_upsert


def main() -> None:
    os.environ["AI_LAYER_MCP_BRIDGE"] = "1"
    with registered_mcp_process():
        mcp.run()


__all__ = [
    "mcp", "MCP_INSTRUCTIONS", "TOOL_HANDLERS", "core_tool", "execute_core_tool",
    "project_info",
    "memory_search",
    "memory_context",
    "task_current",
    "task_next",
    "review_sandbox_prepare",
    "review_check_run",
    "verification_run",
    "review_sandbox_cleanup",
    "task_create",
    "task_adopt",
    "task_stage_delegate",
    "task_discovery_complete",
    "task_implementation_complete",
    "task_review_complete",
    "task_fix_complete",
    "task_stage_complete",
    "task_worker_disconnected",
    "task_worker_heartbeat",
    "task_resume",
    "task_cancel",
    "skill_list",
    "skill_search",
    "skill_get",
    "skill_project_create",
    "skill_import",
    "skill_catalog",
    "skill_install",
    "skill_update",
    "skill_set_enabled",
    "skill_remove",
    "skill_info",
    "session_list",
    "session_restore",
    "session_save",
    "decision_search",
    "knowledge_list",
    "knowledge_draft_upsert",
]

if __name__ == "__main__":
    main()
