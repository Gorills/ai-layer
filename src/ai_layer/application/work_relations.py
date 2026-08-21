from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, Task, utcnow
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import (
    EpicPlanWorkRelation,
    EpicWorkRelation,
    TaskWorkRelation,
    WorkHierarchy,
)
from ai_layer.observability.work_events import append_contextual_event

_WORK_KEY = re.compile(r"^W-(\d+)$")


@dataclass(frozen=True, slots=True)
class TaskWorkBinding:
    work: WorkItem
    role: str


def _sequence_from_key(value: str) -> int:
    match = _WORK_KEY.fullmatch(str(value or "").strip())
    if match is None:
        raise ValueError("work_key must look like W-0001")
    sequence = int(match.group(1))
    if sequence <= 0:
        raise ValueError("work_key must look like W-0001")
    return sequence


def work_for_key(db: Session, project: Project, work_key: str) -> WorkItem:
    sequence = _sequence_from_key(work_key)
    work = db.scalar(
        select(WorkItem).where(
            WorkItem.project_id == project.id,
            WorkItem.sequence == sequence,
        )
    )
    if work is None:
        raise ValueError(f"work {work_key} does not exist in this project")
    return work


def _lock_project(db: Session, project: Project) -> None:
    if db.scalar(select(Project.id).where(Project.id == project.id).with_for_update()) is None:
        raise RuntimeError("project no longer exists")


def _next_work_sequence(db: Session, project: Project) -> int:
    _lock_project(db, project)
    previous = db.scalar(
        select(func.coalesce(func.max(WorkItem.sequence), 0)).where(WorkItem.project_id == project.id)
    )
    return int(previous or 0) + 1


def _ensure_hierarchy(
    db: Session,
    work: WorkItem,
    *,
    parent_work_id: UUID | None,
    root_work_id: UUID,
) -> WorkHierarchy:
    row = db.get(WorkHierarchy, work.id)
    if row is None:
        row = WorkHierarchy(
            work_id=work.id,
            parent_work_id=parent_work_id,
            root_work_id=root_work_id,
        )
        db.add(row)
        db.flush()
        return row
    if row.parent_work_id != parent_work_id or row.root_work_id != root_work_id:
        raise RuntimeError("WORK_HIERARCHY_CONFLICT: canonical Work hierarchy already differs")
    return row


def create_control_plane_work(
    db: Session,
    project: Project,
    *,
    goal: str,
    kind: str = "change",
    linked_epic_id: UUID | None = None,
    parent_work: WorkItem | None = None,
    root_work: WorkItem | None = None,
) -> WorkItem:
    if parent_work is not None and root_work is None:
        raise ValueError("child Work requires root_work")
    if parent_work is not None and parent_work.project_id != project.id:
        raise ValueError("parent Work belongs to another project")
    if root_work is not None and root_work.project_id != project.id:
        raise ValueError("root Work belongs to another project")
    now = utcnow()
    work = WorkItem(
        project_id=project.id,
        sequence=_next_work_sequence(db, project),
        goal=str(goal).strip(),
        kind=kind,
        status="active",
        map_disposition={"status": "pending"},
        observability_coverage="control_plane_only",
        assurance="agent_reported",
        linked_epic_id=linked_epic_id,
        started_at=now,
        updated_at=now,
        last_milestone_at=now,
    )
    db.add(work)
    db.flush()
    root_id = root_work.id if root_work is not None else work.id
    _ensure_hierarchy(
        db,
        work,
        parent_work_id=parent_work.id if parent_work is not None else None,
        root_work_id=root_id,
    )
    append_contextual_event(
        db,
        event_type="WorkStarted",
        project=project,
        aggregate_type="work",
        aggregate_id=str(work.id),
        work=work,
        epic_id=linked_epic_id,
        payload={"goal": work.goal, "kind": work.kind, "status": work.status},
        importance="high",
    )
    return work


