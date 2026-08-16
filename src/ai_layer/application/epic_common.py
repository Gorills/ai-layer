from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.core.service import get_project
from ai_layer.db.epic_models import Epic, EpicAudit, EpicPlanItem, EpicSpecVersion
from ai_layer.db.models import Project, Task
from ai_layer.epics.contracts import epic_key, plan_item_key, spec_quality
from ai_layer.observability.work_events import append_contextual_event
from ai_layer.workspace.repository import capture_repository_state

DOC_PATH_NAMES = {
    "README.md",
    "ARCHITECTURE.md",
    "CURRENT_STATE.md",
    "CHANGELOG.md",
    "ROADMAP.md",
}


def project_for_root(db: Session, project_root: str | Path) -> Project:
    return get_project(db, Path(project_root).expanduser().resolve())


def lock_project(db: Session, project: Project) -> None:
    db.execute(select(Project.id).where(Project.id == project.id).with_for_update())


def sequence_from_key(key: str) -> int:
    text = str(key or "").strip().upper()
    if not text.startswith("E-"):
        raise ValueError("epic_key must look like E-0001")
    try:
        return int(text[2:])
    except ValueError as exc:
        raise ValueError("epic_key must look like E-0001") from exc


def epic_for_update(db: Session, project: Project, key: str) -> Epic:
    sequence = sequence_from_key(key)
    epic = db.scalar(
        select(Epic)
        .where(Epic.project_id == project.id, Epic.sequence == sequence)
        .with_for_update()
    )
    if epic is None:
        raise ValueError(f"Epic {key} was not found in project {project.name}")
    return epic


def current_spec(db: Session, epic: Epic) -> EpicSpecVersion:
    row = db.scalar(
        select(EpicSpecVersion).where(
            EpicSpecVersion.epic_id == epic.id,
            EpicSpecVersion.version == epic.current_spec_version,
        )
    )
    if row is None:
        raise RuntimeError("Epic current spec version is missing")
    return row


def task_row(db: Session, task_id) -> Task | None:
    return db.get(Task, task_id) if task_id else None


def task_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Task Engine returned an invalid task id: {value!r}") from exc


def capture_identity(root: str) -> dict:
    state = capture_repository_state(root)
    return {"digest": str(state["digest"]), "file_count": int(state["file_count"])}


def append_epic_event(
    db: Session,
    project: Project,
    epic: Epic,
    event_type: str,
    payload: dict,
) -> None:
    append_contextual_event(
        db,
        event_type=event_type,
        project=project,
        aggregate_type="epic",
        aggregate_id=str(epic.id),
        payload={"key": epic_key(epic.sequence), **payload},
        epic_id=epic.id,
        importance="high",
    )


def audit_state_payload(epic: Epic, audits: list[EpicAudit]) -> dict:
    current = [item for item in audits if item.spec_version == epic.current_spec_version]
    historical = [item for item in audits if item.spec_version != epic.current_spec_version]
    latest_version = max((int(item.spec_version) for item in audits), default=None)
    if current:
        status = "current"
    elif audits and latest_version is not None and latest_version < epic.current_spec_version:
        status = "stale_after_revision"
    else:
        status = "not_audited"
    return {
        "status": status,
        "current_spec_version": epic.current_spec_version,
        "current_spec_audit_count": len(current),
        "historical_audit_count": len(historical),
        "latest_audit_spec_version": latest_version,
        "reaudit_recommended": status == "stale_after_revision",
    }


def epic_audit_state(db: Session, epic: Epic) -> dict:
    audits = db.scalars(
        select(EpicAudit).where(EpicAudit.epic_id == epic.id).order_by(EpicAudit.created_at.asc())
    ).all()
    return audit_state_payload(epic, list(audits))


def audit_payload(row: EpicAudit, *, current_spec_version: int | None = None) -> dict:
    payload = {
        "id": str(row.id),
        "spec_version": row.spec_version,
        "scope": row.scope,
        "auditor_id": row.auditor_id,
        "summary": row.summary,
        "findings": list(row.findings or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if current_spec_version is not None:
        payload["is_current_spec"] = row.spec_version == current_spec_version
    return payload


def plan_payload(db: Session, row: EpicPlanItem) -> dict:
    linked = task_row(db, row.task_id)
    return {
        "id": str(row.id),
        "key": plan_item_key(row.ordinal),
        "ordinal": row.ordinal,
        "kind": row.kind,
        "title": row.title,
        "goal": row.goal,
        "acceptance_criteria": list(row.acceptance_criteria or []),
        "constraints": list(row.constraints or []),
        "status": row.status,
        "task_id": str(row.task_id) if row.task_id else None,
        "task_key": f"T-{int(linked.sequence):04d}" if linked else None,
        "task_status": linked.status if linked else None,
        "spec_version": row.spec_version,
        "plan_version": row.plan_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def epic_payload(
    db: Session,
    epic: Epic,
    *,
    include_spec: bool,
    include_history: bool,
    include_audits: bool = True,
) -> dict:
    spec = current_spec(db, epic)
    audits = list(
        db.scalars(
            select(EpicAudit)
            .where(EpicAudit.epic_id == epic.id)
            .order_by(EpicAudit.created_at.asc())
        ).all()
    )
    plan = db.scalars(
        select(EpicPlanItem)
        .where(EpicPlanItem.epic_id == epic.id)
        .order_by(EpicPlanItem.ordinal.asc())
    ).all()
    payload = {
        "id": str(epic.id),
        "key": epic_key(epic.sequence),
        "project_id": str(epic.project_id),
        "title": epic.title,
        "status": epic.status,
        "current_spec_version": epic.current_spec_version,
        "approved_spec_version": epic.approved_spec_version,
        "execution_spec_version": epic.execution_spec_version,
        "spec_quality": spec_quality(spec.content),
        "audit_state": audit_state_payload(epic, audits),
        "phase0_task_id": str(epic.phase0_task_id) if epic.phase0_task_id else None,
        "drift_task_id": str(epic.drift_task_id) if epic.drift_task_id else None,
        "phase0_summary": epic.phase0_summary,
        "phase0_corrections": list(epic.phase0_corrections or []),
        "decision_required": list(epic.decision_required or []),
        "plan_version": epic.plan_version,
        "blocked_reason": epic.blocked_reason,
        "created_at": epic.created_at.isoformat() if epic.created_at else None,
        "updated_at": epic.updated_at.isoformat() if epic.updated_at else None,
        "approved_at": epic.approved_at.isoformat() if epic.approved_at else None,
        "completed_at": epic.completed_at.isoformat() if epic.completed_at else None,
        "archived_at": epic.archived_at.isoformat() if epic.archived_at else None,
        "plan": [plan_payload(db, item) for item in plan],
    }
    if include_audits:
        payload["audits"] = [
            audit_payload(item, current_spec_version=epic.current_spec_version) for item in audits
        ]
    if include_spec:
        payload["spec"] = {
            "version": spec.version,
            "content": spec.content,
            "source": spec.source,
            "change_summary": spec.change_summary,
            "rationale": spec.rationale,
            "created_at": spec.created_at.isoformat() if spec.created_at else None,
        }
    if include_history:
        versions = db.scalars(
            select(EpicSpecVersion)
            .where(EpicSpecVersion.epic_id == epic.id)
            .order_by(EpicSpecVersion.version.asc())
        ).all()
        payload["spec_versions"] = [
            {
                "version": item.version,
                "source": item.source,
                "change_summary": item.change_summary,
                "rationale": item.rationale,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in versions
        ]
    return payload
