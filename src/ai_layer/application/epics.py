from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.core.service import get_project
from ai_layer.db.epic_models import Epic, EpicAudit, EpicPlanItem, EpicSpecVersion
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import (
    EPIC_EXECUTION_STATUSES,
    MAX_EPIC_AUDIT_FINDINGS,
    MAX_EPIC_PLAN_ITEMS,
    MAX_EPIC_SPEC_CHARS,
    MAX_EPIC_TITLE_CHARS,
    bounded_text,
    epic_key,
    final_task_contract,
    phase0_contract,
    plan_item_key,
    spec_quality,
)
from ai_layer.observability.domain_events import append_event
from ai_layer.tasks.lifecycle import create_task
from ai_layer.tasks.views import task_to_dict
from ai_layer.workspace.repository import capture_repository_state


DOC_PATH_NAMES = {
    "README.md",
    "ARCHITECTURE.md",
    "CURRENT_STATE.md",
    "CHANGELOG.md",
    "ROADMAP.md",
}


def _project(db: Session, project_root: str | Path) -> Project:
    return get_project(db, Path(project_root).expanduser().resolve())


def _lock_project(db: Session, project: Project) -> None:
    db.execute(select(Project.id).where(Project.id == project.id).with_for_update())


def _epic_for_update(db: Session, project: Project, key: str) -> Epic:
    sequence = _sequence_from_key(key)
    epic = db.scalar(
        select(Epic)
        .where(Epic.project_id == project.id, Epic.sequence == sequence)
        .with_for_update()
    )
    if epic is None:
        raise ValueError(f"Epic {key} was not found in project {project.name}")
    return epic


def _sequence_from_key(key: str) -> int:
    text = str(key or "").strip().upper()
    if not text.startswith("E-"):
        raise ValueError("epic_key must look like E-0001")
    try:
        return int(text[2:])
    except ValueError as exc:
        raise ValueError("epic_key must look like E-0001") from exc


def _current_spec(db: Session, epic: Epic) -> EpicSpecVersion:
    row = db.scalar(
        select(EpicSpecVersion).where(
            EpicSpecVersion.epic_id == epic.id,
            EpicSpecVersion.version == epic.current_spec_version,
        )
    )
    if row is None:
        raise RuntimeError("Epic current spec version is missing")
    return row


def _spec(db: Session, epic: Epic, version: int) -> EpicSpecVersion:
    row = db.scalar(
        select(EpicSpecVersion).where(
            EpicSpecVersion.epic_id == epic.id,
            EpicSpecVersion.version == int(version),
        )
    )
    if row is None:
        raise ValueError(f"Epic spec v{version} was not found")
    return row


def _task(db: Session, task_id) -> Task | None:
    return db.get(Task, task_id) if task_id else None


def _task_open(task: Task | None) -> bool:
    return bool(task and task.status in {"active", "blocked"})


def _capture(root: str) -> dict:
    state = capture_repository_state(root)
    return {"digest": str(state["digest"]), "file_count": int(state["file_count"])}


def _event(db: Session, project: Project, epic: Epic, event_type: str, payload: dict) -> None:
    append_event(
        db,
        event_type=event_type,
        project=project,
        aggregate_type="epic",
        aggregate_id=str(epic.id),
        payload={"key": epic_key(epic.sequence), **payload},
    )


