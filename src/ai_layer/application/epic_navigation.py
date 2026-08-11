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
    plan_payload,
    project_for_root,
    task_row,
)
from ai_layer.application.epic_planning import retry_final_item
from ai_layer.application.epic_task_boundary import accepted_task_identity
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.tasks.views import task_to_dict


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


def _complete_final_item(db: Session, project: Project, epic: Epic, task: Task) -> dict:
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
        return {"state": "task_open", "task": task_to_dict(db, task, include_history=False)}
    if task.status != "completed":
        active.status = "blocked"
        epic.status = "blocked"
        epic.blocked_reason = f"Linked Task ended in unsupported status {task.status}"
        return {"state": "blocked"}
    active.status = "completed"
    active.completed_at = task.completed_at or utcnow()
    identity = accepted_task_identity(db, task)
    epic.execution_digest = identity["digest"]
    epic.execution_files = identity["file_count"]
    if active.kind == "final":
        return _complete_final_item(db, project, epic, task)
    append_epic_event(
        db,
        project,
        epic,
        "EpicPlanItemCompleted",
        {"plan_item": f"P-{int(active.ordinal):03d}", "task": f"T-{int(task.sequence):04d}"},
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


def _drift_task_navigation(db: Session, epic: Epic) -> dict:
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


def _phase0_navigation(db: Session, epic: Epic) -> dict:
    task = task_row(db, epic.phase0_task_id)
    if task and task.status in {"active", "blocked"}:
        return {
            "action": "continue_task",
            "tool": "task_next",
            "task": task_to_dict(db, task, include_history=False),
        }
    if task and task.status == "completed":
        return {
            "action": "record_phase0_reconciliation",
            "tool": "epic_reconcile_complete",
            "message": (
                "Apply non-branching/strong-recommendation corrections to the execution spec; "
                "human_decisions only for genuine material trade-offs."
            ),
        }
    return {"action": "human_attention_required", "message": "Phase 0 Task is missing or invalid"}


def _pending_navigation(db: Session, epic: Epic) -> dict:
    pending = db.scalar(
        select(EpicPlanItem)
        .where(EpicPlanItem.epic_id == epic.id, EpicPlanItem.status == "pending")
        .order_by(EpicPlanItem.ordinal.asc())
        .limit(1)
    )
    if pending is None:
        return {
            "action": "human_attention_required",
            "message": "Epic has no active/pending plan item but is not completed",
        }
    return {
        "action": "start_final_review" if pending.kind == "final" else "start_next_task",
        "tool": "epic_start_next",
        "plan_item": plan_payload(db, pending),
    }


def _running_navigation(db: Session, project: Project, epic: Epic) -> dict:
    sync = _sync_active_item(db, project, epic)
    db.flush()
    if sync and sync.get("state") == "task_open":
        return {"action": "continue_task", "tool": "task_next", "task": sync["task"]}
    if epic.status == "completed":
        return {"action": "archive", "tool": "epic_archive"}
    if epic.status == "blocked":
        return {"action": "human_attention_required", "message": epic.blocked_reason}
    drift = _drift_action(project, epic)
    if drift is None:
        return _pending_navigation(db, epic)
    epic.status = "blocked"
    epic.blocked_reason = (
        "repository_drift_detected: targeted reconciliation required before the next Epic Task"
    )
    append_epic_event(
        db,
        project,
        epic,
        "EpicDriftDetected",
        {"expected": drift["expected_digest"], "current": drift["current_digest"]},
    )
    return drift


def _human_decision_navigation(epic: Epic) -> dict:
    return {
        "action": "human_attention_required",
        "message": epic.blocked_reason,
        "resolution_tool": "epic_reconcile_complete",
        "decision_required": list(epic.decision_required or []),
    }


def _navigation_action(db: Session, project: Project, epic: Epic) -> dict:
    if epic.status == "draft":
        return {
            "action": "audit_revise_or_approve",
            "allowed_tools": ["epic_audit_record", "epic_spec_revise", "epic_approve"],
            "message": (
                "Spec is mutable. Run unlimited independent audit/revision rounds; approval freezes the human baseline."
            ),
        }
    if epic.status == "approved":
        return {"action": "start_phase0", "tool": "epic_start_next"}
    if epic.status == "phase0":
        return _phase0_navigation(db, epic)
    if epic.status == "planning":
        return {
            "action": "create_task_plan",
            "tool": "epic_plan_set",
            "message": (
                "Create implementation Tasks from the reconciled execution spec. Phase 0 and final closure/review are automatic."
            ),
        }
    if epic.status == "blocked" and epic.blocked_reason.startswith("human_decision_required"):
        return _human_decision_navigation(epic)
    if epic.drift_task_id:
        return _drift_task_navigation(db, epic)
    if epic.status in {"running", "final_review"}:
        return _running_navigation(db, project, epic)
    if epic.status == "blocked" and epic.blocked_reason.startswith("repository_drift_detected"):
        return {
            "action": "start_drift_reconciliation",
            "tool": "epic_start_next",
            "message": (
                "Run targeted analysis-only reconciliation. Resolve obvious drift automatically; ask the human only for material trade-offs."
            ),
        }
    if epic.status == "blocked":
        return {"action": "human_attention_required", "message": epic.blocked_reason}
    if epic.status == "completed":
        return {"action": "archive", "tool": "epic_archive"}
    return {"action": "none", "message": f"Epic status is {epic.status}"}


def next_action(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        action = _navigation_action(db, project, epic)
        db.flush()
        return {
            "epic": epic_payload(db, epic, include_spec=False, include_history=False),
            "next_action": action,
        }
