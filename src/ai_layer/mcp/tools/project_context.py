from __future__ import annotations

from ai_layer.application.transport import application_scope as session_scope
from ai_layer.application.transport import knowledge_search as search_knowledge
from ai_layer.application.transport import memory_context as build_memory_context
from ai_layer.application.transport import project_info as get_project_info
from ai_layer.application.transport import project_map_reconcile as reconcile_project_map
from ai_layer.application.transport import project_search as search_project
from ai_layer.application.transport import project_status as get_project_status
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.context import bind_project_root
from ai_layer.mcp.runtime import _project, _scoped, _text, core_tool, project_root_for_tool


def project_status(project_root: str | None = None) -> dict:
    """WHEN: first state call for registered-project work. Returns Work/Task/Epic/Git/index/effective-policy state without scanning source."""
    root = project_root_for_tool(project_root, tool="project_status")
    with mcp_audit(
        root,
        "project_status",
        arg_keys=["project_root"] if project_root else [],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = get_project_status(db, project)
            bind_project_root(root)
            work = result.get("work") or {}
            map_state = (result.get("index") or {}).get("project_map") or {}
            policy = result.get("project_policy") or {}
            audit["metrics"] = {
                "active_work": len(work.get("active_work") or []),
                "live_work": len(work.get("live_work") or []),
                "active_task": bool(work.get("active_task")),
                "active_epic": bool(work.get("active_epic")),
                "dirty": (result.get("repository") or {}).get("dirty"),
                "navigation_files": int(map_state.get("navigation_files") or 0),
                "symbols": int(map_state.get("symbol_count") or 0),
                "semantic_current": int(map_state.get("semantic_current") or 0),
                "semantic_stale": int(map_state.get("semantic_stale") or 0),
                "semantic_missing": int(map_state.get("semantic_missing") or 0),
                "policy_chars": int(policy.get("chars") or 0),
                "policy_version": policy.get("version"),
            }
            return _scoped(result, root)


def project_search(
    query: str,
    project_root: str | None = None,
    limit: int = 8,
    query_variants: list[str] | None = None,
) -> dict:
    """WHEN: code location is unknown. PRIMARY QUERY CONTRACT: for non-English natural-language intent, send concise English code-centric retrieval terms and preserve exact code identifiers verbatim. Optionally pass at most one original-language/mixed query_variants entry to widen domain aliases. Returns Project Map breadcrumbs only; open current source before claims/edits."""
    root = project_root_for_tool(project_root, tool="project_search")
    query = _text(query, tool="project_search", field="query")
    bounded_limit = max(1, min(limit, 20))
    variants = list(query_variants or [])
    with mcp_audit(
        root,
        "project_search",
        arg_keys=["query", "project_root", "limit", "query_variants"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_project(
                db,
                project,
                query,
                bounded_limit,
                query_variants=variants,
            )
            matches = list(result.get("matches") or [])
            audit["metrics"] = {
                "hits": len(matches),
                "limit": bounded_limit,
                "queries_used": len(result.get("queries_used") or [query]),
                "top_score": matches[0].get("score") if matches else None,
                "search_mode": result.get("search_mode"),
                "semantic_hits": sum(1 for item in matches if item.get("semantic")),
                "semantic_degraded": bool(result.get("semantic_search_degraded")),
            }
            return _scoped(result, root)


def project_map_reconcile(
    entries: list[dict] | None = None,
    remove_paths: list[str] | None = None,
    scope_paths: list[str] | None = None,
    source_task_key: str | None = None,
    no_changes_reason: str | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: after meaningful real work established better navigation facts. Reconcile only inspected/affected paths. Canonical purpose/responsibilities/hints must be concise English; keep code identifiers exact and put useful Russian/other aliases in domain_terms. For Epic finalization pass source_task_key so closure has durable ProjectMapReconciled evidence."""
    root = project_root_for_tool(project_root, tool="project_map_reconcile")
    with mcp_audit(
        root,
        "project_map_reconcile",
        arg_keys=[
            "entries",
            "remove_paths",
            "scope_paths",
            "source_task_key",
            "no_changes_reason",
            "project_root",
        ],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = reconcile_project_map(
                db,
                project,
                entries=entries,
                remove_paths=remove_paths,
                scope_paths=scope_paths,
                source_task_key=(source_task_key or "").strip() or None,
                no_changes_reason=(no_changes_reason or "").strip() or None,
            )
            audit["metrics"] = {
                "updated": len(result.get("updated") or []),
                "removed": len(result.get("removed") or []),
                "scope_paths": len(result.get("scope_paths") or []),
                "source_ref": result.get("source_ref"),
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


def knowledge_search(
    query: str,
    project_root: str | None = None,
    limit: int = 8,
) -> list[dict]:
    """WHEN: you need reviewed project facts, invariants or fragile-area knowledge. Searches curated VERIFIED Project Knowledge only; current source remains authoritative."""
    root = project_root_for_tool(project_root, tool="knowledge_search")
    query = _text(query, tool="knowledge_search", field="query")
    bounded_limit = max(1, min(limit, 20))
    with mcp_audit(
        root,
        "knowledge_search",
        arg_keys=["query", "project_root", "limit"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_knowledge(db, project, query, bounded_limit)
            audit["metrics"] = {"hits": len(result), "limit": bounded_limit}
            return result


def memory_search(
    query: str,
    project_root: str | None = None,
    limit: int = 8,
) -> list[dict]:
    """Backward-compatible alias for knowledge_search. Prefer knowledge_search for reviewed semantic project facts."""
    root = project_root_for_tool(project_root, tool="memory_search")
    query = _text(query, tool="memory_search", field="query")
    bounded_limit = max(1, min(limit, 20))
    with mcp_audit(
        root,
        "memory_search",
        arg_keys=["query", "project_root", "limit"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_knowledge(db, project, query, bounded_limit)
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
    """Legacy compatibility helper. Without task/query it serves project_status; otherwise it returns a compact knowledge brief. Prefer focused Project Intelligence tools."""
    root = project_root_for_tool(project_root, tool="memory_context")
    current_task = (task or query or "").strip()
    keys = (["task"] if task else (["query"] if query else [])) + ["limit"]
    if project_root:
        keys.append("project_root")
    with mcp_audit(root, "memory_context", arg_keys=keys) as audit:
        with session_scope() as db:
            project = _project(db, root)
            if not current_task:
                result = dict(get_project_status(db, project))
                result["compatibility"] = {
                    "requested_tool": "memory_context",
                    "served_as": "project_status",
                    "reason": (
                        "No task/query was supplied. memory_context is legacy; project_status is the current "
                        "startup and continuation surface."
                    ),
                }
                bind_project_root(root)
                audit["metrics"] = {
                    "legacy_composite": False,
                    "served_as": "project_status",
                }
                return _scoped(result, root)

            result = build_memory_context(
                db,
                project,
                current_task,
                max(1, min(limit, 12)),
            )
            hints = list(result.get("knowledge_hints") or [])
            audit["metrics"] = {
                "knowledge_hits": len(hints),
                "legacy_composite": True,
                "compact_compatibility": True,
            }
            return _scoped(result, root)


project_status = core_tool()(project_status)
project_search = core_tool()(project_search)
project_map_reconcile = core_tool()(project_map_reconcile)
project_info = core_tool()(project_info)
knowledge_search = core_tool()(knowledge_search)
memory_search = core_tool()(memory_search)
memory_context = core_tool()(memory_context)