def _audit_payload(row: EpicAudit) -> dict:
    return {
        "id": str(row.id),
        "spec_version": row.spec_version,
        "scope": row.scope,
        "auditor_id": row.auditor_id,
        "summary": row.summary,
        "findings": list(row.findings or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _plan_payload(db: Session, row: EpicPlanItem) -> dict:
    linked = _task(db, row.task_id)
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


def _epic_payload(db: Session, epic: Epic, *, include_spec: bool, include_history: bool) -> dict:
    current_spec = _current_spec(db, epic)
    audits = db.scalars(
        select(EpicAudit)
        .where(EpicAudit.epic_id == epic.id)
        .order_by(EpicAudit.created_at.asc())
    ).all()
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
        "spec_quality": spec_quality(current_spec.content),
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
        "audits": [_audit_payload(item) for item in audits],
        "plan": [_plan_payload(db, item) for item in plan],
    }
    if include_spec:
        payload["spec"] = {
            "version": current_spec.version,
            "content": current_spec.content,
            "source": current_spec.source,
            "change_summary": current_spec.change_summary,
            "rationale": current_spec.rationale,
            "created_at": current_spec.created_at.isoformat() if current_spec.created_at else None,
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
                "content": item.content if include_spec else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in versions
        ]
    return payload


def create(project_root: str | Path, *, title: str, spec_markdown: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        _lock_project(db, project)
        title_text = bounded_text(title, field="epic title", max_chars=MAX_EPIC_TITLE_CHARS)
        spec_text = bounded_text(
            spec_markdown, field="epic spec", max_chars=MAX_EPIC_SPEC_CHARS
        )
        previous = db.scalar(select(func.max(Epic.sequence)).where(Epic.project_id == project.id))
        epic = Epic(project_id=project.id, sequence=int(previous or 0) + 1, title=title_text)
        db.add(epic)
        db.flush()
        db.add(
            EpicSpecVersion(
                epic_id=epic.id,
                version=1,
                content=spec_text,
                source="draft",
                change_summary="Initial Epic specification created from the accepted discussion context.",
            )
        )
        _event(db, project, epic, "EpicCreated", {"spec_version": 1})
        db.flush()
        return _epic_payload(db, epic, include_spec=True, include_history=True)


def list_for_project(project_root: str | Path, *, include_archived: bool = True) -> list[dict]:
    with session_scope() as db:
        project = _project(db, project_root)
        stmt = select(Epic).where(Epic.project_id == project.id)
        if not include_archived:
            stmt = stmt.where(Epic.status != "archived")
        rows = db.scalars(stmt.order_by(Epic.sequence.desc())).all()
        return [_epic_payload(db, row, include_spec=False, include_history=False) for row in rows]


def get(project_root: str | Path, *, key: str, include_history: bool = True) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        return _epic_payload(db, epic, include_spec=True, include_history=include_history)


def revise_spec(
    project_root: str | Path,
    *,
    key: str,
    spec_markdown: str,
    change_summary: str,
    rationale: str = "",
) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        if epic.status not in {"draft", "blocked"}:
            raise RuntimeError("Spec may be manually revised only while Epic is draft or blocked")
        content = bounded_text(
            spec_markdown, field="epic spec", max_chars=MAX_EPIC_SPEC_CHARS
        )
        current = _current_spec(db, epic)
        if content == current.content:
            return _epic_payload(db, epic, include_spec=True, include_history=True)
        version = epic.current_spec_version + 1
        db.add(
            EpicSpecVersion(
                epic_id=epic.id,
                version=version,
                content=content,
                source="revision",
                change_summary=bounded_text(
                    change_summary, field="change_summary", max_chars=4_000
                ),
                rationale=bounded_text(rationale, field="rationale", max_chars=8_000, required=False),
            )
        )
        epic.current_spec_version = version
        epic.status = "draft"
        epic.blocked_reason = ""
        epic.decision_required = []
        epic.updated_at = utcnow()
        _event(db, project, epic, "EpicSpecRevised", {"spec_version": version})
        db.flush()
        return _epic_payload(db, epic, include_spec=True, include_history=True)


def record_audit(
    project_root: str | Path,
    *,
    key: str,
    summary: str,
    findings: list[dict] | None = None,
    scope: str = "independent",
    auditor_id: str = "",
) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        items = list(findings or [])[:MAX_EPIC_AUDIT_FINDINGS]
        row = EpicAudit(
            epic_id=epic.id,
            spec_version=epic.current_spec_version,
            scope=bounded_text(scope, field="audit scope", max_chars=64),
            auditor_id=bounded_text(
                auditor_id, field="auditor_id", max_chars=128, required=False
            ),
            summary=bounded_text(summary, field="audit summary", max_chars=12_000),
            findings=items,
        )
        db.add(row)
        _event(
            db,
            project,
            epic,
            "EpicAudited",
            {"spec_version": epic.current_spec_version, "findings": len(items)},
        )
        db.flush()
        return _audit_payload(row)


def approve(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        if epic.status != "draft":
            raise RuntimeError("Only a DRAFT Epic can be approved")
        quality = spec_quality(_current_spec(db, epic).content)
        if quality["missing_recommended_sections"]:
            raise RuntimeError(
                "Epic spec is missing required human-readable sections: "
                + ", ".join(quality["missing_recommended_sections"])
            )
        epic.status = "approved"
        epic.approved_spec_version = epic.current_spec_version
        epic.execution_spec_version = None
        epic.approved_at = utcnow()
        epic.updated_at = utcnow()
        _event(db, project, epic, "EpicApproved", {"spec_version": epic.current_spec_version})
        db.flush()
        return _epic_payload(db, epic, include_spec=True, include_history=True)


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
    contract = phase0_contract(
        {"key": key, "approved_spec_version": epic.approved_spec_version}
    )
    goal = (
        f"Epic {key} Phase 0. Reconcile approved spec v{epic.approved_spec_version} against the current "
        "repository before any implementation Task is created. Call epic_get for the full spec."
    )
    criteria = list(contract["mandatory_checks"])
    constraints = [
        "Analysis-only: do not mutate repository files or external systems.",
        "Return verified facts, risks and a proposed decomposition through the normal DISCOVERY completion contract.",
        "After this Task completes, the orchestrator must call epic_reconcile_complete; do not create implementation Tasks directly.",
    ]
    return goal, criteria, constraints


def start_next(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        _lock_project(db, project)
        epic = _epic_for_update(db, project, key)
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
            epic.phase0_task_id = result["id"]
            epic.status = "phase0"
            epic.updated_at = utcnow()
            _event(db, project, epic, "EpicPhase0Started", {"task": result["key"]})
            db.flush()
            return {"epic": _epic_payload(db, epic, include_spec=False, include_history=False), "task": result}

        if epic.status not in {"running", "final_review"}:
            raise RuntimeError(f"epic_start_next is not valid while Epic status is {epic.status}")
        pending = db.scalar(
            select(EpicPlanItem)
            .where(
                EpicPlanItem.epic_id == epic.id,
                EpicPlanItem.status == "pending",
            )
            .order_by(EpicPlanItem.ordinal.asc())
            .limit(1)
            .with_for_update()
        )
        if pending is None:
            raise RuntimeError("Epic has no pending plan item to start")
        workflow = "standard"
        result = create_task(
            db,
            project,
            goal=pending.goal,
            acceptance_criteria=list(pending.acceptance_criteria or []),
            constraints=list(pending.constraints or []),
            workflow=workflow,
        )
        pending.task_id = result["id"]
        pending.status = "active"
        epic.status = "final_review" if pending.kind == "final" else "running"
        epic.updated_at = utcnow()
        _event(
            db,
            project,
            epic,
            "EpicPlanItemStarted",
            {"plan_item": plan_item_key(pending.ordinal), "kind": pending.kind, "task": result["key"]},
        )
        db.flush()
        return {"epic": _epic_payload(db, epic, include_spec=False, include_history=False), "task": result}


def _write_execution_spec(
    db: Session,
    epic: Epic,
    content: str,
    *,
    source: str,
    change_summary: str,
    rationale: str,
) -> None:
    current = _current_spec(db, epic)
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
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        phase0 = epic.status == "phase0"
        task_id = epic.phase0_task_id if phase0 else epic.drift_task_id
        task = _task(db, task_id)
        if task is None or task.status != "completed":
            raise RuntimeError("The reconciliation analysis Task must be completed before recording its result")
        decisions = list(human_decisions or [])
        correction_items = list(corrections or [])
        current = _current_spec(db, epic)
        content = bounded_text(
            updated_spec or current.content,
            field="reconciled epic spec",
            max_chars=MAX_EPIC_SPEC_CHARS,
        )
        _write_execution_spec(
            db,
            epic,
            content,
            source="phase0" if phase0 else "drift_reconciliation",
            change_summary=bounded_text(summary, field="reconciliation summary", max_chars=12_000),
            rationale="Automatic reconciliation from current source; material unresolved trade-offs require human decision.",
        )
        epic.phase0_summary = summary if phase0 else epic.phase0_summary
        if phase0:
            epic.phase0_corrections = correction_items
        epic.decision_required = decisions
        state = _capture(project.root_path)
        epic.execution_digest = state["digest"]
        epic.execution_files = state["file_count"]
        epic.drift_task_id = None
        if decisions:
            epic.status = "blocked"
            epic.blocked_reason = "human_decision_required: Phase 0/reconciliation found a material unresolved trade-off."
        elif phase0:
            epic.status = "planning"
            epic.blocked_reason = ""
        else:
            if remaining_plan is not None:
                _replace_pending_work(db, epic, remaining_plan)
            epic.status = "running"
            epic.blocked_reason = ""
        epic.updated_at = utcnow()
        _event(
            db,
            project,
            epic,
            "EpicReconciled",
            {
                "phase0": phase0,
                "execution_spec_version": epic.execution_spec_version,
                "corrections": len(correction_items),
                "human_decisions": len(decisions),
            },
        )
        db.flush()
        return _epic_payload(db, epic, include_spec=True, include_history=True)


def _normalize_work_items(items: list[dict]) -> list[dict]:
    if not items:
        raise ValueError("Epic plan requires at least one implementation Task")
    if len(items) > MAX_EPIC_PLAN_ITEMS - 2:
        raise ValueError(f"Epic plan supports at most {MAX_EPIC_PLAN_ITEMS - 2} implementation Tasks")
    result = []
    for index, raw in enumerate(items, start=1):
        item = dict(raw or {})
        title = bounded_text(item.get("title"), field=f"plan[{index}].title", max_chars=240)
        goal = bounded_text(item.get("goal"), field=f"plan[{index}].goal", max_chars=8_000)
        criteria = [str(value).strip() for value in item.get("acceptance_criteria") or [] if str(value).strip()]
        constraints = [str(value).strip() for value in item.get("constraints") or [] if str(value).strip()]
        result.append(
            {"title": title, "goal": goal, "acceptance_criteria": criteria[:50], "constraints": constraints[:50]}
        )
    return result


def set_plan(project_root: str | Path, *, key: str, work_items: list[dict]) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        if epic.status != "planning":
            raise RuntimeError("Epic plan can be created only after successful Phase 0 reconciliation")
        if epic.execution_spec_version is None:
            raise RuntimeError("Epic has no reconciled execution spec")
        existing = db.scalar(select(EpicPlanItem.id).where(EpicPlanItem.epic_id == epic.id).limit(1))
        if existing is not None:
            raise RuntimeError("Epic already has a plan; use drift reconciliation to replace only pending work")
        normalized = _normalize_work_items(work_items)
        epic.plan_version = 1
        phase0_task = _task(db, epic.phase0_task_id)
        db.add(
            EpicPlanItem(
                epic_id=epic.id,
                ordinal=0,
                kind="phase0",
                title="Phase 0 — reality and completeness reconciliation",
                goal=phase0_task.goal if phase0_task else "Phase 0 reconciliation",
                acceptance_criteria=list(phase0_task.acceptance_criteria or []) if phase0_task else [],
                constraints=list(phase0_task.constraints or []) if phase0_task else [],
                status="completed",
                task_id=epic.phase0_task_id,
                spec_version=epic.execution_spec_version,
                plan_version=epic.plan_version,
                completed_at=phase0_task.completed_at if phase0_task else utcnow(),
            )
        )
        for ordinal, item in enumerate(normalized, start=1):
            db.add(
                EpicPlanItem(
                    epic_id=epic.id,
                    ordinal=ordinal,
                    kind="work",
                    title=item["title"],
                    goal=item["goal"],
                    acceptance_criteria=item["acceptance_criteria"],
                    constraints=[
                        *item["constraints"],
                        f"This Task belongs to {epic_key(epic.sequence)} execution spec v{epic.execution_spec_version}; follow epic_next after Task completion.",
                        "Use STANDARD review-gated workflow; do not downgrade Epic work to MICRO.",
                    ],
                    status="pending",
                    spec_version=epic.execution_spec_version,
                    plan_version=epic.plan_version,
                )
            )
        final_goal, final_criteria, final_constraints = final_task_contract(
            epic_key(epic.sequence), epic.execution_spec_version
        )
        db.add(
            EpicPlanItem(
                epic_id=epic.id,
                ordinal=len(normalized) + 1,
                kind="final",
                title="Final Epic review, documentation and Project Knowledge",
                goal=final_goal,
                acceptance_criteria=final_criteria,
                constraints=final_constraints,
                status="pending",
                spec_version=epic.execution_spec_version,
                plan_version=epic.plan_version,
            )
        )
        epic.status = "running"
        epic.updated_at = utcnow()
        _event(db, project, epic, "EpicPlanCreated", {"work_items": len(normalized), "plan_version": 1})
        db.flush()
        return _epic_payload(db, epic, include_spec=False, include_history=False)


def _replace_pending_work(db: Session, epic: Epic, work_items: list[dict]) -> None:
    normalized = _normalize_work_items(work_items)
    existing = db.scalars(
        select(EpicPlanItem)
        .where(EpicPlanItem.epic_id == epic.id)
        .order_by(EpicPlanItem.ordinal.asc())
    ).all()
    completed = [item for item in existing if item.status == "completed"]
    if any(item.status == "active" for item in existing):
        raise RuntimeError("Cannot replace pending Epic plan while a linked Task is active")
    for item in existing:
        if item.status == "pending":
            db.delete(item)
    next_ordinal = max((item.ordinal for item in completed), default=0) + 1
    epic.plan_version += 1
    for item in normalized:
        db.add(
            EpicPlanItem(
                epic_id=epic.id,
                ordinal=next_ordinal,
                kind="work",
                title=item["title"],
                goal=item["goal"],
                acceptance_criteria=item["acceptance_criteria"],
                constraints=item["constraints"],
                status="pending",
                spec_version=epic.execution_spec_version or epic.current_spec_version,
                plan_version=epic.plan_version,
            )
        )
        next_ordinal += 1
    goal, criteria, constraints = final_task_contract(
        epic_key(epic.sequence), epic.execution_spec_version or epic.current_spec_version
    )
    db.add(
        EpicPlanItem(
            epic_id=epic.id,
            ordinal=next_ordinal,
            kind="final",
            title="Final Epic review, documentation and Project Knowledge",
            goal=goal,
            acceptance_criteria=criteria,
            constraints=constraints,
            status="pending",
            spec_version=epic.execution_spec_version or epic.current_spec_version,
            plan_version=epic.plan_version,
        )
    )


def _final_closure_evidence(db: Session, task: Task) -> dict:
    changes = dict(task.final_changes or {})
    paths = {
        str(path)
        for group in ("added", "modified", "deleted")
        for path in changes.get(group) or []
    }
    docs_updated = any(path in DOC_PATH_NAMES or path.startswith("docs/") for path in paths)
    knowledge_event = db.scalar(
        select(RuntimeEvent)
        .where(
            RuntimeEvent.event_type == "KnowledgePublished",
            RuntimeEvent.aggregate_type == "task",
            RuntimeEvent.aggregate_id == str(task.id),
        )
        .order_by(RuntimeEvent.created_at.desc())
        .limit(1)
    )
    published = int((knowledge_event.payload or {}).get("published") or 0) if knowledge_event else 0
    return {"docs_updated": docs_updated, "knowledge_published": published, "changed_paths": sorted(paths)}


def _retry_final_item(db: Session, epic: Epic, evidence: dict) -> None:
    previous = db.scalar(
        select(func.max(EpicPlanItem.ordinal)).where(EpicPlanItem.epic_id == epic.id)
    )
    goal, criteria, constraints = final_task_contract(
        epic_key(epic.sequence), epic.execution_spec_version or epic.current_spec_version
    )
    constraints = [
        *constraints,
        "Previous closure attempt failed mechanical Epic gates: " + str(evidence),
    ]
    db.add(
        EpicPlanItem(
            epic_id=epic.id,
            ordinal=int(previous or 0) + 1,
            kind="final",
            title="Final Epic review retry",
            goal=goal,
            acceptance_criteria=criteria,
            constraints=constraints,
            status="pending",
            spec_version=epic.execution_spec_version or epic.current_spec_version,
            plan_version=epic.plan_version,
        )
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
    task = _task(db, active.task_id)
    if task is None:
        active.status = "blocked"
        epic.status = "blocked"
        epic.blocked_reason = "Linked Epic Task record is missing"
        return {"state": "blocked"}
    if task.status == "blocked":
        active.status = "blocked"
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
    state = _capture(project.root_path)
    epic.execution_digest = state["digest"]
    epic.execution_files = state["file_count"]
    if active.kind == "final":
        evidence = _final_closure_evidence(db, task)
        if evidence["docs_updated"] and evidence["knowledge_published"] > 0:
            epic.status = "completed"
            epic.completed_at = utcnow()
            epic.blocked_reason = ""
            _event(db, project, epic, "EpicCompleted", {"final_task": f"T-{int(task.sequence):04d}", **evidence})
            return {"state": "completed", "closure": evidence}
        _retry_final_item(db, epic, evidence)
        epic.status = "final_review"
        epic.blocked_reason = ""
        _event(db, project, epic, "EpicFinalReviewRetryRequired", evidence)
        return {"state": "final_retry", "closure": evidence}
    _event(
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
    state = _capture(project.root_path)
    if state["digest"] == epic.execution_digest:
        return None
    return {
        "action": "reconcile_repository_drift",
        "tool": "epic_start_next",
        "message": "Repository changed outside the last accepted Epic Task boundary. Run targeted read-only reconciliation before starting the next planned Task.",
        "expected_digest": epic.execution_digest,
        "current_digest": state["digest"],
    }


def next_action(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        if epic.status == "draft":
            return {
                "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                "next_action": {
                    "action": "audit_revise_or_approve",
                    "allowed_tools": ["epic_audit_record", "epic_spec_revise", "epic_approve"],
                    "message": "Spec is still mutable. Run as many independent audit/revision rounds as needed; approval freezes the human baseline.",
                },
            }
        if epic.status == "approved":
            return {
                "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                "next_action": {"action": "start_phase0", "tool": "epic_start_next"},
            }
        if epic.status == "phase0":
            task = _task(db, epic.phase0_task_id)
            if _task_open(task):
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {
                        "action": "continue_task",
                        "tool": "task_next",
                        "task": task_to_dict(db, task, include_history=False),
                    },
                }
            if task and task.status == "completed":
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {
                        "action": "record_phase0_reconciliation",
                        "tool": "epic_reconcile_complete",
                        "message": "Apply all non-branching/strong-recommendation corrections to the execution spec. Supply human_decisions only for genuine material trade-offs.",
                    },
                }
        if epic.status == "planning":
            return {
                "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                "next_action": {
                    "action": "create_task_plan",
                    "tool": "epic_plan_set",
                    "message": "Create implementation Tasks from the reconciled execution spec. Phase 0 and the final closure/review Task are added automatically.",
                },
            }
        if epic.status in {"running", "final_review"}:
            sync = _sync_active_item(db, project, epic)
            db.flush()
            if sync and sync.get("state") == "task_active":
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {"action": "continue_task", "tool": "task_next", "task": sync["task"]},
                }
            if epic.status == "completed":
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {"action": "archive", "tool": "epic_archive"},
                }
            if epic.status == "blocked":
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {"action": "human_attention_required", "message": epic.blocked_reason},
                }
            drift = _drift_action(project, epic)
            if drift is not None:
                epic.status = "blocked"
                epic.blocked_reason = "repository_drift_detected: targeted reconciliation required before the next Epic Task"
                _event(db, project, epic, "EpicDriftDetected", {"expected": drift["expected_digest"], "current": drift["current_digest"]})
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": drift,
                }
            pending = db.scalar(
                select(EpicPlanItem)
                .where(EpicPlanItem.epic_id == epic.id, EpicPlanItem.status == "pending")
                .order_by(EpicPlanItem.ordinal.asc())
                .limit(1)
            )
            if pending is not None:
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {
                        "action": "start_final_review" if pending.kind == "final" else "start_next_task",
                        "tool": "epic_start_next",
                        "plan_item": _plan_payload(db, pending),
                    },
                }
        if epic.status == "blocked":
            if epic.blocked_reason.startswith("repository_drift_detected"):
                return {
                    "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                    "next_action": {
                        "action": "start_drift_reconciliation",
                        "tool": "epic_start_next",
                        "message": "Run a targeted analysis-only reconciliation. Resolve obvious drift automatically; ask the human only for material trade-offs.",
                    },
                }
            return {
                "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                "next_action": {"action": "human_attention_required", "message": epic.blocked_reason},
            }
        if epic.status == "completed":
            return {
                "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
                "next_action": {"action": "archive", "tool": "epic_archive"},
            }
        return {
            "epic": _epic_payload(db, epic, include_spec=False, include_history=False),
            "next_action": {"action": "none", "message": f"Epic status is {epic.status}"},
        }


