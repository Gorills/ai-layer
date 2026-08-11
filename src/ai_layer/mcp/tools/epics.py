from __future__ import annotations

from ai_layer.application import epics as app_epics
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import _scoped, _text, core_tool, project_root_for_tool


def _with_root(payload: dict, root: str) -> dict:
    return _scoped(payload, root)


@core_tool()
def epic_create(title: str, spec_markdown: str, project_root: str | None = None) -> dict:
    """WHEN: the user says the planned product/architecture is understood and asks to create an Epic. INPUT: complete human-readable final-product specification, not a task list. Creates immutable spec v1 in DRAFT; implementation Tasks are forbidden until approval and Phase 0."""
    root = project_root_for_tool(project_root, tool="epic_create")
    title = _text(title, tool="epic_create", field="title")
    spec_markdown = _text(spec_markdown, tool="epic_create", field="spec_markdown")
    with mcp_audit(
        root,
        "epic_create",
        arg_keys=["title", "spec_markdown", "project_root"],
    ) as audit:
        result = app_epics.create(root, title=title, spec_markdown=spec_markdown)
        audit["metrics"] = {
            "epic": result.get("key"),
            "spec_version": result.get("current_spec_version"),
        }
        return _with_root(result, root)


@core_tool()
def epic_list(project_root: str | None = None, include_archived: bool = True) -> dict:
    """List durable Epics for the registered project. Use epic_get for the full specification/history."""
    root = project_root_for_tool(project_root, tool="epic_list")
    with mcp_audit(
        root,
        "epic_list",
        arg_keys=["project_root", "include_archived"],
    ) as audit:
        items = app_epics.list_for_project(root, include_archived=include_archived)
        audit["metrics"] = {"epics": len(items)}
        return _with_root({"epics": items}, root)


@core_tool()
def epic_get(
    epic_key: str,
    project_root: str | None = None,
    include_history: bool = True,
) -> dict:
    """AUTHORITATIVE EPIC READ. Returns current full spec, spec versions, unlimited audit history, plan and linked Task states. Use this instead of chat memory for Phase 0, execution and final review."""
    root = project_root_for_tool(project_root, tool="epic_get")
    key = _text(epic_key, tool="epic_get", field="epic_key")
    with mcp_audit(
        root,
        "epic_get",
        arg_keys=["epic_key", "project_root", "include_history"],
    ) as audit:
        result = app_epics.get(root, key=key, include_history=include_history)
        audit["metrics"] = {"epic": result.get("key"), "status": result.get("status")}
        return _with_root(result, root)


@core_tool()
def epic_spec_revise(
    epic_key: str,
    spec_markdown: str,
    change_summary: str,
    rationale: str = "",
    project_root: str | None = None,
) -> dict:
    """WHEN: a DRAFT or already-approved-but-not-started Epic changes before Phase 0. Creates a new immutable spec version, returns the Epic to DRAFT and requires explicit reapproval. Execution-time human decisions are resolved through epic_reconcile_complete."""
    root = project_root_for_tool(project_root, tool="epic_spec_revise")
    result = app_epics.revise_spec(
        root,
        key=_text(epic_key, tool="epic_spec_revise", field="epic_key"),
        spec_markdown=_text(spec_markdown, tool="epic_spec_revise", field="spec_markdown"),
        change_summary=_text(change_summary, tool="epic_spec_revise", field="change_summary"),
        rationale=rationale,
    )
    return _with_root(result, root)


@core_tool()
def epic_audit_record(
    epic_key: str,
    summary: str,
    findings: list[dict] | None = None,
    scope: str = "independent",
    auditor_id: str = "",
    project_root: str | None = None,
) -> dict:
    """WHEN: an independent Epic specification audit has actually been performed before Phase 0, including after approval but before execution starts. Records findings against the exact current spec version. Audit rounds are unlimited; revision after approval returns the Epic to DRAFT and requires reapproval."""
    root = project_root_for_tool(project_root, tool="epic_audit_record")
    result = app_epics.record_audit(
        root,
        key=_text(epic_key, tool="epic_audit_record", field="epic_key"),
        summary=_text(summary, tool="epic_audit_record", field="summary"),
        findings=findings,
        scope=scope,
        auditor_id=auditor_id,
    )
    return _with_root(result, root)


