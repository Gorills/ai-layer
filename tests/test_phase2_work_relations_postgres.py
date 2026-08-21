from __future__ import annotations

import os
from pathlib import Path
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_layer.db.epic_models import Epic
from ai_layer.db.models import Project, Task
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import EpicWorkRelation, TaskWorkRelation

POSTGRES_URL = os.getenv("AI_LAYER_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.postgres


def _engine():
    if not POSTGRES_URL:
        pytest.skip("AI_LAYER_TEST_POSTGRES_URL is not configured")
    return create_engine(POSTGRES_URL, pool_pre_ping=True)


def _project(tmp_path: Path) -> tuple[object, Path]:
    engine = _engine()
    root = tmp_path / f"phase2-pg-{uuid4().hex}"
    root.mkdir()
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name=f"phase2-{uuid4().hex}",
            root_path=str(root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        return project.id, root


def test_postgres_task_cannot_belong_to_two_work_outcomes(tmp_path: Path) -> None:
    engine = _engine()
    project_id, _root = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        task = Task(project_id=project_id, sequence=1, goal="One owner", status="completed")
        work_a = WorkItem(project_id=project_id, sequence=1, goal="A")
        work_b = WorkItem(project_id=project_id, sequence=2, goal="B")
        db.add_all([task, work_a, work_b])
        db.commit()
        task_id = task.id
        work_ids = (work_a.id, work_b.id)

    barrier = Barrier(2)
    results: list[str] = []

    def bind(work_id) -> None:
        with Session(engine) as db:
            db.add(TaskWorkRelation(task_id=task_id, work_id=work_id, role="outcome"))
            barrier.wait()
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [Thread(target=bind, args=(work_id,)) for work_id in work_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["committed", "rejected"]
    with Session(engine) as db:
        relation = db.get(TaskWorkRelation, task_id)
        assert relation is not None
        assert relation.work_id in set(work_ids)


def test_postgres_one_work_cannot_be_root_of_two_epics(tmp_path: Path) -> None:
    engine = _engine()
    project_id, _root = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        root_work = WorkItem(project_id=project_id, sequence=1, goal="Root", kind="planning")
        epic_a = Epic(project_id=project_id, sequence=1, title="Epic A")
        epic_b = Epic(project_id=project_id, sequence=2, title="Epic B")
        db.add_all([root_work, epic_a, epic_b])
        db.commit()
        root_work_id = root_work.id
        epic_ids = (epic_a.id, epic_b.id)

    barrier = Barrier(2)
    results: list[str] = []

    def bind(epic_id) -> None:
        with Session(engine) as db:
            db.add(EpicWorkRelation(epic_id=epic_id, root_work_id=root_work_id))
            barrier.wait()
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [Thread(target=bind, args=(epic_id,)) for epic_id in epic_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["committed", "rejected"]
    with Session(engine) as db:
        rows = list(
            db.scalars(
                select(EpicWorkRelation).where(EpicWorkRelation.root_work_id == root_work_id)
            ).all()
        )
        assert len(rows) == 1
        assert rows[0].epic_id in set(epic_ids)
