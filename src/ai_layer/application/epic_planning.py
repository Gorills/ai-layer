from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import (
    append_epic_event,
    capture_identity,
    current_spec,
    epic_for_update,
    epic_payload,
    project_for_root,
    task_row,
)
from ai_layer.db.epic_models import Epic, EpicPlanItem, EpicSpecVersion
from ai_layer.db.models import utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import (
    MAX_EPIC_PLAN_ITEMS,
    MAX_EPIC_SPEC_CHARS,
    bounded_text,
    epic_key,
    final_task_contract,
)


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
                    item.get("title"), field=f"plan[{index}].title", max_chars=240
                ),
                "goal": bounded_text(
                    item.get("goal"), field=f"plan[{index}].goal", max_chars=8_000
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


def _add_final_item(
    db: Session,
    epic: Epic,
    ordinal: int,
    *,
    retry_note: str = "",
) -> None:
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


def retry_final_item(db: Session, epic: Epic, evidence: dict) -> None:
    previous = db.scalar(
        select(func.max(EpicPlanItem.ordinal)).where(EpicPlanItem.epic_id == epic.id)
    )
    _add_final_item(
        db,
        epic,
        int(previous or 0) + 1,
        retry_note="Previous closure attempt failed mechanical Epic gates: " + str(evidence),
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
                acceptance_criteria=(
                    list(phase0_task.acceptance_criteria or []) if phase0_task else []
                ),
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
            change_summary=bounded_text(summary, field="reconciliation summary", max_chars=12_000),
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