@core_tool()
def epic_approve(epic_key: str, project_root: str | None = None) -> dict:
    """HUMAN GATE. Call only after the user explicitly says the current Epic specification is approved/agreed. Freezes approved_spec_version; Phase 0 still may create a newer execution spec for obvious reality corrections without rewriting the approved baseline."""
    root = project_root_for_tool(project_root, tool="epic_approve")
    result = app_epics.approve(
        root,
        key=_text(epic_key, tool="epic_approve", field="epic_key"),
    )
    return _with_root(result, root)


@core_tool()
def epic_next(epic_key: str, project_root: str | None = None) -> dict:
    """PRIMARY EPIC NAVIGATOR. Call after create/audit/revision/approval, after every linked Task transition/completion, and after context loss. Returns the exact next allowed Epic action/tool. Never infer Epic position from chat history."""
    root = project_root_for_tool(project_root, tool="epic_next")
    key = _text(epic_key, tool="epic_next", field="epic_key")
    with mcp_audit(root, "epic_next", arg_keys=["epic_key", "project_root"]) as audit:
        result = app_epics.next_action(root, key=key)
        action = result.get("next_action") or {}
        audit["metrics"] = {
            "epic": key,
            "action": action.get("action"),
            "tool": action.get("tool"),
        }
        return _with_root(result, root)


@core_tool()
def epic_start_next(epic_key: str, project_root: str | None = None) -> dict:
    """WHEN: epic_next explicitly returns this tool. Starts exactly one eligible Task: mandatory Phase 0, targeted drift reconciliation, next STANDARD implementation Task, or the final closure/full-Epic-review Task. Never call speculatively."""
    root = project_root_for_tool(project_root, tool="epic_start_next")
    key = _text(epic_key, tool="epic_start_next", field="epic_key")
    state = app_epics.get(root, key=key, include_history=False)
    if state.get("status") == "blocked" and str(state.get("blocked_reason") or "").startswith(
        "repository_drift_detected"
    ):
        result = app_epics.start_drift_reconciliation(root, key=key)
    else:
        result = app_epics.start_next(root, key=key)
    return _with_root(result, root)


@core_tool()
def epic_reconcile_complete(
    epic_key: str,
    summary: str,
    updated_spec: str | None = None,
    corrections: list[dict] | None = None,
    human_decisions: list[dict] | None = None,
    remaining_plan: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: epic_next says record_phase0_reconciliation/record_drift_reconciliation, or returns this as resolution_tool for a blocked human decision, and the linked analysis-only Task is completed. Applies non-branching durable corrections automatically. human_decisions is only for genuine material trade-offs; after the user resolves one, call again with the resolved updated_spec and human_decisions=[]."""
    root = project_root_for_tool(project_root, tool="epic_reconcile_complete")
    result = app_epics.reconcile_complete(
        root,
        key=_text(epic_key, tool="epic_reconcile_complete", field="epic_key"),
        summary=_text(summary, tool="epic_reconcile_complete", field="summary"),
        updated_spec=updated_spec,
        corrections=corrections,
        human_decisions=human_decisions,
        remaining_plan=remaining_plan,
    )
    return _with_root(result, root)


@core_tool()
def epic_plan_set(
    epic_key: str,
    work_items: list[dict],
    project_root: str | None = None,
) -> dict:
    """WHEN: epic_next says create_task_plan after successful Phase 0. INPUT only implementation work items. AI Layer automatically preserves Phase 0 as item 0 and appends the mandatory final documentation/Project-Knowledge/full-Epic-review Task. Every work item is forced through STANDARD Task lifecycle."""
    root = project_root_for_tool(project_root, tool="epic_plan_set")
    if not isinstance(work_items, list):
        raise ValueError("epic_plan_set: `work_items` must be a list of task objects")
    result = app_epics.set_plan(
        root,
        key=_text(epic_key, tool="epic_plan_set", field="epic_key"),
        work_items=work_items,
    )
    return _with_root(result, root)


@core_tool()
def epic_archive(epic_key: str, project_root: str | None = None) -> dict:
    """WHEN: epic_next says archive. Allowed only after the final STANDARD Task passed and mechanical closure gates prove documentation changed and reviewed Project Knowledge was published. Preserves all spec versions, audits, plan/Task links and evidence."""
    root = project_root_for_tool(project_root, tool="epic_archive")
    result = app_epics.archive(
        root,
        key=_text(epic_key, tool="epic_archive", field="epic_key"),
    )
    return _with_root(result, root)


__all__ = [
    "epic_create",
    "epic_list",
    "epic_get",
    "epic_spec_revise",
    "epic_audit_record",
    "epic_approve",
    "epic_next",
    "epic_start_next",
    "epic_reconcile_complete",
    "epic_plan_set",
    "epic_archive",
]
