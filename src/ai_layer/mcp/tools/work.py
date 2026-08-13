from __future__ import annotations

from ai_layer.application import work as work_uc
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import _scoped, _text, core_tool, project_root_for_tool


def work_begin(
    goal: str,
    kind: str = "change",
    host: str = "unknown",
    client: str = "unknown",
    session_id: str = "",
    turn_id: str = "",
    model: str = "",
    linked_task_key: str | None = None,
    linked_epic_key: str | None = None,
    idempotency_key: str | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: begin one substantive user request performed through normal host-native execution. One WorkItem records what happened; a managed Task remains optional assurance. For short work pair this with work_complete and skip checkpoints. Reuse idempotency_key when retrying the same host event."""
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
    work_key: str,
    summary: str = "",
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    blocked: bool | None = None,
    idempotency_key: str | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: a long work phase reaches a meaningful milestone or blocker. Do not checkpoint every file/tool action. checks use bounded name/status/summary metadata, never raw output. repository_delta accepts only revision IDs, changed_files/insertions/deletions counts, dirty, and assurance. Reuse idempotency_key for delivery retries."""
    root = project_root_for_tool(project_root, tool="work_checkpoint")
    work_key = _text(work_key, tool="work_checkpoint", field="work_key")
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
            checks=checks,
            repository_delta=repository_delta,
            blocked=blocked,
            idempotency_key=(idempotency_key or "").strip() or None,
        )
        audit["metrics"] = {"work_key": work_key, "blocked": blocked}
        return _scoped(result, root)


def _terminal(
    operation: str,
    work_key: str,
    summary: str,
    reviewed_paths: list[str] | None,
    changed_paths: list[str] | None,
    checks: list[dict] | None,
    repository_delta: dict | None,
    map_disposition: dict | None,
    idempotency_key: str | None,
    project_root: str | None,
) -> dict:
    root = project_root_for_tool(project_root, tool=operation)
    work_key = _text(work_key, tool=operation, field="work_key")
    summary = _text(summary, tool=operation, field="summary")
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
            checks=checks,
            repository_delta=repository_delta,
            map_disposition=map_disposition,
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
    work_key: str,
    summary: str,
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    map_disposition: dict | None = None,
    idempotency_key: str | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: substantive work reached a terminal successful result. Report only observed paths and bounded check/delta metadata; never raw commands, output, or source. A reconciled Map disposition must include the checked scope and event_id returned by project_map_reconcile; otherwise use checked_no_change, not_applicable, deferred, or pending."""
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
    work_key: str,
    summary: str,
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    map_disposition: dict | None = None,
    idempotency_key: str | None = None,
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
    work_key: str,
    summary: str,
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    map_disposition: dict | None = None,
    idempotency_key: str | None = None,
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
    work_key: str,
    summary: str,
    reviewed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    checks: list[dict] | None = None,
    repository_delta: dict | None = None,
    map_disposition: dict | None = None,
    idempotency_key: str | None = None,
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
