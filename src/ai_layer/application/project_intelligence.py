from __future__ import annotations

from pathlib import Path

from ai_layer.application import epics as epic_uc
from ai_layer.application import tasks as task_uc
from ai_layer.application import work as work_uc
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.domain.agent_contract import PROJECT_SEARCH_MAX_QUERIES, agent_runtime_contract
from ai_layer.domain.project_map import project_map_capability_contract
from ai_layer.epics.contracts import EPIC_EXECUTION_STATUSES, EPIC_OPEN_STATUSES
from ai_layer.memory.navigation import project_map_status, search_project_map
from ai_layer.memory.project_map_search import merge_project_search, search_semantic_map
from ai_layer.memory.project_map_semantics import reconcile_project_map, semantic_map_status
from ai_layer.memory.refresh_runtime import interactive_freshness
from ai_layer.policy.project_policy import project_policy_snapshot
from ai_layer.workspace.status import repository_runtime_status


def _compact_task(item: dict | None) -> dict | None:
    if not item:
        return None
    stage = dict(item.get("active_stage") or {})
    return {
        "id": item.get("id"),
        "key": item.get("key"),
        "goal": item.get("goal"),
        "status": item.get("status"),
        "workflow_profile": item.get("workflow_profile"),
        "risk_level": item.get("risk_level"),
        "updated_at": item.get("updated_at"),
        "active_stage": (
            {
                "id": stage.get("id"),
                "kind": stage.get("kind"),
                "status": stage.get("status"),
                "worker_id": stage.get("worker_id"),
            }
            if stage
            else None
        ),
        "next_action": item.get("next_action"),
        "open_findings": int(item.get("open_findings") or 0),
    }


def _epic_state(project_root: str | Path) -> dict:
    try:
        rows = epic_uc.list_for_project(project_root, include_archived=False)
    except Exception as exc:
        return {
            "available": False,
            "active": None,
            "open": [],
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }
    open_rows = [row for row in rows if row.get("status") in EPIC_OPEN_STATUSES]
    execution = next(
        (row for row in open_rows if row.get("status") in EPIC_EXECUTION_STATUSES),
        None,
    )

    def compact(item: dict) -> dict:
        return {
            "id": item.get("id"),
            "key": item.get("key"),
            "title": item.get("title"),
            "status": item.get("status"),
            "updated_at": item.get("updated_at"),
        }

    return {
        "available": True,
        "active": compact(execution) if execution else None,
        "open": [compact(item) for item in open_rows[:8]],
    }


def _ordinary_work_focus(ordinary_work: dict) -> dict | None:
    live = list(ordinary_work.get("live") or [])
    if live:
        return live[0]
    for item in ordinary_work.get("active") or []:
        if not item.get("live"):
            return item
    return None


def _continuation(
    active_task: dict | None,
    active_work: dict | None,
    active_epic: dict | None,
) -> dict:
    if active_task:
        return {
            "kind": "task",
            "key": active_task.get("key"),
            "goal": active_task.get("goal"),
            "navigator": "task_next",
            "next_action": active_task.get("next_action"),
            "instruction": (
                "This project has an in-progress managed Task. Resume its strict Task procedure rather than "
                "rediscovering repository state."
            ),
        }
    if active_work:
        if active_work.get("live"):
            instruction = (
                "This project has live ordinary Work. Resume it through host-native execution and keep the "
                "same WorkItem; checkpoint only at a meaningful milestone or blocker."
            )
        else:
            instruction = (
                "This project has stale ordinary Work. Resume or terminate that WorkItem; "
                "do not start a new WorkItem."
            )
        return {
            "kind": "work",
            "key": active_work.get("key"),
            "goal": active_work.get("goal"),
            "navigator": None,
            "instruction": instruction,
        }
    if active_epic:
        return {
            "kind": "epic",
            "key": active_epic.get("key"),
            "title": active_epic.get("title"),
            "navigator": "epic_next",
            "instruction": "This project has an executing Epic. Resume this Epic.",
        }
    return {
        "kind": "none",
        "navigator": None,
        "instruction": "No live work is currently observed; handle the user's new request natively.",
    }


