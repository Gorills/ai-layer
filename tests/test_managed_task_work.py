from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application.managed_work import sync_task_backing_work
from ai_layer.db.base import Base
from ai_layer.db.models import Project, Task, utcnow
from ai_layer.db.work_models import AgentRun, RuntimeEventContext, WorkItem
from ai_layer.tasks import service as tasks
from ai_layer.work.service import begin_work


def _project(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="managed-work",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()
    return db, project, root


def test_managed_task_gets_backing_work_without_fake_agent_run(tmp_path: Path):
    db, project, _root = _project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Run this through the standard Task protocol",
            acceptance_criteria=[],
            constraints=[],
        )
        work = sync_task_backing_work(
            db, project, {"task": {"id": created["id"]}}, create_if_missing=True
        )
        assert work is not None
        assert work["key"] == "W-0001"
        assert work["linked_task_id"] == created["id"]
        assert work["observability_coverage"] == "control_plane_only"
        assert work["live"] is False
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0

        contexts = list(
            db.scalars(
                select(RuntimeEventContext).where(
                    RuntimeEventContext.task_id == UUID(created["id"])
                )
            ).all()
        )
        assert contexts
        assert all(item.work_id == UUID(work["id"]) for item in contexts)
    finally:
        db.close()


def test_task_create_repairs_matching_prior_work_and_terminal_state_closes_it(tmp_path: Path):
    db, project, root = _project(tmp_path)
    try:
        original, _run = begin_work(db, project, goal="Run this through the standard Task protocol")
        db.commit()
        created = tasks.create_task(
            db,
            project,
            goal="Run this through the standard Task protocol",
            acceptance_criteria=[],
            constraints=[],
        )
        linked = sync_task_backing_work(db, project, created, create_if_missing=True)
        assert linked is not None
        assert linked["key"] == f"W-{original.sequence:04d}"
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1

        task = db.scalar(select(Task).where(Task.id == UUID(created["id"])))
        assert task is not None
        task.status = "completed"
        task.completion_summary = "Managed protocol completed."
        task.final_changes = {"modified": ["app.py"]}
        task.completed_at = utcnow()
        db.commit()

        completed = sync_task_backing_work(db, project, {"id": created["id"]})
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["changed_paths"] == ["app.py"]
        assert completed["map_disposition"]["status"] == "deferred"
        assert (root / "app.py").exists()
    finally:
        db.close()