def task_work_binding(db: Session, task: Task) -> TaskWorkBinding | None:
    relation = db.get(TaskWorkRelation, task.id)
    if relation is None:
        return None
    work = db.get(WorkItem, relation.work_id)
    if work is None or work.project_id != task.project_id:
        raise RuntimeError("TASK_WORK_RELATION_CORRUPT: canonical Work is missing or cross-project")
    return TaskWorkBinding(work=work, role=relation.role)


def _task_is_epic_control(db: Session, task: Task) -> bool:
    epic_control = db.scalar(
        select(Epic.id)
        .where(or_(Epic.phase0_task_id == task.id, Epic.drift_task_id == task.id))
        .limit(1)
    )
    if epic_control is not None:
        return True
    plan_control = db.scalar(
        select(EpicPlanItem.id)
        .where(
            EpicPlanItem.task_id == task.id,
            EpicPlanItem.kind.in_(("phase0", "final")),
        )
        .limit(1)
    )
    return plan_control is not None


def bind_task_work(
    db: Session,
    project: Project,
    task: Task,
    work: WorkItem,
    *,
    role: str = "outcome",
) -> TaskWorkBinding:
    if role not in {"outcome", "epic_control"}:
        raise ValueError("role must be outcome or epic_control")
    if task.project_id != project.id or work.project_id != project.id:
        raise ValueError("Task and Work must belong to the same project")
    existing = db.get(TaskWorkRelation, task.id)
    if existing is not None:
        if existing.work_id != work.id or existing.role != role:
            raise RuntimeError("TASK_WORK_RELATION_CONFLICT: Task already belongs to another Work")
        return TaskWorkBinding(work=work, role=role)

    if role == "outcome" and task.status in {"active", "blocked"}:
        other = db.scalar(
            select(TaskWorkRelation.task_id)
            .join(Task, Task.id == TaskWorkRelation.task_id)
            .where(
                TaskWorkRelation.work_id == work.id,
                TaskWorkRelation.role == "outcome",
                TaskWorkRelation.task_id != task.id,
                Task.status.in_(("active", "blocked")),
            )
            .limit(1)
        )
        if other is not None:
            raise RuntimeError("WORK_ALREADY_HAS_OPEN_ASSURANCE: Work already has an open managed Task")

    db.add(TaskWorkRelation(task_id=task.id, work_id=work.id, role=role))
    if role == "outcome":
        work.linked_task_id = task.id
        work.updated_at = utcnow()
        work.last_milestone_at = work.updated_at
    db.flush()
    return TaskWorkBinding(work=work, role=role)


def _legacy_task_candidates(db: Session, task: Task) -> list[WorkItem]:
    return list(
        db.scalars(
            select(WorkItem)
            .where(
                WorkItem.project_id == task.project_id,
                WorkItem.linked_task_id == task.id,
            )
            .order_by(WorkItem.sequence.asc())
            .limit(2)
        ).all()
    )


def _matching_native_work(db: Session, task: Task) -> WorkItem | None:
    relation_exists = exists(
        select(TaskWorkRelation.task_id).where(TaskWorkRelation.work_id == WorkItem.id)
    )
    epic_root_exists = exists(
        select(EpicWorkRelation.epic_id).where(EpicWorkRelation.root_work_id == WorkItem.id)
    )
    rows = list(
        db.scalars(
            select(WorkItem)
            .where(
                WorkItem.project_id == task.project_id,
                WorkItem.linked_task_id.is_(None),
                WorkItem.linked_epic_id.is_(None),
                WorkItem.status.in_(("active", "blocked")),
                WorkItem.goal == task.goal,
                ~relation_exists,
                ~epic_root_exists,
            )
            .order_by(WorkItem.updated_at.desc(), WorkItem.sequence.desc())
            .limit(2)
        ).all()
    )
    return rows[0] if len(rows) == 1 else None