def project_status(project_root: str | Path) -> dict:
    """Return cheap durable work state, effective policy and Project Map freshness."""
    root = Path(project_root).expanduser().resolve()
    task_state = task_uc.read_state(root, include_history=False)
    active_task = _compact_task(task_state.get("current"))
    latest_task = _compact_task(task_state.get("latest"))
    epic_state = _epic_state(root)
    active_epic = epic_state.get("active")
    ordinary_work = work_uc.state(root, limit=8)
    live_work = list(ordinary_work.get("live") or [])
    active_work = _ordinary_work_focus(ordinary_work)
    repository = repository_runtime_status(root)
    policy = project_policy_snapshot(root)

    with session_scope() as db:
        project = get_project(db, root)
        freshness = interactive_freshness(project)
        map_state = project_map_status(db, project)
        map_state.update(semantic_map_status(db, project))
        project_payload = {
            "id": str(project.id),
            "name": project.name,
            "root_path": project.root_path,
            "languages": dict(project.languages or {}),
        }

    focus = active_task or active_work or active_epic
    if active_task:
        focus_payload = {
            "kind": "task",
            "key": active_task.get("key"),
            "goal": active_task.get("goal"),
        }
    elif active_work:
        focus_payload = {
            "kind": "work",
            "key": active_work.get("key"),
            "goal": active_work.get("goal"),
        }
    elif active_epic:
        focus_payload = {
            "kind": "epic",
            "key": active_epic.get("key"),
            "title": active_epic.get("title"),
        }
    else:
        focus_payload = None

    return {
        "agent_contract": agent_runtime_contract(),
        "project": project_payload,
        "project_policy": policy,
        "repository": repository,
        "work": {
            "active_work": list(ordinary_work.get("active") or []),
            "live_work": live_work,
            "recent_work": list(ordinary_work.get("recent") or []),
            "work_attention": list(ordinary_work.get("attention") or []),
            "active_task": active_task,
            "latest_task": latest_task if active_task is None else None,
            "active_epic": active_epic,
            "open_epics": epic_state.get("open") or [],
            "current_focus": focus_payload,
            "continuation": _continuation(active_task, active_work, active_epic),
            "state_source": task_state.get("source"),
            "observability_contract": ordinary_work.get("observability_contract"),
        },
        "index": {
            "project_map": map_state,
            "freshness": {
                "status": freshness.get("status"),
                "snapshot_available": freshness.get("snapshot_available"),
                "background_refresh": freshness.get("background_refresh"),
                "refresh_job": freshness.get("refresh_job"),
                "changed_paths": list(freshness.get("changed_paths") or [])[:20],
                "read_contract": freshness.get("read_contract"),
            },
        },
        "guidance": {
            "source_of_truth": "current repository source via host-native tools",
            "project_policy": (
                "Apply project_status.project_policy before implementation; use its version/hash to detect drift."
            ),
            "ordinary_work": (
                "Substantive host-native requests use WorkItem lifecycle. Managed Task is optional assurance, "
                "not the ordinary-work identity."
            ),
            "unknown_code_location": (
                "Call project_search before broad repository grep/search. For non-English goals, use a concise "
                "English code-centric primary query, preserve exact identifiers, and use at most one original "
                "or mixed widening variant."
            ),
            "known_code_location": (
                "If the user already supplied a precise file/symbol, open it directly after this status call; "
                "project_search is unnecessary ceremony."
            ),
            "execution_owner": "host-native agent runtime",
            "managed_workflow": (
                "Use task_next/epic_next only when resuming or explicitly choosing a managed Task/Epic flow."
            ),
            "project_map": project_map_capability_contract(),
        },
        "active": bool(focus),
    }


def _search_queries(query: str, query_variants: list[str] | None) -> list[str]:
    primary = " ".join(str(query or "").split())
    if not primary:
        raise ValueError("project_search query is required")
    variants = list(query_variants or [])
    if len(variants) > PROJECT_SEARCH_MAX_QUERIES - 1:
        raise ValueError(
            f"project_search accepts at most {PROJECT_SEARCH_MAX_QUERIES} total query variants"
        )
    result = [primary]
    seen = {primary.casefold()}
    for raw in variants:
        item = " ".join(str(raw or "").split())
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result


