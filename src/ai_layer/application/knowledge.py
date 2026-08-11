from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from ai_layer.core.service import get_project
from ai_layer.db.models import Task, TaskStage
from ai_layer.db.session import session_scope
from ai_layer.memory.knowledge_store import knowledge_status, list_knowledge, upsert_draft
from ai_layer.observability.domain_events import append_event


def _active_delegated_mutation_stage(db, project, worker_id: str) -> tuple[Task, TaskStage]:
    worker = str(worker_id or "").strip()
    if not worker:
        raise ValueError("knowledge_draft_upsert: `worker_id` is required")
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "active")
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None:
        raise RuntimeError("knowledge_draft_upsert requires an active managed task")
    stage = db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == task.id, TaskStage.status == "active")
        .order_by(TaskStage.ordinal.desc())
        .limit(1)
    )
    if task.workflow_profile in {"micro", "analysis_only"}:
        raise RuntimeError(
            "knowledge_draft_upsert requires a review-gated standard/discovery_first task; "
            f"current workflow is `{task.workflow_profile}`"
        )
    if stage is None or stage.kind not in {"implement", "fix"}:
        raise RuntimeError(
            "knowledge_draft_upsert is allowed only to the delegated implementer/fixer; "
            "discovery/review remain read-only"
        )
    if not stage.worker_id:
        raise RuntimeError(
            "knowledge_draft_upsert requires task_stage_delegate before writing a draft"
        )
    if stage.worker_id != worker:
        raise RuntimeError(
            f"knowledge_draft_upsert worker mismatch: active stage belongs to `{stage.worker_id}`, not `{worker}`"
        )
    return task, stage


def status(project_root: str | Path) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        return knowledge_status(db, project)


def _record_draft_review_inspection(db, project, source_task_id: str, cards: list[dict]) -> bool:
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "active")
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None or str(task.id) != str(source_task_id):
        return False
    stage = db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == task.id, TaskStage.status == "active")
        .order_by(TaskStage.ordinal.desc())
        .limit(1)
    )
    if stage is None or stage.kind != "review" or not stage.worker_id or not cards:
        return False
    append_event(
        db,
        event_type="KnowledgeReviewInspected",
        project=project,
        aggregate_type="knowledge_review",
        aggregate_id=str(stage.id),
        payload={
            "task_id": str(task.id),
            "review_stage_id": str(stage.id),
            "draft_cards": len(cards),
            "knowledge_ids": [str(card.get("id")) for card in cards[:50]],
        },
    )
    return True


def list_cards(
    project_root: str | Path,
    *,
    status: str = "VERIFIED",
    source_task_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        cards = list_knowledge(
            db,
            project,
            status=status,
            source_task_id=source_task_id,
            limit=limit,
        )
        if str(status or "").upper() == "DRAFT" and source_task_id:
            _record_draft_review_inspection(db, project, source_task_id, cards)
        return cards


def upsert_card_draft(
    project_root: str | Path,
    *,
    worker_id: str,
    key: str,
    category: str,
    title: str,
    summary: str,
    claims: list[str] | None,
    constraints: list[str] | None,
    unknowns: list[str] | None = None,
    evidence_paths: list[str] | None = None,
) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        task, stage = _active_delegated_mutation_stage(db, project, worker_id)
        result = upsert_draft(
            db,
            project,
            source_task_id=str(task.id),
            key=key,
            category=category,
            title=title,
            summary=summary,
            claims=claims,
            constraints=constraints,
            unknowns=unknowns,
            evidence_paths=evidence_paths,
        )
        append_event(
            db,
            event_type="KnowledgeDraftUpdated",
            project=project,
            aggregate_type="project_knowledge",
            aggregate_id=str(result["id"]),
            payload={
                "key": result.get("key"),
                "category": result.get("category"),
                "task_id": str(task.id),
                "stage_id": str(stage.id),
                "evidence_paths": len(result.get("source_pointers") or []),
            },
        )
        db.commit()
        result["task_key"] = f"T-{int(task.sequence):04d}"
        result["stage_kind"] = stage.kind
        result["publication"] = (
            "DRAFT only. It becomes VERIFIED automatically only when this managed task later passes "
            "an independent review stage."
        )
        return result
