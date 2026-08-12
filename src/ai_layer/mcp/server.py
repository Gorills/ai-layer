"""MCP composition root. Tool adapters are registered by focused modules."""

from __future__ import annotations

import os

from ai_layer.core.mcp_process import registered_mcp_process
from ai_layer.mcp.runtime import MCP_INSTRUCTIONS, TOOL_HANDLERS, core_tool, execute_core_tool, mcp
from ai_layer.mcp.tools.epics import (
    epic_approve,
    epic_archive,
    epic_audit_prepare,
    epic_audit_record,
    epic_create,
    epic_get,
    epic_intervening_review_prepare,
    epic_intervening_review_record,
    epic_list,
    epic_next,
    epic_plan_set,
    epic_reconcile_complete,
    epic_spec_edit,
    epic_spec_get,
    epic_spec_revise,
    epic_start_next,
)
from ai_layer.mcp.tools.knowledge import knowledge_draft_upsert, knowledge_list
from ai_layer.mcp.tools.project_context import (
    memory_context,
    memory_search,
    project_info,
)
from ai_layer.mcp.tools.sessions import (
    decision_search,
    session_list,
    session_restore,
    session_save,
)
from ai_layer.mcp.tools.skills import (
    skill_catalog,
    skill_get,
    skill_import,
    skill_info,
    skill_install,
    skill_list,
    skill_project_create,
    skill_remove,
    skill_search,
    skill_set_enabled,
    skill_update,
)
from ai_layer.mcp.tools.tasks import (
    review_check_run,
    review_sandbox_cleanup,
    review_sandbox_prepare,
    task_adopt,
    task_cancel,
    task_create,
    task_current,
    task_discovery_complete,
    task_fix_complete,
    task_implementation_complete,
    task_next,
    task_resume,
    task_review_complete,
    task_stage_complete,
    task_stage_delegate,
    verification_run,
)
from ai_layer.mcp.tools.worker_control import task_worker_disconnected, task_worker_heartbeat


def main() -> None:
    os.environ["AI_LAYER_MCP_BRIDGE"] = "1"
    with registered_mcp_process():
        mcp.run()


__all__ = [
    "mcp",
    "MCP_INSTRUCTIONS",
    "TOOL_HANDLERS",
    "core_tool",
    "execute_core_tool",
    "project_info",
    "memory_search",
    "memory_context",
    "epic_create",
    "epic_list",
    "epic_get",
    "epic_spec_get",
    "epic_spec_edit",
    "epic_spec_revise",
    "epic_audit_prepare",
    "epic_audit_record",
    "epic_approve",
    "epic_next",
    "epic_start_next",
    "epic_intervening_review_prepare",
    "epic_intervening_review_record",
    "epic_reconcile_complete",
    "epic_plan_set",
    "epic_archive",
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
