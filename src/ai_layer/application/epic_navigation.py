from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import (
    DOC_PATH_NAMES,
    append_epic_event,
    capture_identity,
    epic_audit_state,
    epic_for_update,
    epic_payload,
    plan_payload,
    project_for_root,
    task_row,
)
from ai_layer.application.epic_planning import retry_final_item
from ai_layer.application.epic_review import (
    INTERVENING_REVIEW_BLOCK_PREFIX,
    detect_intervening_tasks,
)
from ai_layer.application.epic_task_boundary import accepted_task_identity
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.domain.project_map import project_map_capability_contract
from ai_layer.tasks.constants import OPEN_TASK_STATUSES
from ai_layer.tasks.views import task_to_dict


def _latest_task_event(db: Session, task: Task, event_type: str) -> RuntimeEvent | None:
    return db.scalar(
        select(RuntimeEvent)
        .where(
            RuntimeEvent.event_type == event_type,
            RuntimeEvent.aggregate_type == "task",
            RuntimeEvent.aggregate_id == str(task.id),
        )
        .order_by(RuntimeEvent.created_at.desc())
        .limit(1)
    )


def _final_closure_evidence(db: Session, task: Task) -> dict:
    changes = dict(task.final_changes or {})
    paths = {
        str(path) for group in ("added", "modified", "deleted") for path in changes.get(group) or []
    }
    docs_updated = any(path in DOC_PATH_NAMES or path.startswith("docs/") for path in paths)
    knowledge_event = _latest_task_event(db, task, "KnowledgePublished")
    published = int((knowledge_event.payload or {}).get("published") or 0) if knowledge_event else 0
    map_event = _latest_task_event(db, task, "ProjectMapReconciled")
    map_payload = dict(map_event.payload or {}) if map_event else {}
    map_scope_paths = list(map_payload.get("scope_paths") or [])[:120]
    return {
        "docs_updated": docs_updated,
        "knowledge_published": published,
        "project_map_reconciled": map_event is not None and bool(map_scope_paths),
        "project_map_updated": int(map_payload.get("updated") or 0),
        "project_map_removed": int(map_payload.get("removed") or 0),
        "project_map_scope_paths": map_scope_paths,
        "project_map_no_changes_reason": str(map_payload.get("no_changes_reason") or "")[:500],
        "changed_paths": sorted(paths),
    }


def _project_map_reconciliation_action(task: Task, evidence: dict) -> dict:
    source_task_key = f"T-{int(task.sequence):04d}"
    return {
        "action": "reconcile_project_map",
        "tool": "project_map_reconcile",
        "source_task_key": source_task_key,
        "required": ["scope_paths", "source_task_key"],
        "task_changed_paths": list(evidence.get("changed_paths") or [])[:120],
        "message": (
            "The final Task is already completed and its documentation/Project Knowledge evidence is sufficient. "
            "Only Project Map reconciliation is missing; do NOT create another implementation/review Task. "
            "Project Map is AI Layer's reusable navigation index. Inspect the relevant current-source scope "
            "and existing breadcrumbs as needed, then call project_map_reconcile with this completed Task key "
            "and non-empty checked scope_paths. Add only semantic entries actually established from source; "
            "if existing map semantics are already accurate, use no_changes_reason. Then call epic_next again."
        ),
        "project_map": project_map_capability_contract(source_task_key=source_task_key),
    }


