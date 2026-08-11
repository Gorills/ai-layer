from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import (
    DOC_PATH_NAMES,
    append_epic_event,
    capture_identity,
    epic_for_update,
    epic_payload,
    lock_project,
    plan_payload,
    project_for_root,
    task_row,
    task_uuid,
)
from ai_layer.application.epic_planning import retry_final_item
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import (
    EPIC_EXECUTION_STATUSES,
    epic_key,
    phase0_contract,
    plan_item_key,
)
from ai_layer.tasks.lifecycle import create_task
from ai_layer.tasks.views import task_to_dict


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


def _final_closure_evidence(db: Session, task: Task) -> dict:
    changes = dict(task.final_changes or {})
    paths = {
        str(path) for group in ("added", "modified", "deleted") for path in changes.get(group) or []
    }
    docs_updated = any(path in DOC_PATH_NAMES or path.startswith("docs/") for path in paths)
    event = db.scalar(
        select(RuntimeEvent)
        .where(
            RuntimeEvent.event_type == "KnowledgePublished",
            RuntimeEvent.aggregate_type == "task",
            RuntimeEvent.aggregate_id == str(task.id),
        )
        .order_by(RuntimeEvent.created_at.desc())
        .limit(1)
    )
    published = int((event.payload or {}).get("published") or 0) if event else 0
    return {
        "docs_updated": docs_updated,
        "knowledge_published": published,
        "changed_paths": sorted(paths),
    }


def _sync_active_item(db: Session, project: Project, epic: Epic) -> dict | None:
    active = db.scalar(
        select(EpicPlanItem)
        .where(EpicPlanItem.epic_id == epic.id, EpicPlanItem.status == "active")
        .order_by(EpicPlanItem.ordinal.asc())
        .limit(1)
        .with_for_update()
    )
    if active is None:
        return None
    task = task_row(db, active.task_id)
    if task is None:
        active.status = "blocked"
        epic.status = "blocked"
        epic.blocked_reason = "Linked Epic Task record is missing"
        return {"state": "blocked"}
    if task.status in {"active", "blocked"}:
        return {
            "state": "task_open",
            "task": task_to_dict(db, task, include_history=False),
        }
    if task.status != "completed":
        active.status = "blocked"
        epic.status = "blocked"
        epic.blocked_reason = f"Linked Task ended in unsupported status {task.status}"
        return {"state": "blocked"}
    active.status = "completed"
    active.completed_at = task.completed_at or utcnow()
    identity = capture_identity(project.root_path)
    epic.execution_digest = identity["digest"]
    epic.execution_files = identity["file_count"]
    if active.kind == "final":
        evidence = _final_closure_evidence(db, task)
        if evidence["docs_updated"] and evidence["knowledge_published"] > 0:
            epic.status = "completed"
            epic.completed_at = utcnow()
            epic.blocked_reason = ""
            append_epic_event(
                db,
                project,
                epic,
                "EpicCompleted",
                {"final_task": f"T-{int(task.sequence):04d}", **evidence},
            )
            return {"state": "completed", "closure": evidence}
        retry_final_item(db, epic, evidence)
        epic.status = "final_review"
        epic.blocked_reason = ""
        append_epic_event(db, project, epic, "EpicFinalReviewRetryRequired", evidence)
        return {"state": "final_retry", "closure": evidence}
    append_epic_event(
        db,
        project,
        epic,
        "EpicPlanItemCompleted",
        {"plan_item": plan_item_key(active.ordinal), "task": f"T-{int(task.sequence):04d}"},
    )
    return {"state": "task_completed"}


def _drift_action(project: Project, epic: Epic) -> dict | None:
    if not epic.execution_digest:
        return None
    identity = capture_identity(project.root_path)
    if identity["digest"] == epic.execution_digest:
        return None
    return {
        "action": "start_drift_reconciliation",
        "tool": "epic_start_next",
        "message": (
            "Repository changed outside the last accepted Epic Task boundary. Run targeted read-only "
            "reconciliation before starting the next planned Task."
        ),
        "expected_digest": epic.execution_digest,
        "current_digest": identity["digest"],
    }


