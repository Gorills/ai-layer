from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import (
    append_epic_event,
    capture_identity,
    epic_for_update,
    epic_payload,
    lock_project,
    project_for_root,
    task_uuid,
)
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import (
    EPIC_EXECUTION_STATUSES,
    epic_key,
    phase0_contract,
    plan_item_key,
)
from ai_layer.tasks.lifecycle import create_task


def _assert_no_other_execution_epic(db: Session, project: Project, epic: Epic) -> None:
    other = db.scalar(
        select(Epic)
        .where(
            Epic.project_id == project.id,
            Epic.id != epic.id,
            Epic.status.in_(sorted(EPIC_EXECUTION_STATUSES)),
        )
        .limit(1)
    )
    if other is not None:
        raise RuntimeError(
            f"Another Epic {epic_key(other.sequence)} is already in execution state {other.status}"
        )


def _assert_no_open_task(db: Session, project: Project) -> None:
    open_task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status.in_(["active", "blocked"]))
        .limit(1)
    )
    if open_task is not None:
        raise RuntimeError(
            f"Project already has open Task T-{int(open_task.sequence):04d}; continue it before Epic scheduling"
        )


def _assert_current_execution_boundary(project: Project, epic: Epic) -> None:
    if not epic.execution_digest:
        return
    identity = capture_identity(project.root_path)
    if identity["digest"] != epic.execution_digest:
        raise RuntimeError(
            "Repository changed since the last accepted Epic boundary. Call epic_next before "
            "starting another Epic Task so accepted standalone Tasks can be reviewed or unknown "
            "drift can be reconciled."
        )


def _phase0_goal(epic: Epic) -> tuple[str, list[str], list[str]]:
    key = epic_key(epic.sequence)
    contract = phase0_contract({"key": key, "approved_spec_version": epic.approved_spec_version})
    goal = (
        f"Epic {key} Phase 0. Reconcile approved spec v{epic.approved_spec_version} against the current "
        "repository before any implementation Task is created. Call epic_get for the full spec."
    )
    criteria = list(contract["mandatory_checks"])
    constraints = [
        "Analysis-only: do not mutate repository files or external systems.",
        "Return verified facts, risks and a proposed decomposition through the normal DISCOVERY completion contract.",
        "After this Task completes, call epic_reconcile_complete; do not create implementation Tasks directly.",
    ]
    return goal, criteria, constraints


def start_next(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        lock_project(db, project)
        epic = epic_for_update(db, project, key)
        _assert_no_open_task(db, project)
        if epic.status == "approved":
            _assert_no_other_execution_epic(db, project, epic)
            goal, criteria, constraints = _phase0_goal(epic)
            result = create_task(
                db,
                project,
                goal=goal,
                acceptance_criteria=criteria,
                constraints=constraints,
                workflow="analysis_only",
            )
            epic.phase0_task_id = task_uuid(result["id"])
            epic.status = "phase0"
            epic.updated_at = utcnow()
            append_epic_event(
                db,
                project,
                epic,
                "EpicPhase0Started",
                {"task": result["key"]},
            )
            db.flush()
            return {
                "epic": epic_payload(db, epic, include_spec=False, include_history=False),
                "task": result,
            }
        if epic.status not in {"running", "final_review"}:
            raise RuntimeError(f"epic_start_next is not valid while Epic status is {epic.status}")
        _assert_current_execution_boundary(project, epic)
        if epic.drift_task_id:
            raise RuntimeError("A drift reconciliation Task already exists; follow epic_next")
        pending = db.scalar(
            select(EpicPlanItem)
            .where(EpicPlanItem.epic_id == epic.id, EpicPlanItem.status == "pending")
            .order_by(EpicPlanItem.ordinal.asc())
            .limit(1)
            .with_for_update()
        )
        if pending is None:
            raise RuntimeError("Epic has no pending plan item to start")
        result = create_task(
            db,
            project,
            goal=pending.goal,
            acceptance_criteria=list(pending.acceptance_criteria or []),
            constraints=list(pending.constraints or []),
            workflow="standard",
        )
        pending.task_id = task_uuid(result["id"])
        pending.status = "active"
        epic.status = "final_review" if pending.kind == "final" else "running"
        epic.updated_at = utcnow()
        append_epic_event(
            db,
            project,
            epic,
            "EpicPlanItemStarted",
            {
                "plan_item": plan_item_key(pending.ordinal),
                "kind": pending.kind,
                "task": result["key"],
            },
        )
        db.flush()
        return {
            "epic": epic_payload(db, epic, include_spec=False, include_history=False),
            "task": result,
        }


def start_drift_reconciliation(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        lock_project(db, project)
        epic = epic_for_update(db, project, key)
        if epic.status != "blocked" or not epic.blocked_reason.startswith(
            "repository_drift_detected"
        ):
            raise RuntimeError("Epic is not waiting for repository drift reconciliation")
        _assert_no_open_task(db, project)
        goal = (
            f"Targeted drift reconciliation for {epic_key(epic.sequence)} execution spec "
            f"v{epic.execution_spec_version}. Compare repository changes since the last accepted Epic Task "
            "boundary with remaining spec assumptions."
        )
        criteria = [
            "Identify which remaining Epic requirements/assumptions are affected by external repository drift.",
            "For obvious or strongly recommended durable corrections, propose updated execution spec/remaining plan without human interruption.",
            "Escalate only genuine material trade-offs through human_decisions.",
            "Do not mutate the repository during reconciliation.",
        ]
        result = create_task(
            db,
            project,
            goal=goal,
            acceptance_criteria=criteria,
            constraints=["analysis-only", "After completion call epic_reconcile_complete"],
            workflow="analysis_only",
        )
        epic.drift_task_id = task_uuid(result["id"])
        epic.status = "running"
        epic.blocked_reason = ""
        append_epic_event(
            db,
            project,
            epic,
            "EpicDriftReconciliationStarted",
            {"task": result["key"]},
        )
        db.flush()
        return {
            "epic": epic_payload(db, epic, include_spec=False, include_history=False),
            "task": result,
        }