def _complete_final_item(db: Session, project: Project, epic: Epic, task: Task) -> dict:
    evidence = _final_closure_evidence(db, task)
    docs_ready = bool(evidence["docs_updated"])
    knowledge_ready = evidence["knowledge_published"] > 0
    map_ready = bool(evidence["project_map_reconciled"])
    if docs_ready and knowledge_ready and map_ready:
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
    if docs_ready and knowledge_ready and not map_ready:
        epic.status = "final_review"
        epic.blocked_reason = ""
        return {
            "state": "awaiting_project_map",
            "closure": evidence,
            "next_action": _project_map_reconciliation_action(task, evidence),
        }
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
    identity = accepted_task_identity(db, task)
    epic.execution_digest = identity["digest"]
    epic.execution_files = identity["file_count"]
    if active.kind == "final":
        result = _complete_final_item(db, project, epic, task)
        if result.get("state") == "awaiting_project_map":
            active.status = "active"
            active.completed_at = None
            return result
        active.status = "completed"
        active.completed_at = task.completed_at or utcnow()
        return result
    active.status = "completed"
    active.completed_at = task.completed_at or utcnow()
    append_epic_event(
        db,
        project,
        epic,
        "EpicPlanItemCompleted",
        {"plan_item": f"P-{int(active.ordinal):03d}", "task": f"T-{int(task.sequence):04d}"},
    )
    return {"state": "task_completed"}


def _linked_task_ids(db: Session, epic: Epic) -> set:
    ids = {task_id for task_id in (epic.phase0_task_id, epic.drift_task_id) if task_id}
    ids.update(
        task_id
        for task_id in db.scalars(
            select(EpicPlanItem.task_id).where(
                EpicPlanItem.epic_id == epic.id,
                EpicPlanItem.task_id.is_not(None),
            )
        ).all()
        if task_id
    )
    return ids


def _standalone_open_task(db: Session, project: Project, epic: Epic) -> Task | None:
    linked = _linked_task_ids(db, epic)
    task = db.scalar(
        select(Task)
        .where(
            Task.project_id == project.id,
            Task.status.in_(sorted(OPEN_TASK_STATUSES)),
        )
        .order_by(Task.sequence.asc())
        .limit(1)
    )
    if task is None or task.id in linked:
        return None
    return task


def _continue_standalone_task(db: Session, task: Task) -> dict:
    return {
        "action": "continue_standalone_task",
        "tool": "task_next",
        "task": task_to_dict(db, task, include_history=False),
        "message": (
            "This Task is intentionally outside the Epic. The Epic remains paused; finish or cancel "
            "the standalone Task, then call epic_next to resume the Epic."
        ),
    }


