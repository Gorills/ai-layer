from __future__ import annotations

import shlex

from ai_layer.application.transport import application_scope as session_scope
from ai_layer.application.transport import cleanup_review_sandbox as db_cleanup_review_sandbox
from ai_layer.application.transport import prepare_review_sandbox as db_prepare_review_sandbox
from ai_layer.application.transport import run_review_check as db_run_review_check
from ai_layer.application.transport import run_verification as db_run_verification
from ai_layer.application.transport import task_adopt as db_adopt_task
from ai_layer.application.transport import task_cancel as db_cancel_task
from ai_layer.application.transport import task_complete_current as db_complete_current_stage
from ai_layer.application.transport import task_complete_legacy as db_complete_stage
from ai_layer.application.transport import task_create as db_create_task
from ai_layer.application.transport import task_current as db_current_task
from ai_layer.application.transport import task_delegate as db_delegate_current_stage
from ai_layer.application.transport import task_next as db_next_task_action
from ai_layer.application.transport import task_resume as db_resume_task
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import (
    _compact_open_transition,
    _list,
    _project,
    _scoped,
    _text,
    core_tool,
    project_root_for_tool,
)


def task_current(project_root: str | None = None) -> dict:
    """WHEN: project_status shows an active managed Task, or explicit managed Task state inspection is needed. INPUT: optional project_root. RETURNS the one open managed Task and exact next stage; if none is active, returns host-native idle guidance plus task_create as an optional managed-work choice. Does not mutate repository or task state."""
    root = project_root_for_tool(project_root, tool="task_current")
    with mcp_audit(
        root, "task_current", arg_keys=["project_root"] if project_root else []
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_current_task(db, project, include_history=False)
            audit["metrics"] = {
                "active": bool(result.get("active")),
                "state": result.get("state"),
                "task": ((result.get("task") or {}).get("key")),
            }
            return _scoped(result, root)


def task_next(project_root: str | None = None) -> dict:
    """PRIMARY MANAGED TASK NAVIGATOR. WHEN: project_status reports an active/selected managed Task, after each managed Task transition, after its worker returns, or after context loss inside that Task. RETURNS the exact managed next action and stage contract. If no managed Task is active, ordinary host-native work remains allowed and task_create is optional; do not create a Task merely to authorize edits."""
    root = project_root_for_tool(project_root, tool="task_next")
    with mcp_audit(root, "task_next", arg_keys=["project_root"] if project_root else []) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_next_task_action(db, project)
            next_action = (
                result.get("next_action") or ((result.get("task") or {}).get("next_action")) or {}
            )
            audit["metrics"] = {
                "active": bool(result.get("active")),
                "state": result.get("state"),
                "next_action": next_action.get("action"),
                "tool": next_action.get("tool"),
            }
            return _scoped(result, root)


def review_sandbox_prepare(project_root: str | None = None) -> dict:
    """WHEN: the active delegated reviewer needs to run checks that may write files. Creates/reuses a disposable copy of the current working tree outside the canonical repository. This is filesystem/workspace isolation for normal test artifacts, not a security sandbox against malicious commands."""
    root = project_root_for_tool(project_root, tool="review_sandbox_prepare")
    with mcp_audit(
        root, "review_sandbox_prepare", arg_keys=["project_root"] if project_root else []
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_prepare_review_sandbox(db, project)
            audit["metrics"] = {
                "stage_id": result.get("stage_id"),
                "reused": bool(result.get("reused")),
            }
            return _scoped(result, root)


def review_check_run(
    command: list[str] | str,
    cwd: str | None = None,
    timeout_seconds: int = 300,
    project_root: str | None = None,
) -> dict:
    """WHEN: an active read-only discovery/review worker needs an executable test/static check. INPUT: argv list (preferred; a string is parsed with shlex), optional relative cwd inside the disposable discovery/review workspace, timeout <=900s. AI Layer executes without shell=True, records exit/duration/output digest, and canonical project files remain under the read-only guard."""
    root = project_root_for_tool(project_root, tool="review_check_run")
    argv = shlex.split(command) if isinstance(command, str) else _list(command)
    if not argv:
        raise ValueError("review_check_run: `command` is required; pass argv as a list.")
    with mcp_audit(
        root,
        "review_check_run",
        arg_keys=["command", "cwd", "timeout_seconds", "project_root"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_run_review_check(
                db,
                project,
                command=argv,
                cwd=cwd,
                timeout_seconds=max(1, min(int(timeout_seconds), 900)),
            )
            audit["metrics"] = {
                "ok": bool(result.get("ok")),
                "exit_code": result.get("exit_code"),
                "duration_ms": result.get("duration_ms"),
                "evidence_id": result.get("evidence_id"),
            }
            return _scoped(result, root)


def verification_run(
    command: list[str] | str,
    cwd: str = ".",
    timeout_seconds: int = 300,
    project_root: str | None = None,
) -> dict:
    """Run AI-Layer-verified checks for the active delegated IMPLEMENT/FIX stage."""
    root = project_root_for_tool(project_root, tool="verification_run")
    argv = shlex.split(command) if isinstance(command, str) else _list(command)
    if not argv:
        raise ValueError("verification_run: `command` is required; pass argv as a list.")
    with mcp_audit(
        root, "verification_run", arg_keys=["command", "cwd", "timeout_seconds", "project_root"]
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_run_verification(
                db,
                project,
                command=argv,
                cwd=cwd,
                timeout_seconds=max(1, min(int(timeout_seconds), 900)),
            )
            audit["metrics"] = {
                "ok": bool(result.get("ok")),
                "assurance": result.get("assurance"),
                "exit_code": result.get("exit_code"),
                "verification_id": result.get("id"),
            }
            return _scoped(result, root)


def review_sandbox_cleanup(project_root: str | None = None) -> dict:
    """WHEN: the delegated reviewer is done with disposable verification files. Safe to omit on normal task_stage_complete because AI Layer also performs best-effort cleanup automatically."""
    root = project_root_for_tool(project_root, tool="review_sandbox_cleanup")
    with mcp_audit(
        root, "review_sandbox_cleanup", arg_keys=["project_root"] if project_root else []
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_cleanup_review_sandbox(db, project)
            audit["metrics"] = {"removed": bool(result.get("removed"))}
            return _scoped(result, root)


def task_create(
    goal: str,
    acceptance_criteria: list[str] | str | None = None,
    constraints: list[str] | str | None = None,
    workflow: str = "auto",
    risk: str = "auto",
    complexity: str = "auto",
    uncertainty: str = "auto",
    cost_policy: str = "auto",
    project_root: str | None = None,
) -> dict:
    """WHEN: no managed Task is active and the user/agent explicitly chooses durable or strict managed execution. This tool is NOT required before ordinary host-native edits. INPUT: goal plus compact acceptance_criteria/constraints; normally keep workflow/risk/complexity/uncertainty/cost_policy=auto. Dirty worktrees are valid: AI Layer captures the exact current repository state as the immutable Task baseline and preserves pre-existing changes separately from the later managed delta. AI Layer classifies MICRO/STANDARD/DISCOVERY_FIRST/ANALYSIS_ONLY and returns the live managed next action."""
    root = project_root_for_tool(project_root, tool="task_create")
    goal = _text(goal, tool="task_create", field="goal")
    criteria = _list(acceptance_criteria)
    task_constraints = _list(constraints)
    with mcp_audit(
        root,
        "task_create",
        arg_keys=[
            "goal",
            "acceptance_criteria",
            "constraints",
            "workflow",
            "risk",
            "complexity",
            "uncertainty",
            "cost_policy",
            "project_root",
        ],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_create_task(
                db,
                project,
                goal=goal,
                acceptance_criteria=criteria,
                constraints=task_constraints,
                workflow=workflow,
                risk=risk,
                complexity=complexity,
                uncertainty=uncertainty,
                cost_policy=cost_policy,
            )
            audit["metrics"] = {
                "task": result.get("key"),
                "stage": (result.get("active_stage") or {}).get("kind"),
                "acceptance_criteria": len(criteria),
                "workflow_profile": result.get("workflow_profile"),
                "risk_level": result.get("risk_level"),
                "complexity_level": result.get("complexity_level"),
                "uncertainty_level": result.get("uncertainty_level"),
                "cost_policy": result.get("cost_policy"),
                "preexisting_paths": (result.get("preexisting_changes") or {}).get("total", 0),
            }
            return _scoped(result, root)


def task_adopt(
    goal: str,
    acceptance_criteria: list[str] | str | None = None,
    constraints: list[str] | str | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: substantive repository edits already happened outside a managed Task and the user/agent now explicitly wants AI Layer managed review/remediation. INPUT: goal required; compact acceptance_criteria/constraints; project_root explicit or safely bound. Requires a dirty Git worktree, records those paths as unmanaged pre-task provenance, SKIPS IMPLEMENT, and starts at read-only REVIEW. Never use this to pretend prior edits were managed implementation."""
    root = project_root_for_tool(project_root, tool="task_adopt")
    goal = _text(goal, tool="task_adopt", field="goal")
    criteria = _list(acceptance_criteria)
    task_constraints = _list(constraints)
    with mcp_audit(
        root,
        "task_adopt",
        arg_keys=["goal", "acceptance_criteria", "constraints", "project_root"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_adopt_task(
                db,
                project,
                goal=goal,
                acceptance_criteria=criteria,
                constraints=task_constraints,
            )
            audit["metrics"] = {
                "task": result.get("key"),
                "stage": (result.get("active_stage") or {}).get("kind"),
                "adopted_paths": (result.get("adopted_changes") or {}).get("total", 0),
            }
            return _scoped(result, root)


def task_stage_delegate(
    worker_id: str,
    project_root: str | None = None,
    actual_model: str | None = None,
    model_assurance: str = "requested_unverified",
) -> dict:
    """WHEN: task_next says delegate_stage. INPUT: one fresh worker_id label only. AI Layer binds that worker BEFORE repository mutation and refuses delegation if undelegated repository changes already appeared. RETURNS the compact worker contract, requested cost/model tier/profile, and exact stage-specific completion contract. Use the requested host profile when available instead of inheriting the parent model blindly."""
    root = project_root_for_tool(project_root, tool="task_stage_delegate")
    worker_id = _text(worker_id, tool="task_stage_delegate", field="worker_id")
    with mcp_audit(
        root,
        "task_stage_delegate",
        arg_keys=["worker_id", "actual_model", "model_assurance", "project_root"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_delegate_current_stage(
                db,
                project,
                worker_id=worker_id,
                actual_model=actual_model,
                model_assurance=model_assurance,
            )
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "stage": (result.get("active_stage") or {}).get("kind"),
                "worker_id": (result.get("active_stage") or {}).get("worker_id"),
                "idempotent": bool(result.get("delegation_idempotent")),
            }
            return _scoped(result, root)


def task_discovery_complete(
    summary: str,
    checks: list[str] | str | None = None,
    outcome: str = "ready_for_implementation",
    verified_facts: list[str] | str | None = None,
    risks: list[str] | str | None = None,
    proposed_plan: list[str] | str | None = None,
    proposed_acceptance_criteria: list[str] | str | None = None,
    external_actions: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: task_next says record_stage_result for DISCOVERY. Read-only discovery records verified facts/risks/plan without review findings or fixer semantics. discovery_first normally returns ready_for_implementation; analysis_only returns analysis_complete/no_change_needed."""
    root = project_root_for_tool(project_root, tool="task_discovery_complete")
    summary = _text(summary, tool="task_discovery_complete", field="summary")
    check_items = _list(checks)
    result_data = {
        "verified_facts": _list(verified_facts),
        "risks": _list(risks),
        "proposed_plan": _list(proposed_plan),
        "proposed_acceptance_criteria": _list(proposed_acceptance_criteria),
    }
    with mcp_audit(
        root,
        "task_discovery_complete",
        arg_keys=[
            "summary",
            "checks",
            "outcome",
            "verified_facts",
            "risks",
            "proposed_plan",
            "proposed_acceptance_criteria",
            "external_actions",
            "project_root",
        ],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_complete_current_stage(
                db,
                project,
                expected_kind="discovery",
                summary=summary,
                checks=check_items,
                outcome=outcome,
                external_actions=external_actions,
                result_data=result_data,
            )
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "status": result.get("status"),
                "next_stage": (result.get("active_stage") or {}).get("kind"),
                "workflow_profile": result.get("workflow_profile"),
            }
            return _scoped(result, root)


def task_implementation_complete(
    summary: str,
    checks: list[str] | str | None = None,
    outcome: str = "done",
    external_actions: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: task_next says record_stage_result for IMPLEMENT. INPUT: compact summary, at least one check, optional outcome=done|blocked, optional declared external_actions. Stage id and worker id are read from durable state; do not pass or guess them."""
    root = project_root_for_tool(project_root, tool="task_implementation_complete")
    summary = _text(summary, tool="task_implementation_complete", field="summary")
    check_items = _list(checks)
    with mcp_audit(
        root,
        "task_implementation_complete",
        arg_keys=["summary", "checks", "outcome", "external_actions", "project_root"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_complete_current_stage(
                db,
                project,
                expected_kind="implement",
                summary=summary,
                checks=check_items,
                outcome=outcome,
                external_actions=external_actions,
            )
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "status": result.get("status"),
                "next_stage": (result.get("active_stage") or {}).get("kind"),
                "handoff_written": bool(result.get("handoff_session_id")),
            }
            return _scoped(result, root)


def task_review_complete(
    summary: str,
    checks: list[str] | str | None = None,
    verdict: str = "pass",
    findings: list[dict] | None = None,
    verification_results: list[dict] | None = None,
    external_actions: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: task_next says record_stage_result for REVIEW. INPUT: summary, checks, verdict=pass|changes_required; findings only for actionable defects; one verification_results item per pending finding id when task_next requires it. Review external_actions may be verification-only; external mutations are rejected."""
    root = project_root_for_tool(project_root, tool="task_review_complete")
    summary = _text(summary, tool="task_review_complete", field="summary")
    check_items = _list(checks)
    with mcp_audit(
        root,
        "task_review_complete",
        arg_keys=[
            "summary",
            "checks",
            "verdict",
            "findings",
            "verification_results",
            "external_actions",
            "project_root",
        ],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_complete_current_stage(
                db,
                project,
                expected_kind="review",
                summary=summary,
                checks=check_items,
                verdict=verdict,
                findings=findings,
                verification_results=verification_results,
                external_actions=external_actions,
            )
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "status": result.get("status"),
                "next_stage": (result.get("active_stage") or {}).get("kind"),
                "open_findings": result.get("open_findings"),
                "handoff_written": bool(result.get("handoff_session_id")),
            }
            return _scoped(result, root)


def task_fix_complete(
    summary: str,
    checks: list[str] | str | None = None,
    outcome: str = "done",
    external_actions: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """WHEN: task_next says record_stage_result for FIX. INPUT: summary, checks, optional outcome=done|no_changes_needed|blocked and declared external_actions. Stage id/worker id are inferred from durable state."""
    root = project_root_for_tool(project_root, tool="task_fix_complete")
    summary = _text(summary, tool="task_fix_complete", field="summary")
    check_items = _list(checks)
    with mcp_audit(
        root,
        "task_fix_complete",
        arg_keys=["summary", "checks", "outcome", "external_actions", "project_root"],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_complete_current_stage(
                db,
                project,
                expected_kind="fix",
                summary=summary,
                checks=check_items,
                outcome=outcome,
                external_actions=external_actions,
            )
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "status": result.get("status"),
                "next_stage": (result.get("active_stage") or {}).get("kind"),
                "handoff_written": bool(result.get("handoff_session_id")),
            }
            return _scoped(result, root)


def task_stage_complete(
    stage_id: str,
    worker_id: str,
    summary: str,
    checks: list[str] | str | None = None,
    outcome: str = "done",
    verdict: str | None = None,
    findings: list[dict] | None = None,
    verification_results: list[dict] | None = None,
    external_actions: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """LEGACY/DIAGNOSTIC completion API. New workflow should use task_next + task_stage_delegate + the returned stage-specific completion tool. New stages still require explicit delegation before this generic API can complete them."""
    root = project_root_for_tool(project_root, tool="task_stage_complete")
    stage_id = _text(stage_id, tool="task_stage_complete", field="stage_id")
    worker_id = _text(worker_id, tool="task_stage_complete", field="worker_id")
    summary = _text(summary, tool="task_stage_complete", field="summary")
    check_items = _list(checks)
    with mcp_audit(
        root,
        "task_stage_complete",
        arg_keys=[
            "stage_id",
            "worker_id",
            "summary",
            "checks",
            "outcome",
            "verdict",
            "findings",
            "verification_results",
            "external_actions",
            "project_root",
        ],
    ) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_complete_stage(
                db,
                project,
                stage_id=stage_id,
                worker_id=worker_id,
                summary=summary,
                checks=check_items,
                outcome=outcome,
                verdict=verdict,
                findings=findings,
                verification_results=verification_results,
                external_actions=external_actions,
            )
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "status": result.get("status"),
                "next_stage": (result.get("active_stage") or {}).get("kind"),
                "open_findings": result.get("open_findings"),
                "handoff_written": bool(result.get("handoff_session_id")),
                "normalization_count": len(result.get("input_normalizations") or []),
                "normalizations": result.get("input_normalizations") or [],
                "effective_verdict": result.get("effective_review_verdict"),
            }
            return _scoped(result, root)


def task_resume(project_root: str | None = None) -> dict:
    """WHEN: the sole task is BLOCKED and the external blocker has actually been resolved. For a reviewer-write violation the repository must first be restored exactly to the review-stage start state. Creates a fresh replacement stage; never resumes in parallel."""
    root = project_root_for_tool(project_root, tool="task_resume")
    with mcp_audit(root, "task_resume", arg_keys=["project_root"] if project_root else []) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_resume_task(db, project)
            result = _compact_open_transition(db, project, result)
            audit["metrics"] = {
                "task": result.get("key"),
                "stage": (result.get("active_stage") or {}).get("kind"),
            }
            return _scoped(result, root)


def task_cancel(reason: str, project_root: str | None = None) -> dict:
    """WHEN: the user/orchestrator explicitly abandons the current active or blocked task. INPUT: reason required. This is not a shortcut around review or blockers."""
    root = project_root_for_tool(project_root, tool="task_cancel")
    reason = _text(reason, tool="task_cancel", field="reason")
    with mcp_audit(root, "task_cancel", arg_keys=["reason", "project_root"]) as audit:
        with session_scope() as db:
            project = _project(db, root)
            result = db_cancel_task(db, project, reason=reason)
            audit["metrics"] = {"task": result.get("key"), "status": result.get("status")}
            return _scoped(result, root)


# MCP schema/handler registration remains local to this capability adapter.
task_current = core_tool()(task_current)
task_next = core_tool()(task_next)
review_sandbox_prepare = core_tool()(review_sandbox_prepare)
review_check_run = core_tool()(review_check_run)
verification_run = core_tool()(verification_run)
review_sandbox_cleanup = core_tool()(review_sandbox_cleanup)
task_create = core_tool()(task_create)
task_adopt = core_tool()(task_adopt)
task_stage_delegate = core_tool()(task_stage_delegate)
task_discovery_complete = core_tool()(task_discovery_complete)
task_implementation_complete = core_tool()(task_implementation_complete)
task_review_complete = core_tool()(task_review_complete)
task_fix_complete = core_tool()(task_fix_complete)
task_stage_complete = core_tool()(task_stage_complete)
task_resume = core_tool()(task_resume)
task_cancel = core_tool()(task_cancel)