def ensure_task_work(
    db: Session,
    project: Project,
    task: Task,
    *,
    create_if_missing: bool,
    preferred_work_key: str | None = None,
) -> TaskWorkBinding | None:
    existing = task_work_binding(db, task)
    if existing is not None:
        if preferred_work_key is not None:
            preferred = work_for_key(db, project, preferred_work_key)
            if preferred.id != existing.work.id:
                raise RuntimeError("TASK_WORK_RELATION_CONFLICT: Task already belongs to another Work")
        return existing

    if preferred_work_key is not None:
        preferred = work_for_key(db, project, preferred_work_key)
        return bind_task_work(db, project, task, preferred, role="outcome")

    if _task_is_epic_control(db, task):
        return None

    legacy = _legacy_task_candidates(db, task)
    if len(legacy) > 1:
        raise RuntimeError(
            "AMBIGUOUS_LEGACY_TASK_WORK: multiple Work rows reference this Task; explicit Work selection is required"
        )
    if len(legacy) == 1:
        return bind_task_work(db, project, task, legacy[0], role="outcome")
    if not create_if_missing:
        return None

    work = _matching_native_work(db, task)
    if work is None:
        work = create_control_plane_work(
            db,
            project,
            goal=task.goal,
            kind="research" if task.workflow_profile == "analysis_only" else "change",
        )
    return bind_task_work(db, project, task, work, role="outcome")


def epic_root_work(db: Session, epic: Epic) -> WorkItem | None:
    relation = db.get(EpicWorkRelation, epic.id)
    if relation is None:
        return None
    work = db.get(WorkItem, relation.root_work_id)
    if work is None or work.project_id != epic.project_id:
        raise RuntimeError("EPIC_WORK_RELATION_CORRUPT: root Work is missing or cross-project")
    return work


def bind_epic_root_work(
    db: Session,
    project: Project,
    epic: Epic,
    work: WorkItem,
) -> WorkItem:
    if epic.project_id != project.id or work.project_id != project.id:
        raise ValueError("Epic and root Work must belong to the same project")
    existing = db.get(EpicWorkRelation, epic.id)
    if existing is not None:
        if existing.root_work_id != work.id:
            raise RuntimeError("EPIC_WORK_RELATION_CONFLICT: Epic already has another root Work")
        return work
    other_epic = db.scalar(
        select(EpicWorkRelation.epic_id)
        .where(EpicWorkRelation.root_work_id == work.id)
        .limit(1)
    )
    if other_epic is not None:
        raise RuntimeError("WORK_ALREADY_EPIC_ROOT: Work is already the root of another Epic")
    hierarchy = db.get(WorkHierarchy, work.id)
    if hierarchy is not None and (
        hierarchy.parent_work_id is not None or hierarchy.root_work_id != work.id
    ):
        raise RuntimeError("EPIC_ROOT_MUST_BE_ROOT_WORK: child Work cannot become an Epic root")
    _ensure_hierarchy(db, work, parent_work_id=None, root_work_id=work.id)
    db.add(EpicWorkRelation(epic_id=epic.id, root_work_id=work.id))
    if work.linked_epic_id not in {None, epic.id}:
        raise RuntimeError("LEGACY_EPIC_LINK_CONFLICT: Work is linked to another Epic")
    work.linked_epic_id = epic.id
    work.updated_at = utcnow()
    db.flush()
    return work


def ensure_epic_root_work(
    db: Session,
    project: Project,
    epic: Epic,
    *,
    create_if_missing: bool,
    preferred_work_key: str | None = None,
) -> WorkItem | None:
    existing = epic_root_work(db, epic)
    if existing is not None:
        if preferred_work_key is not None:
            preferred = work_for_key(db, project, preferred_work_key)
            if preferred.id != existing.id:
                raise RuntimeError("EPIC_WORK_RELATION_CONFLICT: Epic already has another root Work")
        return existing
    if preferred_work_key is not None:
        return bind_epic_root_work(db, project, epic, work_for_key(db, project, preferred_work_key))
    if not create_if_missing:
        return None

    legacy_count = int(
        db.scalar(
            select(func.count()).select_from(WorkItem).where(
                WorkItem.project_id == project.id,
                WorkItem.linked_epic_id == epic.id,
            )
        )
        or 0
    )
    if legacy_count:
        raise RuntimeError(
            "LEGACY_EPIC_ROOT_UNRESOLVED: linked_epic_id does not prove root ownership; explicit Work selection is required"
        )
    work = create_control_plane_work(
        db,
        project,
        goal=epic.title,
        kind="planning",
        linked_epic_id=epic.id,
    )
    return bind_epic_root_work(db, project, epic, work)