def _drift_action(db: Session, project: Project, epic: Epic) -> dict | None:
    if not epic.execution_digest:
        return None
    identity = capture_identity(project.root_path)
    if identity["digest"] == epic.execution_digest:
        return None
    intervening = detect_intervening_tasks(
        db,
        project,
        epic,
        current_identity=identity,
    )
    if intervening is not None:
        return {
            "action": "review_intervening_tasks",
            "tool": "epic_intervening_review_prepare",
            "message": (
                "Repository changes are fully attributable to accepted standalone Tasks executed between "
                "Epic Tasks. Run a read-only impact review instead of treating them as unknown drift."
            ),
            "intervening_tasks": intervening["task_keys"],
            "expected_digest": intervening["expected_digest"],
            "current_digest": intervening["current_digest"],
        }
    return {
        "action": "start_drift_reconciliation",
        "tool": "epic_start_next",
        "message": (
            "Repository changed outside a safely attributable accepted Task boundary. Run targeted "
            "read-only reconciliation before starting the next planned Epic Task."
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
    if sync and sync.get("state") == "awaiting_project_map":
        return dict(sync["next_action"])
    if epic.status == "completed":
        return {"action": "archive", "tool": "epic_archive"}
    if epic.status == "blocked":
        return {"action": "human_attention_required", "message": epic.blocked_reason}

    standalone = _standalone_open_task(db, project, epic)
    if standalone is not None:
        return _continue_standalone_task(db, standalone)

    drift = _drift_action(db, project, epic)
    if drift is None:
        return _pending_navigation(db, epic)
    if drift["action"] == "review_intervening_tasks":
        epic.status = "blocked"
        epic.blocked_reason = (
            f"{INTERVENING_REVIEW_BLOCK_PREFIX}: accepted standalone Tasks must be checked against "
            "remaining Epic assumptions"
        )
        append_epic_event(
            db,
            project,
            epic,
            "EpicInterveningTasksDetected",
            {
                "tasks": drift["intervening_tasks"],
                "expected": drift["expected_digest"],
                "current": drift["current_digest"],
            },
        )
        return drift

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


def _draft_navigation(db: Session, epic: Epic) -> dict:
    audit_state = epic_audit_state(db, epic)
    if audit_state["status"] == "stale_after_revision":
        message = (
            f"Spec v{epic.current_spec_version} is mutable. Audits of older versions remain historical; "
            "a fresh independent audit of the current spec is recommended before relying on them."
        )
    else:
        message = (
            "Spec is mutable and passive: ordinary project Tasks may continue independently. "
            "Run unlimited independent audit/edit rounds; approval freezes only the human baseline."
        )
    return {
        "action": "audit_revise_or_approve",
        "allowed_tools": [
            "epic_audit_prepare",
            "epic_audit_record",
            "epic_spec_edit",
            "epic_spec_revise",
            "epic_spec_get",
            "epic_approve",
        ],
        "audit_state": audit_state,
        "message": message,
    }


def _approved_navigation(db: Session, project: Project, epic: Epic) -> dict:
    standalone = _standalone_open_task(db, project, epic)
    if standalone is not None:
        return _continue_standalone_task(db, standalone)
    return {
        "action": "start_phase0_when_ready",
        "tool": "epic_start_next",
        "optional_tools": [
            "epic_audit_prepare",
            "epic_audit_record",
            "epic_spec_edit",
            "epic_spec_revise",
            "epic_spec_get",
        ],
        "audit_state": epic_audit_state(db, epic),
        "message": (
            "The approved Epic is still passive until Phase 0 starts. Ordinary Tasks may run first; "
            "call epic_start_next only when you intentionally begin Epic execution."
        ),
    }


def _navigation_action(db: Session, project: Project, epic: Epic) -> dict:
    if epic.status == "draft":
        return _draft_navigation(db, epic)
    if epic.status == "approved":
        return _approved_navigation(db, project, epic)
    if epic.status == "phase0":
        return _phase0_navigation(db, epic)
    if epic.status == "planning":
        return {
            "action": "create_task_plan",
            "tool": "epic_plan_set",
            "message": (
                "Create implementation Tasks from the reconciled execution spec. Phase 0 and final "
                "closure/review are automatic."
            ),
        }
    if epic.status == "blocked" and epic.blocked_reason.startswith("human_decision_required"):
        return _human_decision_navigation(epic)
    if epic.status == "blocked" and epic.blocked_reason.startswith(INTERVENING_REVIEW_BLOCK_PREFIX):
        return {
            "action": "review_intervening_tasks",
            "tool": "epic_intervening_review_prepare",
            "message": (
                "Accepted standalone Tasks occurred since the last Epic boundary. Review only their impact "
                "on remaining Epic assumptions; do not start a full drift reconciliation unless required."
            ),
        }
    if epic.drift_task_id:
        return _drift_task_navigation(db, epic)
    if epic.status in {"running", "final_review"}:
        return _running_navigation(db, project, epic)
    if epic.status == "blocked" and epic.blocked_reason.startswith("repository_drift_detected"):
        return {
            "action": "start_drift_reconciliation",
            "tool": "epic_start_next",
            "message": (
                "Run targeted analysis-only reconciliation. Resolve obvious drift automatically; "
                "ask the human only for material trade-offs."
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
        source_task_key = (
            str(action.get("source_task_key") or "")
            if action.get("tool") == "project_map_reconcile"
            else None
        )
        return {
            "epic": epic_payload(db, epic, include_spec=False, include_history=False),
            "next_action": action,
            "project_map": project_map_capability_contract(source_task_key=source_task_key or None),
        }