def _search_once(db, project, query: str) -> tuple[dict, str | None]:
    structural = search_project_map(db, project, query, limit=20)
    semantic_error = None
    try:
        semantic = search_semantic_map(db, project, query, limit=40)
    except Exception as exc:
        semantic = []
        semantic_error = f"{type(exc).__name__}: {exc}"[:300]
    result = merge_project_search(structural, semantic, limit=20)
    if semantic_error:
        result["search_mode"] = structural.get("search_mode", "lexical_metadata")
    return result, semantic_error


def _fuse_search(results: list[tuple[str, dict]], limit: int) -> dict:
    primary_query, primary = results[0]
    fused = dict(primary)
    by_path: dict[str, dict] = {}
    for used_query, payload in results:
        for raw in list(payload.get("matches") or []):
            item = dict(raw)
            path = str(item.get("path") or "")
            if not path:
                continue
            existing = by_path.get(path)
            if existing is None or float(item.get("score") or 0.0) > float(
                existing.get("score") or 0.0
            ):
                previous_queries = list(existing.get("matched_queries") or []) if existing else []
                item["matched_queries"] = list(dict.fromkeys([*previous_queries, used_query]))
                by_path[path] = item
            else:
                existing["matched_queries"] = list(
                    dict.fromkeys([*list(existing.get("matched_queries") or []), used_query])
                )
    matches = sorted(
        by_path.values(),
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )[:limit]
    fused["query"] = primary_query
    fused["queries_used"] = [item[0] for item in results]
    fused["matches"] = matches
    fused["query_contract"] = {
        "primary": "English code-centric for non-English natural-language intent",
        "identifiers": "preserved verbatim",
        "max_queries": PROJECT_SEARCH_MAX_QUERIES,
        "source_verification_required": True,
    }
    return fused


def project_search(
    project_root: str | Path,
    query: str,
    limit: int = 8,
    query_variants: list[str] | None = None,
) -> dict:
    """Search bounded structural + semantic Project Map breadcrumbs; never return source bodies."""
    root = Path(project_root).expanduser().resolve()
    bounded_limit = max(1, min(int(limit), 20))
    queries = _search_queries(query, query_variants)
    semantic_errors: dict[str, str] = {}
    with session_scope() as db:
        project = get_project(db, root)
        freshness = interactive_freshness(project)
        per_query: list[tuple[str, dict]] = []
        for item in queries:
            search_result, error = _search_once(db, project, item)
            per_query.append((item, search_result))
            if error:
                semantic_errors[item] = error
        result = _fuse_search(per_query, bounded_limit)
        if semantic_errors:
            result["semantic_search_degraded"] = semantic_errors
        map_state = dict(result.get("map") or {})
        map_state.update(semantic_map_status(db, project))
        result["map"] = map_state
    result["freshness"] = {
        "status": freshness.get("status"),
        "snapshot_available": freshness.get("snapshot_available"),
        "background_refresh": freshness.get("background_refresh"),
        "refresh_job": freshness.get("refresh_job"),
        "changed_paths": list(freshness.get("changed_paths") or [])[:20],
        "read_contract": freshness.get("read_contract"),
    }
    if freshness.get("status") not in {"fresh", "refreshed"}:
        result["source_verification_required"] = True
    return result


def project_map_reconcile(
    project_root: str | Path,
    *,
    entries: list[dict] | None = None,
    remove_paths: list[str] | None = None,
    scope_paths: list[str] | None = None,
    source_task_key: str | None = None,
    source_work_key: str | None = None,
    no_changes_reason: str | None = None,
) -> dict:
    """Persist bounded semantic Project Map knowledge learned from real source work."""
    root = Path(project_root).expanduser().resolve()
    with session_scope() as db:
        project = get_project(db, root)
        result = reconcile_project_map(
            db,
            project,
            entries=entries,
            remove_paths=remove_paths,
            scope_paths=scope_paths,
            source_task_key=source_task_key,
            source_work_key=source_work_key,
            no_changes_reason=no_changes_reason,
        )
        map_state = project_map_status(db, project)
        map_state.update(semantic_map_status(db, project))
        result["map"] = map_state
        return result
