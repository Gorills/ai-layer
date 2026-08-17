from __future__ import annotations

from ai_layer.application import work as work_uc
from ai_layer.audit.service import mcp_audit
from ai_layer.core.jsonutil import wire_value
from ai_layer.mcp.runtime import _scoped, _text, core_tool, project_root_for_tool
from ai_layer.mcp.tool_schema import (
    IdempotencyKey,
    ProjectPathList,
    WorkCheckList,
    WorkClientText,
    WorkGoalText,
    WorkHostText,
    WorkKeyText,
    WorkKind,
    WorkLinkKey,
    WorkMapDispositionInput,
    WorkRepositoryDeltaInput,
    WorkSessionText,
    WorkSummaryOptional,
)


def work_begin(
    goal: WorkGoalText,
    kind: WorkKind = "change",
    host: WorkHostText = "unknown",
    client: WorkClientText = "unknown",
    session_id: WorkSessionText = "",
    turn_id: WorkSessionText = "",
    model: WorkSessionText = "",
    linked_task_key: WorkLinkKey | None = None,
    linked_epic_key: WorkLinkKey | None = None,
    idempotency_key: IdempotencyKey | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: begin one substantive ordinary user request (change, diagnose, review, research, planning, or ops), including investigation that should fill Project Map. Call after project_status on the default substantive route; an explicit managed Task / standard Task protocol request routes directly to task_create instead. For short work pair this with work_complete and skip checkpoints. Reuse idempotency_key when retrying the same host event."""
    root = project_root_for_tool(project_root, tool="work_begin")
    goal = _text(goal, tool="work_begin", field="goal")
    with mcp_audit(
        root,
        "work_begin",
        arg_keys=[
            "goal",
            "kind",
            "host",
            "client",
            "session_id",
            "turn_id",
            "model",
            "linked_task_key",
            "linked_epic_key",
            "idempotency_key",
            "project_root",
        ],
    ) as audit:
        result = work_uc.begin(
            root,
            goal=goal,
            kind=kind,
            host=host,
            client=client,
            session_id=session_id,
            turn_id=turn_id,
            model=model,
            linked_task_key=(linked_task_key or "").strip() or None,
            linked_epic_key=(linked_epic_key or "").strip() or None,
            idempotency_key=(idempotency_key or "").strip() or None,
        )
        audit["metrics"] = {"work_key": (result.get("work") or {}).get("key"), "kind": kind}
        return _scoped(result, root)


def work_checkpoint(
    work_key: WorkKeyText,
    summary: WorkSummaryOptional = "",
    reviewed_paths: ProjectPathList | None = None,
    changed_paths: ProjectPathList | None = None,
    checks: WorkCheckList | None = None,
    repository_delta: WorkRepositoryDeltaInput | None = None,
    blocked: bool | None = None,
    linked_task_key: WorkLinkKey | None = None,
    linked_epic_key: WorkLinkKey | None = None,
    idempotency_key: IdempotencyKey | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: a long work phase reaches a meaningful milestone or blocker. Do not checkpoint every file/tool action. checks use bounded name/status/summary metadata, never raw output. repository_delta accepts only revision IDs, changed_files/insertions/deletions counts, dirty, and assurance. Optional linked_task_key / linked_epic_key may attach a project-scoped Task or Epic after begin. Reuse idempotency_key for delivery retries."""
    root = project_root_for_tool(project_root, tool="work_checkpoint")
    work_key = _text(work_key, tool="work_checkpoint", field="work_key")
    task_key = (linked_task_key or "").strip() or None
    epic_key = (linked_epic_key or "").strip() or None
    with mcp_audit(
        root,
        "work_checkpoint",
        arg_keys=[
            "work_key",
            "summary",
            "reviewed_paths",
            "changed_paths",
            "checks",
            "repository_delta",
            "blocked",
            "linked_task_key",
            "linked_epic_key",
            "idempotency_key",
            "project_root",
        ],
    ) as audit:
        result = work_uc.checkpoint(
            root,
            work_key=work_key,
            summary=summary,
            reviewed_paths=reviewed_paths,
            changed_paths=changed_paths,
            checks=wire_value(checks),
            repository_delta=wire_value(repository_delta),
            blocked=blocked,
            linked_task_key=task_key,
            linked_epic_key=epic_key,
            idempotency_key=(idempotency_key or "").strip() or None,
        )
        audit["metrics"] = {"work_key": work_key, "blocked": blocked}
        return _scoped(result, root)


def _terminal(
    operation: str,
    work_key: str,
    summary: str,
    reviewed_paths: ProjectPathList | None,
    changed_paths: ProjectPathList | None,
    checks: WorkCheckList | None,
    repository_delta: WorkRepositoryDeltaInput | None,
    map_disposition: WorkMapDispositionInput | None,
    idempotency_key: IdempotencyKey | None,
    project_root: str | None,
) -> dict:
    root = project_root_for_tool(project_root, tool=operation)
    work_key = _text(work_key, tool=operation, field="work_key")
    summary = (summary or "").strip()
    with mcp_audit(
        root,
        operation,
        arg_keys=[
            "work_key",
            "summary",
            "reviewed_paths",
            "changed_paths",
            "checks",
            "repository_delta",
            "map_disposition",
            "idempotency_key",
            "project_root",
        ],
    ) as audit:
        handler = getattr(work_uc, operation.removeprefix("work_"))
        result = handler(
            root,
            work_key=work_key,
            summary=summary,
            reviewed_paths=reviewed_paths,
            changed_paths=changed_paths,
            checks=wire_value(checks),
            repository_delta=wire_value(repository_delta),
            map_disposition=wire_value(map_disposition),
            idempotency_key=(idempotency_key or "").strip() or None,
        )
        work = result.get("work") or {}
        audit["metrics"] = {
            "work_key": work_key,
            "status": work.get("status"),
            "map_status": (work.get("map_disposition") or {}).get("status"),
        }
        return _scoped(result, root)


def work_complete(
    work_key: WorkKeyText,
    summary: WorkSummaryOptional = "",
    reviewed_paths: ProjectPathList | None = None,
    changed_paths: ProjectPathList | None = None,
    checks: WorkCheckList | None = None,
    repository_delta: WorkRepositoryDeltaInput | None = None,
    map_disposition: WorkMapDispositionInput | None = None,
    idempotency_key: IdempotencyKey | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: substantive work reached a terminal successful result. summary is optional: when omitted AI Layer reuses an existing Work summary or derives a truthful terminal summary from the known goal. checks may use canonical name/status/summary or a natural command/result report; raw command/result fields are normalized and are not persisted. A work-linked project_map_reconcile already persists reconciled map_disposition; omit it here to keep that value. If no reconciliation was recorded and map state is still pending, terminal closure records a truthful deferred disposition automatically."""
    return _terminal(
        "work_complete",
        work_key,
        summary,
        reviewed_paths,
        changed_paths,
        checks,
        repository_delta,
        map_disposition,
        idempotency_key,
        project_root,
    )


def work_fail(
    work_key: WorkKeyText,
    summary: WorkSummaryOptional = "",
    reviewed_paths: ProjectPathList | None = None,
    changed_paths: ProjectPathList | None = None,
    checks: WorkCheckList | None = None,
    repository_delta: WorkRepositoryDeltaInput | None = None,
    map_disposition: WorkMapDispositionInput | None = None,
    idempotency_key: IdempotencyKey | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: work terminated unsuccessfully rather than merely hitting a temporary blocker."""
    return _terminal(
        "work_fail",
        work_key,
        summary,
        reviewed_paths,
        changed_paths,
        checks,
        repository_delta,
        map_disposition,
        idempotency_key,
        project_root,
    )


def work_interrupt(
    work_key: WorkKeyText,
    summary: WorkSummaryOptional = "",
    reviewed_paths: ProjectPathList | None = None,
    changed_paths: ProjectPathList | None = None,
    checks: WorkCheckList | None = None,
    repository_delta: WorkRepositoryDeltaInput | None = None,
    map_disposition: WorkMapDispositionInput | None = None,
    idempotency_key: IdempotencyKey | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: work stops with useful continuation state and may be resumed by a later WorkItem or host session."""
    return _terminal(
        "work_interrupt",
        work_key,
        summary,
        reviewed_paths,
        changed_paths,
        checks,
        repository_delta,
        map_disposition,
        idempotency_key,
        project_root,
    )


def work_abandon(
    work_key: WorkKeyText,
    summary: WorkSummaryOptional = "",
    reviewed_paths: ProjectPathList | None = None,
    changed_paths: ProjectPathList | None = None,
    checks: WorkCheckList | None = None,
    repository_delta: WorkRepositoryDeltaInput | None = None,
    map_disposition: WorkMapDispositionInput | None = None,
    idempotency_key: IdempotencyKey | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: user/host intentionally abandons the WorkItem and it must no longer appear active."""
    return _terminal(
        "work_abandon",
        work_key,
        summary,
        reviewed_paths,
        changed_paths,
        checks,
        repository_delta,
        map_disposition,
        idempotency_key,
        project_root,
    )


work_begin = core_tool()(work_begin)
work_checkpoint = core_tool()(work_checkpoint)
work_complete = core_tool()(work_complete)
work_fail = core_tool()(work_fail)
work_interrupt = core_tool()(work_interrupt)
work_abandon = core_tool()(work_abandon)
