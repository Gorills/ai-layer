from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application.managed_work import sync_task_backing_work
from ai_layer.db.base import Base
from ai_layer.db.models import Project, Task
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import TaskWorkRelation
from ai_layer.tasks import service as tasks
from ai_layer.work.service import begin_work


def test_task_block_resume_cancel_preserves_canonical_work(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="phase2-lifecycle",
            root_path=str(root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        work, _run = begin_work(db, project, goal="Preserve identity")
        db.commit()

        created = tasks.create_task(
            db,
            project,
            goal="Preserve identity",
            acceptance_criteria=[],
            constraints=[],
        )
        task_id = UUID(created["id"])
        sync_task_backing_work(
            db,
            project,
            created,
            create_if_missing=True,
            preferred_work_key=f"W-{work.sequence:04d}",
        )
        relation = db.get(TaskWorkRelation, task_id)
        assert relation is not None and relation.work_id == work.id
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1

        task = db.get(Task, task_id)
        assert task is not None
        task.status = "blocked"
        task.blocked_reason = "Waiting on dependency"
        db.commit()
        blocked = sync_task_backing_work(db, project, {"id": created["id"]})
        assert blocked is not None and blocked["status"] == "blocked"

        task = db.get(Task, task_id)
        assert task is not None
        task.status = "active"
        task.blocked_reason = ""
        db.commit()
        resumed = sync_task_backing_work(db, project, {"id": created["id"]})
        assert resumed is not None and resumed["status"] == "active"

        task = db.get(Task, task_id)
        assert task is not None
        task.status = "cancelled"
        task.blocked_reason = "Cancelled by user"
        db.commit()
        cancelled = sync_task_backing_work(db, project, {"id": created["id"]})
        assert cancelled is not None and cancelled["status"] == "abandoned"
        assert cancelled["id"] == str(work.id)
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1
        relation = db.get(TaskWorkRelation, task_id)
        assert relation is not None and relation.work_id == work.id