def _drift_task_navigation(db: Session, epic: Epic) -> dict | None:
    if not epic.drift_task_id:
        return None
    task = task_row(db, epic.drift_task_id)
    if task is None:
        epic.status = "blocked"
        epic.blocked_reason = "Drift reconciliation Task record is missing"
        return {"action": "human_attention_required", "message": epic.blocked_reason}
    if task.status in {"active", "blocked"}:
        return {
            "action": "continue_task",
            "tool": "task_next",
            "task": task_to_dict(db, task, include_history=False),
        }
    if task.status == "completed":
        return {
            "action": "record_drift_reconciliation",
            "tool": "epic_reconcile_complete",
            "message": (
                "Update only affected execution-spec/remaining-plan assumptions. Apply obvious or clearly "
                "superior durable corrections automatically; human_decisions is only for genuine trade-offs."
            ),
        }
    epic.status = "blocked"
    epic.blocked_reason = f"Drift reconciliation Task ended in unsupported status {task.status}"
    return {"action": "human_attention_required", "message": epic.blocked_reason}


def next_action(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        action: dict[str, object]
        if epic.status == "draft":
            action = {
                "action": "audit_revise_or_approve",
                "allowed_tools": ["epic_audit_record", "epic_spec_revise", "epic_approve"],
                "message": (
                    "Spec is mutable. Run unlimited independent audit/revision rounds; approval freezes the human baseline."
                ),
            }
        elif epic.status == "approved":
            action = {"action": "start_phase0", "tool": "epic_start_next"}
        elif epic.status == "phase0":
            task = task_row(db, epic.phase0_task_id)
            if task and task.status in {"active", "blocked"}:
                action = {
                    "action": "continue_task",
                    "tool": "task_next",
                    "task": task_to_dict(db, task, include_history=False),
                }
            elif task and task.status == "completed":
                action = {
                    "action": "record_phase0_reconciliation",
                    "tool": "epic_reconcile_complete",
                    "message": (
                        "Apply non-branching/strong-recommendation corrections to the execution spec; "
                        "human_decisions only for genuine material trade-offs."
                    ),
                }
            else:
                action = {
                    "action": "human_attention_required",
                    "message": "Phase 0 Task is missing or invalid",
                }
        elif epic.status == "planning":
            action = {
                "action": "create_task_plan",
                "tool": "epic_plan_set",
                "message": (
                    "Create implementation Tasks from the reconciled execution spec. Phase 0 and final closure/review are automatic."
                ),
            }
        elif epic.drift_task_id:
            action = _drift_task_navigation(db, epic) or {"action": "none"}
        elif epic.status in {"running", "final_review"}:
            sync = _sync_active_item(db, project, epic)
            db.flush()
            if sync and sync.get("state") == "task_open":
                action = {
                    "action": "continue_task",
                    "tool": "task_next",
                    "task": sync["task"],
                }
            elif epic.status == "completed":
                action = {"action": "archive", "tool": "epic_archive"}
            elif epic.status == "blocked":
                action = {"action": "human_attention_required", "message": epic.blocked_reason}
            else:
                drift = _drift_action(project, epic)
                if drift is not None:
                    epic.status = "blocked"
                    epic.blocked_reason = (
                        "repository_drift_detected: targeted reconciliation required before the next Epic Task"
                    )
                    append_epic_event(
                        db,
                        project,
                        epic,
                        "EpicDriftDetected",
                        {
                            "expected": drift["expected_digest"],
                            "current": drift["current_digest"],
                        },
                    )
                    action = drift
                else:
                    pending = db.scalar(
                        select(EpicPlanItem)
                        .where(
                            EpicPlanItem.epic_id == epic.id,
                            EpicPlanItem.status == "pending",
                        )
                        .order_by(EpicPlanItem.ordinal.asc())
                        .limit(1)
                    )
                    if pending is None:
                        action = {
                            "action": "human_attention_required",
                            "message": "Epic has no active/pending plan item but is not completed",
                        }
                    else:
                        action = {
                            "action": (
                                "start_final_review"
                                if pending.kind == "final"
                                else "start_next_task"
                            ),
                            "tool": "epic_start_next",
                            "plan_item": plan_payload(db, pending),
                        }
        elif epic.status == "blocked" and epic.blocked_reason.startswith(
            "repository_drift_detected"
        ):
            action = {
                "action": "start_drift_reconciliation",
                "tool": "epic_start_next",
                "message": (
                    "Run targeted analysis-only reconciliation. Resolve obvious drift automatically; ask the human only for material trade-offs."
                ),
            }
        elif epic.status == "blocked":
            action = {"action": "human_attention_required", "message": epic.blocked_reason}
        elif epic.status == "completed":
            action = {"action": "archive", "tool": "epic_archive"}
        else:
            action = {"action": "none", "message": f"Epic status is {epic.status}"}
        db.flush()
        return {
            "epic": epic_payload(db, epic, include_spec=False, include_history=False),
            "next_action": action,
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
