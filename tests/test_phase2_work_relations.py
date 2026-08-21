from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application.epic_common import append_epic_event
from ai_layer.application.managed_work import sync_task_backing_work
from ai_layer.application.work_relations import (
    bind_epic_control_task,
    bind_task_work,
    ensure_epic_plan_work,
    ensure_epic_root_work,
)
from ai_layer.db.base import Base
from ai_layer.db.epic_models import Epic, EpicPlanItem, EpicSpecVersion
from ai_layer.db.models import Project, Task
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import (
    EpicPlanWorkRelation,
    EpicWorkRelation,
    TaskWorkRelation,
    WorkHierarchy,
)
from ai_layer.tasks import service as tasks
from ai_layer.work.service import begin_work


def _project(tmp_path: Path) -> tuple[Session, Project, Path]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="phase2",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()
    return db, project, root


def _epic(db: Session, project: Project, *, title: str = "Ship the feature") -> Epic:
    epic = Epic(project_id=project.id, sequence=1, title=title)
    db.add(epic)
    db.flush()
    db.add(
        EpicSpecVersion(
            epic_id=epic.id,
            version=1,
            content="# Goal\nShip the feature.\n\n# Acceptance Criteria\n- It works.\n",
            source="draft",
        )
    )
    db.flush()
    return epic


def test_native_to_task_promotion_preserves_one_work_identity(tmp_path: Path) -> None:
    db, project, _root = _project(tmp_path)
    try:
        native, _run = begin_work(db, project, goal="Change request routing")
        db.commit()
        created = tasks.create_task(
            db,
            project,
            goal="Change request routing",
            acceptance_criteria=[],
            constraints=[],
        )

        rendered = sync_task_backing_work(
            db,
            project,
            created,
            create_if_missing=True,
            preferred_work_key=f"W-{native.sequence:04d}",
        )

        assert rendered is not None
        assert rendered["id"] == str(native.id)
        assert rendered["key"] == "W-0001"
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1
        relation = db.get(TaskWorkRelation, UUID(created["id"]))
        assert relation is not None
        assert relation.work_id == native.id
        assert relation.role == "outcome"
        db.refresh(native)
        assert str(native.linked_task_id) == created["id"]
    finally:
        db.close()


def test_ambiguous_legacy_task_links_never_choose_a_winner(tmp_path: Path) -> None:
    db, project, _root = _project(tmp_path)
    try:
        task = Task(project_id=project.id, sequence=1, goal="Legacy task", status="completed")
        db.add(task)
        db.flush()
        for sequence in (1, 2):
            db.add(
                WorkItem(
                    project_id=project.id,
                    sequence=sequence,
                    goal="Legacy task",
                    linked_task_id=task.id,
                )
            )
        db.commit()

        with pytest.raises(RuntimeError, match="AMBIGUOUS_LEGACY_TASK_WORK"):
            sync_task_backing_work(
                db,
                project,
                {"id": str(task.id)},
                create_if_missing=True,
            )
        db.rollback()
        assert db.get(TaskWorkRelation, task.id) is None
    finally:
        db.close()


def test_epic_root_and_plan_item_have_distinct_canonical_work(tmp_path: Path) -> None:
    db, project, _root = _project(tmp_path)
    try:
        epic = _epic(db, project)
        root = ensure_epic_root_work(db, project, epic, create_if_missing=True)
        assert root is not None
        item = EpicPlanItem(
            epic_id=epic.id,
            ordinal=1,
            kind="work",
            title="Implement routing",
            goal="Implement routing",
            status="pending",
            spec_version=1,
            plan_version=1,
        )
        db.add(item)
        db.flush()

        child = ensure_epic_plan_work(db, project, epic, item)
        task = Task(project_id=project.id, sequence=1, goal=item.goal, status="completed")
        db.add(task)
        db.flush()
        binding = bind_task_work(db, project, task, child, role="outcome")
        db.commit()

        assert root.id != child.id
        assert db.get(EpicWorkRelation, epic.id).root_work_id == root.id
        assert db.get(EpicPlanWorkRelation, item.id).work_id == child.id
        hierarchy = db.get(WorkHierarchy, child.id)
        assert hierarchy is not None
        assert hierarchy.parent_work_id == root.id
        assert hierarchy.root_work_id == root.id
        assert binding.work.id == child.id
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 2
    finally:
        db.close()


def test_epic_control_task_never_closes_root_work(tmp_path: Path) -> None:
    db, project, _root = _project(tmp_path)
    try:
        epic = _epic(db, project)
        root = ensure_epic_root_work(db, project, epic, create_if_missing=True)
        assert root is not None
        task = Task(
            project_id=project.id,
            sequence=1,
            goal="Epic final closure",
            status="completed",
            completion_summary="Control task completed.",
        )
        db.add(task)
        db.flush()
        bind_epic_control_task(db, project, epic, task)
        db.commit()

        rendered = sync_task_backing_work(
            db,
            project,
            {"id": str(task.id)},
            create_if_missing=True,
        )

        assert rendered is not None
        assert rendered["id"] == str(root.id)
        db.refresh(root)
        assert root.status == "active"
        relation = db.get(TaskWorkRelation, task.id)
        assert relation is not None and relation.role == "epic_control"
    finally:
        db.close()


def test_epic_completed_event_closes_only_the_root_outcome(tmp_path: Path) -> None:
    db, project, _root = _project(tmp_path)
    try:
        epic = _epic(db, project)
        root = ensure_epic_root_work(db, project, epic, create_if_missing=True)
        assert root is not None
        item = EpicPlanItem(
            epic_id=epic.id,
            ordinal=1,
            kind="work",
            title="Child",
            goal="Child",
            status="completed",
            spec_version=1,
            plan_version=1,
        )
        db.add(item)
        db.flush()
        child = ensure_epic_plan_work(db, project, epic, item)
        child.status = "completed"
        db.flush()

        append_epic_event(db, project, epic, "EpicCompleted", {"final_task": "T-0002"})
        db.commit()

        db.refresh(root)
        db.refresh(child)
        assert root.status == "completed"
        assert root.completed_at is not None
        assert child.status == "completed"
    finally:
        db.close()
