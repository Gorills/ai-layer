from __future__ import annotations

from pathlib import Path

from ai_layer.application import work as work_uc
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.memory.project_map_semantics import semantic_map_status


def _work_state(root: str) -> dict:
    try:
        return work_uc.state(root, limit=4)
    except Exception as exc:
        return {
            "active": [],
            "live": [],
            "recent": [],
            "attention": [],
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


def _map_state(root: str) -> dict:
    try:
        with session_scope() as db:
            project = get_project(db, Path(root))
            return semantic_map_status(db, project)
    except Exception as exc:
        return {
            "semantic_entries": 0,
            "semantic_current": 0,
            "semantic_stale": 0,
            "semantic_orphaned": 0,
            "semantic_missing": 0,
            "semantic_current_coverage": 0.0,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


def _truthful_state(project: dict, work: dict) -> tuple[str, str]:
    live = list(work.get("live") or [])
    active = list(work.get("active") or [])
    blocked = [item for item in active if item.get("status") == "blocked"]
    stale_active = [item for item in active if item.get("status") == "active"] if not live else []
    managed_task = project.get("task") or {}
    human_attention = bool(managed_task.get("human_attention_required"))
    if blocked:
        runtime_state = "blocked"
    elif live:
        runtime_state = "active"
    elif stale_active:
        runtime_state = "stale"
    else:
        runtime_state = "idle"
    if blocked or human_attention or stale_active:
        project_state = "attention"
    elif live:
        project_state = "working"
    else:
        project_state = "healthy"
    return runtime_state, project_state


def enrich_overview(payload: dict) -> dict:
    result = dict(payload)
    projects = []
    active_work = 0
    blocked_work = 0
    recent_work = 0
    active_bridges = 0
    for raw in list(payload.get("projects") or []):
        project = dict(raw)
        root = str(project.get("root") or "")
        work = _work_state(root)
        runtime_state, project_state = _truthful_state(project, work)
        bridges = list(project.get("agents") or [])
        active_bridges += sum(
            1 for item in bridges if item.get("activity_state") in {"ACTIVE", "WORKING"}
        )
        active_work += len(work.get("live") or [])
        blocked_work += sum(
            1 for item in work.get("active") or [] if item.get("status") == "blocked"
        )
        recent_work += len(work.get("recent") or [])
        project["runtime_state"] = runtime_state
        project["project_state"] = project_state
        project["work"] = work
        project["project_map"] = _map_state(root)
        project["mcp_bridges"] = bridges
        project["agents"] = bridges  # compatibility alias; UI must label these as MCP bridges.
        projects.append(project)
    summary = dict(payload.get("summary") or {})
    summary.update(
        {
            "active_work": active_work,
            "blocked_work": blocked_work,
            "recent_work": recent_work,
            "active_mcp_bridges": active_bridges,
        }
    )
    result["summary"] = summary
    result["projects"] = projects
    result["state_contract"] = (
        "working/active is derived from non-stale WorkItem AgentRuns. Open managed Tasks, MCP bridges and "
        "protocol traffic do not by themselves prove that native user work is running."
    )
    return result


def enrich_project(payload: dict) -> dict:
    result = dict(payload)
    project = dict(payload.get("project") or {})
    root = str(project.get("root") or "")
    work = _work_state(root)
    runtime_state, project_state = _truthful_state(project, work)
    bridges = list(project.get("agents") or [])
    project["runtime_state"] = runtime_state
    project["project_state"] = project_state
    project["work"] = work
    project["project_map"] = _map_state(root)
    project["mcp_bridges"] = bridges
    project["agents"] = bridges
    result["project"] = project
    read_models = dict(result.get("read_models") or {})
    read_models["work"] = work
    read_models["mcp_bridges"] = bridges
    result["read_models"] = read_models
    result["state_contract"] = (
        "Project working state follows observed non-stale WorkItem AgentRuns; managed workflow and bridge "
        "state remain separate read models."
    )
    return result