def start_drift_reconciliation(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        _lock_project(db, project)
        epic = _epic_for_update(db, project, key)
        if epic.status != "blocked" or not epic.blocked_reason.startswith("repository_drift_detected"):
            raise RuntimeError("Epic is not waiting for repository drift reconciliation")
        _assert_no_open_task(db, project)
        goal = (
            f"Targeted drift reconciliation for {epic_key(epic.sequence)} execution spec v{epic.execution_spec_version}. "
            "Compare repository changes since the last accepted Epic Task boundary with remaining spec assumptions."
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
        epic.drift_task_id = result["id"]
        epic.status = "running"
        epic.blocked_reason = ""
        _event(db, project, epic, "EpicDriftReconciliationStarted", {"task": result["key"]})
        db.flush()
        return {"epic": _epic_payload(db, epic, include_spec=False, include_history=False), "task": result}


def archive(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        epic = _epic_for_update(db, project, key)
        if epic.status != "completed":
            raise RuntimeError("Only a mechanically completed Epic may be archived")
        epic.status = "archived"
        epic.archived_at = utcnow()
        epic.updated_at = utcnow()
        _event(db, project, epic, "EpicArchived", {"spec_version": epic.execution_spec_version})
        db.flush()
        return _epic_payload(db, epic, include_spec=True, include_history=True)
