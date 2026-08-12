from __future__ import annotations

from ai_layer.application.transport import application_scope as session_scope
from ai_layer.application.transport import memory_context as build_memory_context
from ai_layer.application.transport import memory_search as search_memory
from ai_layer.application.transport import project_info as get_project_info
from ai_layer.application.transport import project_search as search_project
from ai_layer.application.transport import project_status as get_project_status
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.context import bind_project_root
from ai_layer.mcp.runtime import _project, _scoped, _text, core_tool, project_root_for_tool


def project_status(project_root: str | None = None) -> dict:
    """WHEN: first state call for registered-project work. Restores cheap Task/Epic/Git/index state without running workflow navigators or scanning source. INPUT: optional project_root."""
    root = project_root_for_tool(project_root, tool="project_status")
    with mcp_audit(
        root, "project_status", arg_keys=["project_root"] if project_root else []
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = get_project_status(db, project)
            bind_project_root(root)
            work = result.get("work") or {}
            map_state = (result.get("index") or {}).get("project_map") or {}
            audit["metrics"] = {
                "active_task": bool(work.get("active_task")),
                "active_epic": bool(work.get("active_epic")),
                "dirty": (result.get("repository") or {}).get("dirty"),
                "navigation_files": int(map_state.get("navigation_files") or 0),
                "symbols": int(map_state.get("symbol_count") or 0),
            }
            return _scoped(result, root)


def project_search(query: str, project_root: str | None = None, limit: int = 8) -> dict:
    """WHEN: the relevant code location is unknown. Use before broad repository grep/search. Returns metadata-only breadcrumbs (paths/symbols/tests), never source bodies. INPUT: query, optional project_root, limit."""
    root = project_root_for_tool(project_root, tool="project_search")
    query = _text(query, tool="project_search", field="query")
    bounded_limit = max(1, min(limit, 20))
    with mcp_audit(
        root, "project_search", arg_keys=["query", "project_root", "limit"]
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_project(db, project, query, bounded_limit)
            matches = list(result.get("matches") or [])
            audit["metrics"] = {
                "hits": len(matches),
                "limit": bounded_limit,
                "top_score": matches[0].get("score") if matches else None,
                "search_mode": result.get("search_mode"),
            }
            return _scoped(result, root)


def project_info(project_root: str | None = None) -> dict:
    """WHEN: you need registered project metadata only. INPUT: optional project_root."""
    root = project_root_for_tool(project_root, tool="project_info")
    with mcp_audit(root, "project_info", arg_keys=["project_root"] if project_root else []):
        with session_scope() as db:
            result = get_project_info(db, root)
            bind_project_root(root)
            return _scoped(result, root)


def knowledge_search(query: str, project_root: str | None = None, limit: int = 8) -> list[dict]:
    """WHEN: you need reviewed project facts, invariants or fragile-area knowledge. Searches curated VERIFIED Project Knowledge only; current source remains authoritative."""
    root = project_root_for_tool(project_root, tool="knowledge_search")
    query = _text(query, tool="knowledge_search", field="query")
    bounded_limit = max(1, min(limit, 20))
    with mcp_audit(
        root, "knowledge_search", arg_keys=["query", "project_root", "limit"]
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_memory(db, project, query, bounded_limit)
            audit["metrics"] = {"hits": len(result), "limit": bounded_limit}
            return result


def memory_search(query: str, project_root: str | None = None, limit: int = 8) -> list[dict]:
    """Backward-compatible alias for knowledge_search. Prefer knowledge_search for reviewed semantic project facts."""
    root = project_root_for_tool(project_root, tool="memory_search")
    query = _text(query, tool="memory_search", field="query")
    bounded_limit = max(1, min(limit, 20))
    with mcp_audit(
        root, "memory_search", arg_keys=["query", "project_root", "limit"]
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_memory(db, project, query, bounded_limit)
            audit["metrics"] = {
                "hits": len(result),
                "limit": bounded_limit,
                "alias": "knowledge_search",
            }
            return result


def memory_context(
    task: str | None = None,
    query: str | None = None,
    project_root: str | None = None,
    limit: int = 4,
) -> dict:
    """Legacy composite context helper. It is no longer a workflow gate. Prefer project_status first, then project_search/knowledge_search/decision_search only when needed."""
    root = project_root_for_tool(project_root, tool="memory_context")
    current_task = (task or query or "").strip()
    if not current_task:
        raise ValueError(
            'memory_context: `task` is required. Example: memory_context(task="Fix duplicate payment creation", project_root="<workspace>").'
        )
    keys = ["task" if task else "query", "limit"] + (["project_root"] if project_root else [])
    with mcp_audit(root, "memory_context", arg_keys=keys) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = build_memory_context(db, project, current_task, max(1, min(limit, 12)))
            brief = result.get("task_brief") or {}
            audit["metrics"] = {
                "knowledge_hits": len(brief.get("verified_knowledge") or []),
                "history_hits": len(brief.get("relevant_history") or []),
                "legacy_composite": True,
            }
            return _scoped(result, root)


project_status = core_tool()(project_status)
project_search = core_tool()(project_search)
project_info = core_tool()(project_info)
knowledge_search = core_tool()(knowledge_search)
memory_search = core_tool()(memory_search)
memory_context = core_tool()(memory_context)
