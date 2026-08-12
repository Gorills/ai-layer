from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import (
    append_epic_event,
    capture_identity,
    current_spec,
    epic_audit_state,
    epic_for_update,
    epic_payload,
    plan_payload,
    project_for_root,
)
from ai_layer.application.epic_task_boundary import accepted_task_identity
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import bounded_text, epic_key

INTERVENING_REVIEW_BLOCK_PREFIX = "intervening_tasks_review_required"


def prepare_spec_audit(project_root: str | Path, *, key: str) -> dict:
    """Return an independent audit packet without previous audit reasoning."""
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        if epic.status not in {"draft", "approved"}:
            raise RuntimeError(
                "Independent specification audit preparation is allowed only before Phase 0 "
                "while Epic is DRAFT/APPROVED"
            )
        spec = current_spec(db, epic)
        return {
            "epic": {
                "id": str(epic.id),
                "key": epic_key(epic.sequence),
                "title": epic.title,
                "status": epic.status,
                "current_spec_version": epic.current_spec_version,
                "approved_spec_version": epic.approved_spec_version,
            },
            "spec": {
                "version": spec.version,
                "content": spec.content,
                "source": spec.source,
                "change_summary": spec.change_summary,
                "rationale": spec.rationale,
            },
            "audit_state": epic_audit_state(db, epic),
            "audit_contract": {
                "workflow_scope": "epic_specification",
                "review_kind": "independent_spec_audit",
                "task_stage": False,
                "repository_mutation": "forbidden",
                "independence": (
                    "Previous audit summaries/findings are intentionally excluded. "
                    "Do not reconstruct or request them before forming this audit."
                ),
                "worker": (
                    "Use a separate read-only host reviewer/explore worker when the host supports it; "
                    "this is not Task DISCOVERY and must not call task_stage_delegate."
                ),
                "source_authority": (
                    "Current repository source inspected with host-native tools is authoritative for "
                    "claims about existing implementation. Scanner/memory hints are secondary evidence."
                ),
                "record_tool": "epic_audit_record",
                "response_mode": "detailed_audit_allowed_when_requested",
                "mandatory_checks": [
                    "Check completeness, internal consistency, architectural fit and acceptance criteria.",
                    "Verify material claims about the existing repository against current source.",
                    "Find hidden temporary/stub/partial solutions inside the selected scope.",
                    "Separate factual defects from optional improvements and genuine product trade-offs.",
                    "Do not mutate repository files while performing this audit.",
                ],
            },
        }


def _task_key(task: Task) -> str:
    return f"T-{int(task.sequence):04d}"


def _linked_task_ids(db: Session, epic: Epic) -> set[UUID]:
    ids: set[UUID] = set()
    if epic.phase0_task_id:
        ids.add(epic.phase0_task_id)
    if epic.drift_task_id:
        ids.add(epic.drift_task_id)
    for task_id in db.scalars(
        select(EpicPlanItem.task_id).where(
            EpicPlanItem.epic_id == epic.id,
            EpicPlanItem.task_id.is_not(None),
        )
    ).all():
        if task_id:
            ids.add(task_id)
    return ids


def _completed_project_tasks(db: Session, project: Project) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(
                Task.project_id == project.id,
                Task.status == "completed",
                Task.completed_at.is_not(None),
            )
            .order_by(Task.completed_at.asc(), Task.sequence.asc())
        ).all()
    )


def _task_changed_paths(task: Task) -> list[str]:
    changes = dict(task.final_changes or {})
    return sorted(
        {
            str(path)
            for group in ("added", "modified", "deleted")
            for path in changes.get(group) or []
        }
    )


def detect_intervening_tasks(
    db: Session,
    project: Project,
    epic: Epic,
    *,
    current_identity: dict | None = None,
) -> dict | None:
    """Recognize repository drift that is fully explained by accepted standalone Tasks.

    This is deliberately conservative. If the current repository does not equal the
    accepted terminal boundary of the latest completed Task, or the baseline-to-terminal
    digest chain is broken, the drift remains unknown.
    """
    if not epic.execution_digest:
        return None
    identity = current_identity or capture_identity(project.root_path)
    if identity["digest"] == epic.execution_digest:
        return None

    completed = _completed_project_tasks(db, project)
    if not completed:
        return None
    identities = [accepted_task_identity(db, task) for task in completed]
    anchor_indexes = [
        index
        for index, task_identity in enumerate(identities)
        if task_identity["digest"] == epic.execution_digest
    ]
    if not anchor_indexes:
        return None
    anchor_index = max(anchor_indexes)
    if identities[-1]["digest"] != identity["digest"]:
        return None

    linked_ids = _linked_task_ids(db, epic)
    after_anchor = completed[anchor_index + 1 :]
    if not after_anchor:
        return None
    if any(task.id in linked_ids for task in after_anchor):
        return None

    expected_digest = epic.execution_digest
    for task, task_identity in zip(after_anchor, identities[anchor_index + 1 :], strict=True):
        if str(task.baseline_digest or "") != expected_digest:
            return None
        expected_digest = task_identity["digest"]
    if expected_digest != identity["digest"]:
        return None

    tasks = [
        {
            "id": str(task.id),
            "key": _task_key(task),
            "goal": task.goal,
            "status": task.status,
            "workflow_profile": task.workflow_profile,
            "risk_level": task.risk_level,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "changed_paths": _task_changed_paths(task),
        }
        for task in after_anchor
    ]
    if not any(item["changed_paths"] for item in tasks):
        return None
    return {
        "expected_digest": epic.execution_digest,
        "current_digest": identity["digest"],
        "current_files": identity["file_count"],
        "tasks": tasks,
        "task_keys": [item["key"] for item in tasks],
    }


