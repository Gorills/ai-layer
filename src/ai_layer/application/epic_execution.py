from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import (
    DOC_PATH_NAMES,
    append_epic_event,
    capture_identity,
    current_spec,
    epic_for_update,
    epic_payload,
    lock_project,
    plan_payload,
    project_for_root,
    task_row,
    task_uuid,
)
from ai_layer.db.epic_models import Epic, EpicPlanItem, EpicSpecVersion
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import (
    EPIC_EXECUTION_STATUSES,
    MAX_EPIC_PLAN_ITEMS,
    MAX_EPIC_SPEC_CHARS,
    bounded_text,
    epic_key,
    final_task_contract,
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


def _write_execution_spec(
    db: Session,
    epic: Epic,
    content: str,
    *,
    source: str,
    change_summary: str,
    rationale: str,
) -> None:
    current = current_spec(db, epic)
    if content == current.content:
        epic.execution_spec_version = current.version
        return
    version = epic.current_spec_version + 1
    db.add(
        EpicSpecVersion(
            epic_id=epic.id,
            version=version,
            content=content,
            source=source,
            change_summary=change_summary,
            rationale=rationale,
        )
    )
    epic.current_spec_version = version
    epic.execution_spec_version = version


def _normalize_work_items(items: list[dict]) -> list[dict]:
    if not items:
        raise ValueError("Epic plan requires at least one implementation Task")
    if len(items) > MAX_EPIC_PLAN_ITEMS - 2:
        raise ValueError(
            f"Epic plan supports at most {MAX_EPIC_PLAN_ITEMS - 2} implementation Tasks"
        )
    result = []
    for index, raw in enumerate(items, start=1):
        item = dict(raw or {})
        result.append(
            {
                "title": bounded_text(
                    item.get("title"),
                    field=f"plan[{index}].title",
                    max_chars=240,
                ),
                "goal": bounded_text(
                    item.get("goal"),
                    field=f"plan[{index}].goal",
                    max_chars=8_000,
                ),
                "acceptance_criteria": [
                    str(value).strip()
                    for value in item.get("acceptance_criteria") or []
                    if str(value).strip()
                ][:50],
                "constraints": [
                    str(value).strip()
                    for value in item.get("constraints") or []
                    if str(value).strip()
                ][:50],
            }
        )
    return result


def _add_work_items(
    db: Session,
    epic: Epic,
    normalized: list[dict],
    *,
    first_ordinal: int,
) -> int:
    spec_version = epic.execution_spec_version or epic.current_spec_version
    ordinal = first_ordinal
    for item in normalized:
        constraints = [
            *item["constraints"],
            f"This Task belongs to {epic_key(epic.sequence)} execution spec v{spec_version}; follow epic_next after Task completion.",
            "Use STANDARD review-gated workflow; do not downgrade Epic work to MICRO.",
        ]
        db.add(
            EpicPlanItem(
                epic_id=epic.id,
                ordinal=ordinal,
                kind="work",
                title=item["title"],
                goal=item["goal"],
                acceptance_criteria=item["acceptance_criteria"],
                constraints=constraints,
                status="pending",
                spec_version=spec_version,
                plan_version=epic.plan_version,
            )
        )
        ordinal += 1
    return ordinal


def _add_final_item(db: Session, epic: Epic, ordinal: int, *, retry_note: str = "") -> None:
    spec_version = epic.execution_spec_version or epic.current_spec_version
    goal, criteria, constraints = final_task_contract(epic_key(epic.sequence), spec_version)
    if retry_note:
        constraints = [*constraints, retry_note]
    db.add(
        EpicPlanItem(
            epic_id=epic.id,
            ordinal=ordinal,
            kind="final",
            title="Final Epic review, documentation and Project Knowledge",
            goal=goal,
            acceptance_criteria=criteria,
            constraints=constraints,
            status="pending",
            spec_version=spec_version,
            plan_version=epic.plan_version,
        )
    )


def set_plan(project_root: str | Path, *, key: str, work_items: list[dict]) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        if epic.status != "planning":
            raise RuntimeError(
                "Epic plan can be created only after successful Phase 0 reconciliation"
            )
        if epic.execution_spec_version is None:
            raise RuntimeError("Epic has no reconciled execution spec")
        if db.scalar(select(EpicPlanItem.id).where(EpicPlanItem.epic_id == epic.id).limit(1)):
            raise RuntimeError("Epic already has a plan")
        normalized = _normalize_work_items(work_items)
        epic.plan_version = 1
        phase0_task = task_row(db, epic.phase0_task_id)
        db.add(
            EpicPlanItem(
                epic_id=epic.id,
                ordinal=0,
                kind="phase0",
                title="Phase 0 — reality and completeness reconciliation",
                goal=phase0_task.goal if phase0_task else "Phase 0 reconciliation",
                acceptance_criteria=list(phase0_task.acceptance_criteria or [])
                if phase0_task
                else [],
                constraints=list(phase0_task.constraints or []) if phase0_task else [],
                status="completed",
                task_id=epic.phase0_task_id,
                spec_version=epic.execution_spec_version,
                plan_version=epic.plan_version,
                completed_at=phase0_task.completed_at if phase0_task else utcnow(),
            )
        )
        final_ordinal = _add_work_items(db, epic, normalized, first_ordinal=1)
        _add_final_item(db, epic, final_ordinal)
        epic.status = "running"
        epic.updated_at = utcnow()
        append_epic_event(
            db,
            project,
            epic,
            "EpicPlanCreated",
            {"work_items": len(normalized), "plan_version": 1},
        )
        db.flush()
        return epic_payload(db, epic, include_spec=False, include_history=False)


def _replace_pending_work(db: Session, epic: Epic, work_items: list[dict]) -> None:
    normalized = _normalize_work_items(work_items)
    existing = db.scalars(
        select(EpicPlanItem)
        .where(EpicPlanItem.epic_id == epic.id)
        .order_by(EpicPlanItem.ordinal.asc())
    ).all()
    if any(item.status == "active" for item in existing):
        raise RuntimeError("Cannot replace pending Epic plan while a linked Task is active")
    completed = [item for item in existing if item.status == "completed"]
    for item in existing:
        if item.status == "pending":
            db.delete(item)
    epic.plan_version += 1
    first = max((item.ordinal for item in completed), default=0) + 1
    final_ordinal = _add_work_items(db, epic, normalized, first_ordinal=first)
    _add_final_item(db, epic, final_ordinal)


def reconcile_complete(
    project_root: str | Path,
    *,
    key: str,
    summary: str,
    updated_spec: str | None = None,
    corrections: list[dict] | None = None,
    human_decisions: list[dict] | None = None,
    remaining_plan: list[dict] | None = None,
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        is_drift = epic.drift_task_id is not None
        task = task_row(db, epic.drift_task_id if is_drift else epic.phase0_task_id)
        if task is None or task.status != "completed":
            raise RuntimeError(
                "The reconciliation analysis Task must be completed before recording its result"
            )
        if not is_drift and epic.status != "phase0":
            raise RuntimeError("Epic is not waiting for Phase 0 reconciliation")
        decisions = list(human_decisions or [])
        correction_items = list(corrections or [])
        current = current_spec(db, epic)
        content = bounded_text(
            updated_spec or current.content,
            field="reconciled epic spec",
            max_chars=MAX_EPIC_SPEC_CHARS,
        )
        _write_execution_spec(
            db,
            epic,
            content,
            source="drift_reconciliation" if is_drift else "phase0",
            change_summary=bounded_text(
                summary,
                field="reconciliation summary",
                max_chars=12_000,
            ),
            rationale=(
                "Automatic reconciliation from current source; material unresolved trade-offs require human decision."
            ),
        )
        if not is_drift:
            epic.phase0_summary = summary
            epic.phase0_corrections = correction_items
        epic.decision_required = decisions
        identity = capture_identity(project.root_path)
        epic.execution_digest = identity["digest"]
        epic.execution_files = identity["file_count"]
        epic.drift_task_id = None
        if decisions:
            epic.status = "blocked"
            epic.blocked_reason = (
                "human_decision_required: reconciliation found a material unresolved trade-off. "
                "Resolve it, revise the spec, and explicitly approve the new baseline."
            )
        elif is_drift:
            if remaining_plan is not None:
                _replace_pending_work(db, epic, remaining_plan)
            epic.status = "running"
            epic.blocked_reason = ""
        else:
            epic.status = "planning"
            epic.blocked_reason = ""
        epic.updated_at = utcnow()
        append_epic_event(
            db,
            project,
            epic,
            "EpicReconciled",
            {
                "phase0": not is_drift,
                "execution_spec_version": epic.execution_spec_version,
                "corrections": len(correction_items),
                "human_decisions": len(decisions),
            },
        )
        db.flush()
        return epic_payload(db, epic, include_spec=True, include_history=True)


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


def _retry_final_item(db: Session, epic: Epic, evidence: dict) -> None:
    previous = db.scalar(
        select(func.max(EpicPlanItem.ordinal)).where(EpicPlanItem.epic_id == epic.id)
    )
    _add_final_item(
        db,
        epic,
        int(previous or 0) + 1,
        retry_note="Previous closure attempt failed mechanical Epic gates: " + str(evidence),
    )


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
    if task.status == "blocked":
        epic.status = "blocked"
        epic.blocked_reason = task.blocked_reason or "Linked Task is blocked"
        return {"state": "blocked", "task": task_to_dict(db, task, include_history=False)}
    if task.status == "active":
        return {"state": "task_active", "task": task_to_dict(db, task, include_history=False)}
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
        _retry_final_item(db, epic, evidence)
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
            if sync and sync.get("state") == "task_active":
                action = {"action": "continue_task", "tool": "task_next", "task": sync["task"]}
            elif epic.status == "completed":
                action = {"action": "archive", "tool": "epic_archive"}
            elif epic.status == "blocked":
                action = {"action": "human_attention_required", "message": epic.blocked_reason}
            else:
                drift = _drift_action(project, epic)
                if drift is not None:
                    epic.status = "blocked"
                    epic.blocked_reason = "repository_drift_detected: targeted reconciliation required before the next Epic Task"
                    append_epic_event(
                        db,
                        project,
                        epic,
                        "EpicDriftDetected",
                        {"expected": drift["expected_digest"], "current": drift["current_digest"]},
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
                            "action": "start_final_review"
                            if pending.kind == "final"
                            else "start_next_task",
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
