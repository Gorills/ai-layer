from __future__ import annotations
from ai_layer.mcp.runtime import core_tool
from ai_layer.mcp.runtime import _project, _scoped, _text, project_root_for_tool
from ai_layer.mcp.context import bind_project_root
from ai_layer.application.transport import memory_context as build_memory_context
from ai_layer.application.transport import project_info as get_project_info
from ai_layer.audit.service import mcp_audit
from ai_layer.application.transport import memory_search as search_memory
from ai_layer.application.transport import application_scope as session_scope


def project_info(project_root: str | None = None) -> dict:
    """WHEN: you need project metadata only. INPUT: optional project_root. DO NOT use instead of memory_context at task start."""
    root = project_root_for_tool(project_root, tool="project_info")
    with mcp_audit(root, "project_info", arg_keys=["project_root"] if project_root else []):
        with session_scope() as db:
            result = get_project_info(db, root)
            bind_project_root(root)
            return _scoped(result, root)


def memory_search(query: str, project_root: str | None = None, limit: int = 8) -> list[dict]:
    """WHEN: memory_context left one specific reviewed project-knowledge gap. INPUT: query (required), project_root, limit. Searches curated VERIFIED knowledge only; use host-native tools for current source code. DO NOT use for broad repository dumps or repeat the same search."""
    root = project_root_for_tool(project_root, tool="memory_search")
    query = _text(query, tool="memory_search", field="query")
    with mcp_audit(root, "memory_search", arg_keys=["query", "project_root", "limit"]) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_memory(db, project, query, max(1, min(limit, 20)))
            audit["metrics"] = {"hits": len(result), "limit": max(1, min(limit, 20))}
            return result


def memory_context(
    task: str | None = None,
    query: str | None = None,
    project_root: str | None = None,
    limit: int = 4,
) -> dict:
    """WHEN: normally once at the start of every non-trivial repository task. Returns a compact reviewed Project Knowledge/history brief plus workflow policy/state. Current source is NOT copied into memory; inspect it with host-native tools. INPUT: task (canonical, required; legacy query accepted), optional project_root, limit. DO NOT repeat after ordinary edits in the same task."""
    root = project_root_for_tool(project_root, tool="memory_context")
    current_task = (task or query or "").strip()
    if not current_task:
        raise ValueError(
            'memory_context: `task` is required. Example: memory_context(task="Fix duplicate payment creation", project_root="<workspace>"). Legacy `query` is also accepted.'
        )
    keys = ["task" if task else "query", "limit"] + (["project_root"] if project_root else [])
    with mcp_audit(root, "memory_context", arg_keys=keys) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = build_memory_context(db, project, current_task, max(1, min(limit, 12)))
            freshness = result.get("freshness") or {}
            brief = result.get("task_brief") or {}
            audit["metrics"] = {
                "memory_hits": len(brief.get("verified_knowledge") or []),
                "knowledge_hits": len(brief.get("verified_knowledge") or []),
                "knowledge_inventory_items": len(brief.get("knowledge_inventory") or []),
                "stale_knowledge_hits": len(brief.get("stale_knowledge") or []),
                "history_hits": len(brief.get("relevant_history") or []),
                "decision_brief_hits": len(brief.get("relevant_decisions") or []),
                "knowledge_baseline_ready": bool(
                    (result.get("knowledge_state") or {}).get("baseline_ready")
                ),
                "skill_routing_owner": "host-native",
                "automatic_skill_injection": False,
                "automatic_skill_chars": int(
                    (result.get("context_budget") or {}).get("automatic_skill_chars") or 0
                ),
                "memory_refreshed": bool(freshness.get("refreshed")),
                "raw_source_memory_chars": int(
                    (result.get("context_budget") or {}).get("raw_source_memory_chars") or 0
                ),
                "files": freshness.get("files"),
            }
            return _scoped(result, root)


# MCP schema/handler registration remains local to this capability adapter.
project_info = core_tool()(project_info)
memory_search = core_tool()(memory_search)
memory_context = core_tool()(memory_context)