def plan_item_work(db: Session, item: EpicPlanItem) -> WorkItem | None:
    relation = db.get(EpicPlanWorkRelation, item.id)
    if relation is None:
        return None
    work = db.get(WorkItem, relation.work_id)
    if work is None:
        raise RuntimeError("EPIC_PLAN_WORK_RELATION_CORRUPT: child Work is missing")
    return work


def ensure_epic_plan_work(
    db: Session,
    project: Project,
    epic: Epic,
    item: EpicPlanItem,
) -> WorkItem:
    if item.epic_id != epic.id or epic.project_id != project.id:
        raise ValueError("Epic plan item is outside the selected project/Epic")
    if item.kind != "work":
        raise ValueError("only implementation plan items own child Work")
    existing = plan_item_work(db, item)
    if existing is not None:
        return existing
    root = ensure_epic_root_work(db, project, epic, create_if_missing=True)
    if root is None:
        raise RuntimeError("Epic root Work is unavailable")
    work = create_control_plane_work(
        db,
        project,
        goal=item.goal,
        kind="change",
        linked_epic_id=epic.id,
        parent_work=root,
        root_work=root,
    )
    db.add(EpicPlanWorkRelation(plan_item_id=item.id, work_id=work.id))
    db.flush()
    return work


def bind_epic_control_task(
    db: Session,
    project: Project,
    epic: Epic,
    task: Task,
) -> TaskWorkBinding:
    root = ensure_epic_root_work(db, project, epic, create_if_missing=True)
    if root is None:
        raise RuntimeError("Epic root Work is unavailable")
    return bind_task_work(db, project, task, root, role="epic_control")


def complete_epic_root_work(
    db: Session,
    project: Project,
    epic: Epic,
    *,
    summary: str,
) -> WorkItem | None:
    work = epic_root_work(db, epic)
    if work is None or work.status not in {"active", "blocked"}:
        return work
    now = utcnow()
    work.status = "completed"
    work.result_summary = str(summary)[:4000]
    work.updated_at = now
    work.last_milestone_at = now
    work.completed_at = now
    append_contextual_event(
        db,
        event_type="WorkCompleted",
        project=project,
        aggregate_type="work",
        aggregate_id=str(work.id),
        work=work,
        epic_id=epic.id,
        payload={"status": "completed", "summary": work.result_summary},
        importance="high",
    )
    db.flush()
    return work


def canonical_links_for_work(db: Session, work: WorkItem) -> dict[str, object]:
    tasks = list(
        db.scalars(
            select(TaskWorkRelation.task_id)
            .where(TaskWorkRelation.work_id == work.id)
            .order_by(TaskWorkRelation.created_at.asc())
        ).all()
    )
    epic = db.scalar(
        select(EpicWorkRelation.epic_id).where(EpicWorkRelation.root_work_id == work.id).limit(1)
    )
    hierarchy = db.get(WorkHierarchy, work.id)
    plan_item = db.scalar(
        select(EpicPlanWorkRelation.plan_item_id)
        .where(EpicPlanWorkRelation.work_id == work.id)
        .limit(1)
    )
    return {
        "task_ids": [str(item) for item in tasks],
        "epic_root_id": str(epic) if epic is not None else None,
        "parent_work_id": str(hierarchy.parent_work_id) if hierarchy and hierarchy.parent_work_id else None,
        "root_work_id": str(hierarchy.root_work_id) if hierarchy else None,
        "epic_plan_item_id": str(plan_item) if plan_item is not None else None,
    }