def _require_intervening_state(epic: Epic) -> None:
    if epic.status != "blocked" or not str(epic.blocked_reason or "").startswith(
        INTERVENING_REVIEW_BLOCK_PREFIX
    ):
        raise RuntimeError("Epic is not waiting for an intervening-Task impact review")


def prepare_intervening_review(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        _require_intervening_state(epic)
        detected = detect_intervening_tasks(db, project, epic)
        if detected is None:
            raise RuntimeError(
                "Intervening Tasks can no longer explain the current repository state; "
                "call epic_next to re-evaluate drift."
            )
        spec = current_spec(db, epic)
        remaining = db.scalars(
            select(EpicPlanItem)
            .where(
                EpicPlanItem.epic_id == epic.id,
                EpicPlanItem.status == "pending",
            )
            .order_by(EpicPlanItem.ordinal.asc())
        ).all()
        return {
            "epic": {
                "key": epic_key(epic.sequence),
                "title": epic.title,
                "status": epic.status,
                "execution_spec_version": epic.execution_spec_version,
            },
            "execution_spec": {
                "version": spec.version,
                "content": spec.content,
            },
            "intervening_tasks": detected["tasks"],
            "expected_task_keys": detected["task_keys"],
            "remaining_plan": [plan_payload(db, item) for item in remaining],
            "review_contract": {
                "review_kind": "intervening_task_impact",
                "repository_mutation": "forbidden",
                "task_stage": False,
                "source_authority": "current repository source",
                "purpose": (
                    "Decide whether accepted standalone Tasks performed between Epic Tasks materially "
                    "change any remaining Epic assumption, requirement or planned work."
                ),
                "allowed_outcomes": ["unaffected", "reconciliation_required"],
                "record_tool": "epic_intervening_review_record",
                "mandatory_checks": [
                    "Inspect the accepted changed paths and relevant current source.",
                    "Compare changes with remaining plan items and execution-spec assumptions.",
                    "Choose unaffected only when no remaining Epic contract is materially changed.",
                    "Choose reconciliation_required for any material uncertainty or affected assumption.",
                ],
            },
        }


def _resume_status(db: Session, epic: Epic) -> str:
    pending = db.scalar(
        select(EpicPlanItem)
        .where(
            EpicPlanItem.epic_id == epic.id,
            EpicPlanItem.status == "pending",
        )
        .order_by(EpicPlanItem.ordinal.asc())
        .limit(1)
    )
    return "final_review" if pending is not None and pending.kind == "final" else "running"


def record_intervening_review(
    project_root: str | Path,
    *,
    key: str,
    expected_task_keys: list[str],
    outcome: str,
    summary: str,
    affected_plan_items: list[str] | None = None,
    rationale: str = "",
    auditor_id: str = "",
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        _require_intervening_state(epic)
        detected = detect_intervening_tasks(db, project, epic)
        if detected is None:
            raise RuntimeError(
                "Repository state changed since the intervening review was prepared; "
                "call epic_next and prepare the review again."
            )
        expected = [
            str(item).strip().upper() for item in expected_task_keys or [] if str(item).strip()
        ]
        if expected != detected["task_keys"]:
            raise RuntimeError(
                "INTERVENING_TASK_SET_CONFLICT: the accepted Task set changed; "
                "prepare a fresh intervening review."
            )

        verdict = str(outcome or "").strip().casefold()
        if verdict not in {"unaffected", "reconciliation_required"}:
            raise ValueError("outcome must be `unaffected` or `reconciliation_required`")
        affected = [str(item).strip() for item in affected_plan_items or [] if str(item).strip()]
        if verdict == "unaffected" and affected:
            raise ValueError("unaffected review cannot contain affected_plan_items")
        summary_text = bounded_text(summary, field="review summary", max_chars=12_000)
        rationale_text = bounded_text(
            rationale,
            field="review rationale",
            max_chars=8_000,
            required=False,
        )
        auditor = bounded_text(
            auditor_id,
            field="auditor_id",
            max_chars=128,
            required=False,
        )

        if verdict == "unaffected":
            epic.execution_digest = detected["current_digest"]
            epic.execution_files = detected["current_files"]
            epic.status = _resume_status(db, epic)
            epic.blocked_reason = ""
            event_type = "EpicInterveningTasksAccepted"
        else:
            epic.status = "blocked"
            epic.blocked_reason = (
                "repository_drift_detected: accepted intervening Tasks materially affect or may affect "
                "remaining Epic assumptions; targeted reconciliation required"
            )
            event_type = "EpicInterveningTasksRequireReconciliation"
        epic.updated_at = utcnow()
        append_epic_event(
            db,
            project,
            epic,
            event_type,
            {
                "tasks": detected["task_keys"],
                "outcome": verdict,
                "summary": summary_text,
                "affected_plan_items": affected,
                "rationale": rationale_text,
                "auditor_id": auditor,
                "current_digest": detected["current_digest"],
            },
        )
        db.flush()
        payload = epic_payload(db, epic, include_spec=False, include_history=False)
        payload["intervening_review"] = {
            "outcome": verdict,
            "tasks": detected["task_keys"],
            "affected_plan_items": affected,
            "next_tool": "epic_next",
        }
        return payload
