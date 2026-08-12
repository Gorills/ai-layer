from __future__ import annotations

from ai_layer.application.transport import application_scope as session_scope
from ai_layer.application.transport import decision_search as search_decisions
from ai_layer.application.transport import list_sessions as app_list_sessions
from ai_layer.application.transport import restore_session as app_restore_session
from ai_layer.application.transport import save_session as app_save_session
from ai_layer.application.transport import task_current as db_current_task
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import _list, _project, _scoped, _text, core_tool, project_root_for_tool
from ai_layer.privacy.service import privacy_check


def session_list(project_root: str | None = None, limit: int = 20) -> list[dict]:
    """WHEN: explicit historical WorkSession inspection/debugging only. INPUT: optional project_root and limit. Normal continuation starts with project_status; use session_restore only when unmanaged narrative handoff context is specifically needed."""
    root = project_root_for_tool(project_root, tool="session_list")
    with mcp_audit(root, "session_list", arg_keys=["project_root", "limit"]):
        with session_scope() as db:
            project = _project(db, root)
            return app_list_sessions(db, project, max(1, min(limit, 50)))


def session_restore(session_id: str = "latest", project_root: str | None = None) -> dict | None:
    """WHEN: unmanaged prior-work narrative/handoff is specifically needed after project_status did not provide sufficient durable Task/Epic continuation state. INPUT: session_id="latest" (default) or exact id, optional project_root. WorkSession text is historical context, not current source truth and not a substitute for task_next/epic_next."""
    root = project_root_for_tool(project_root, tool="session_restore")
    wanted = (session_id or "latest").strip() or "latest"
    with mcp_audit(root, "session_restore", arg_keys=["session_id", "project_root"]) as audit:
        with session_scope() as db:
            project = _project(db, root)
            item = app_restore_session(db, project, wanted)
            audit["metrics"] = {"found": item is not None}
            return _scoped(item, root) if item else None


def session_save(
    goal: str,
    current_state: str,
    completed_actions: list[str] | str | None = None,
    next_steps: list[str] | str | None = None,
    important_decisions: list[str] | str | None = None,
    verified_facts: list[str] | str | None = None,
    notable_findings: list[str] | str | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: terminal handoff for substantive work intentionally performed outside a managed Task. Managed Tasks save exactly one terminal WorkSession automatically after the final review gate and MUST NOT call this tool for individual stages or after automatic completion. INPUT: goal + current_state required; list fields also accept one string. Use important_decisions only for new consequential choices; verified_facts for confirmed current behavior; notable_findings for review/investigation/advisory findings. Keep all fields compact."""
    root = project_root_for_tool(project_root, tool="session_save")
    goal = _text(goal, tool="session_save", field="goal")
    current_state = _text(current_state, tool="session_save", field="current_state")
    with mcp_audit(
        root,
        "session_save",
        arg_keys=[
            "goal",
            "current_state",
            "completed_actions",
            "next_steps",
            "important_decisions",
            "verified_facts",
            "notable_findings",
            "project_root",
        ],
    ) as audit:
        privacy = privacy_check(root)
        if not privacy.get("ok", True):
            raise RuntimeError(
                "Strict-private privacy check failed before session_save: "
                + "; ".join(
                    f"{item.get('path')}:{item.get('line', '-')} {item.get('code')}"
                    for item in privacy.get("violations", [])[:8]
                )
            )
        with session_scope() as db:
            project = _project(db, root)
            runtime = db_current_task(db, project)
            if runtime.get("active"):
                managed = runtime.get("task") or {}
                raise RuntimeError(
                    f"session_save is disabled while managed task {managed.get('key') or ''} is "
                    "active/blocked. Complete the current managed Task stage instead; the final "
                    "WorkSession handoff is written automatically after the review gates pass."
                )
            completed = _list(completed_actions)
            next_items = _list(next_steps)
            decisions = _list(important_decisions)
            facts = _list(verified_facts)
            findings = _list(notable_findings)
            item = app_save_session(
                db,
                project,
                goal=goal,
                completed_actions=completed,
                current_state=current_state,
                next_steps=next_items,
                important_decisions=decisions,
                verified_facts=facts,
                notable_findings=findings,
            )
            audit["metrics"] = {
                "completed_actions": len(completed),
                "next_steps": len(next_items),
                "decisions": len(decisions),
                "verified_facts": len(facts),
                "findings": len(findings),
            }
            return _scoped(item, root)


def decision_search(query: str, project_root: str | None = None, limit: int = 8) -> list[dict]:
    """WHEN: REQUIRED before choosing/designing/replacing/introducing/materially changing a consequential architecture/provider/API/migration/auth/security/concurrency/persistence approach among plausible alternatives when prior rationale may matter. INPUT: query, optional project_root/limit. Searches durable Decision/session rationale only; current source belongs to host-native tools and reviewed project facts/invariants belong to knowledge_search."""
    root = project_root_for_tool(project_root, tool="decision_search")
    query = _text(query, tool="decision_search", field="query")
    with mcp_audit(root, "decision_search", arg_keys=["query", "project_root", "limit"]) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = search_decisions(db, project, query, max(1, min(limit, 20)))
            audit["metrics"] = {"hits": len(result), "limit": max(1, min(limit, 20))}
            return result


# MCP schema/handler registration remains local to this capability adapter.
session_list = core_tool()(session_list)
session_restore = core_tool()(session_restore)
session_save = core_tool()(session_save)
decision_search = core_tool()(decision_search)
