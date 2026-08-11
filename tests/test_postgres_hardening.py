from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, RepositorySnapshot, Task, TaskStage
from ai_layer.tasks import service as tasks

POSTGRES_URL = os.getenv("AI_LAYER_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.postgres


def _engine():
    if not POSTGRES_URL:
        pytest.skip("AI_LAYER_TEST_POSTGRES_URL is not configured")
    return create_engine(POSTGRES_URL, pool_pre_ping=True)


def _project(tmp_path: Path) -> tuple[UUID, Path]:
    engine = _engine()
    root = tmp_path / f"pg-project-{uuid4().hex}"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name=f"pg-{uuid4().hex}",
            root_path=str(root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        return project.id, root


def test_postgres_constraint_is_authoritative_for_one_open_task(tmp_path: Path) -> None:
    engine = _engine()
    project_id, _ = _project(tmp_path)
    barrier = Barrier(2)
    results: list[str] = []

    def writer(sequence: int) -> None:
        with Session(engine) as db:
            db.add(
                Task(
                    project_id=project_id,
                    sequence=sequence,
                    goal=f"task-{sequence}",
                    status="active",
                )
            )
            barrier.wait()
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [Thread(target=writer, args=(1,)), Thread(target=writer, args=(2,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert sorted(results) == ["committed", "rejected"]
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id))
            == 1
        )


def test_postgres_create_task_uses_db_lock_without_filesystem_lock(
    tmp_path: Path, monkeypatch
) -> None:
    engine = _engine()
    project_id, _ = _project(tmp_path)
    import ai_layer.tasks.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "directory_lock", lambda *args, **kwargs: nullcontext())
    barrier = Barrier(2)
    results: list[str] = []

    def create(goal: str) -> None:
        with Session(engine, expire_on_commit=False) as db:
            project = db.get(Project, project_id)
            assert project is not None
            barrier.wait()
            try:
                tasks.create_task(db, project, goal=goal, acceptance_criteria=[], constraints=[])
            except (RuntimeError, IntegrityError):
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [Thread(target=create, args=("A",)), Thread(target=create, args=("B",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == ["committed", "rejected"]


def test_postgres_concurrent_delegation_has_one_authoritative_worker(
    tmp_path: Path, monkeypatch
) -> None:
    engine = _engine()
    project_id, _ = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        project = db.get(Project, project_id)
        assert project is not None
        tasks.create_task(db, project, goal="Delegate once", acceptance_criteria=[], constraints=[])

    import ai_layer.tasks.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "directory_lock", lambda *args, **kwargs: nullcontext())
    barrier = Barrier(2)
    results: list[str] = []

    def delegate(worker_id: str) -> None:
        with Session(engine, expire_on_commit=False) as db:
            project = db.get(Project, project_id)
            assert project is not None
            barrier.wait()
            try:
                tasks.delegate_current_stage(db, project, worker_id=worker_id)
            except RuntimeError:
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [
        Thread(target=delegate, args=("worker-a",)),
        Thread(target=delegate, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == ["committed", "rejected"]
    with Session(engine) as db:
        task = db.scalar(select(Task).where(Task.project_id == project_id))
        assert task is not None
        stage = db.scalar(
            select(TaskStage).where(TaskStage.task_id == task.id, TaskStage.status == "active")
        )
        assert stage is not None and stage.worker_id in {"worker-a", "worker-b"}


def test_postgres_concurrent_stage_completion_has_one_authoritative_result(
    tmp_path: Path, monkeypatch
) -> None:
    engine = _engine()
    project_id, root = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        project = db.get(Project, project_id)
        assert project is not None
        tasks.create_task(
            db,
            project,
            goal="Change value",
            acceptance_criteria=[],
            constraints=[],
            workflow="standard",
        )
        delegated = tasks.delegate_current_stage(db, project, worker_id="worker-one")
        stage_id = delegated["active_stage"]["id"]
    (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    import ai_layer.tasks.completion as completion

    monkeypatch.setattr(completion, "directory_lock", lambda *args, **kwargs: nullcontext())
    barrier = Barrier(2)
    results: list[str] = []

    def complete() -> None:
        with Session(engine, expire_on_commit=False) as db:
            project = db.get(Project, project_id)
            assert project is not None
            barrier.wait()
            try:
                tasks.complete_stage(
                    db,
                    project,
                    stage_id=stage_id,
                    worker_id="worker-one",
                    summary="Completed once.",
                    checks=["manual check"],
                )
            except RuntimeError:
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [Thread(target=complete), Thread(target=complete)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == ["committed", "rejected"]
    with Session(engine) as db:
        task = db.scalar(select(Task).where(Task.project_id == project_id))
        assert task is not None
        stages = db.scalars(
            select(TaskStage).where(TaskStage.task_id == task.id).order_by(TaskStage.ordinal)
        ).all()
        assert [stage.kind for stage in stages] == ["implement", "review"]
        assert sum(stage.status == "active" for stage in stages) == 1


def test_postgres_concurrent_worker_recovery_has_one_authoritative_result(
    tmp_path: Path, monkeypatch
) -> None:
    engine = _engine()
    project_id, _ = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        project = db.get(Project, project_id)
        assert project is not None
        tasks.create_task(db, project, goal="Recover once", acceptance_criteria=[], constraints=[])
        tasks.delegate_current_stage(db, project, worker_id="lost-worker")

    import ai_layer.tasks.worker_leases as worker_leases

    monkeypatch.setattr(worker_leases, "directory_lock", lambda *args, **kwargs: nullcontext())
    barrier = Barrier(2)
    results: list[str] = []

    def recover() -> None:
        with Session(engine, expire_on_commit=False) as db:
            project = db.get(Project, project_id)
            assert project is not None
            barrier.wait()
            try:
                worker_leases.recover_disconnected_worker(
                    db, project, reason="simulated lost worker"
                )
            except RuntimeError:
                db.rollback()
                results.append("rejected")
            else:
                results.append("committed")

    threads = [Thread(target=recover), Thread(target=recover)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == ["committed", "rejected"]
    with Session(engine) as db:
        task = db.scalar(select(Task).where(Task.project_id == project_id))
        assert task is not None
        stages = db.scalars(
            select(TaskStage).where(TaskStage.task_id == task.id).order_by(TaskStage.ordinal)
        ).all()
        assert len(stages) == 2
        assert stages[0].status == "invalid"
        assert stages[1].status == "active"
        assert stages[1].worker_id == ""


def test_postgres_project_delete_cascades_task_and_snapshot_graph(tmp_path: Path) -> None:
    engine = _engine()
    project_id, _ = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        project = db.get(Project, project_id)
        assert project is not None
        created = tasks.create_task(
            db, project, goal="Disposable project", acceptance_criteria=[], constraints=[]
        )
        task_id = UUID(created["id"])
        task = db.get(Task, task_id)
        assert task is not None and task.baseline_snapshot_id is not None
        snapshot_id = task.baseline_snapshot_id
        db.execute(delete(Project).where(Project.id == project_id))
        db.commit()
    with Session(engine) as db:
        assert db.get(Task, task_id) is None
        assert db.get(RepositorySnapshot, snapshot_id) is None


def test_postgres_snapshot_survives_new_session_and_missing_local_materialization(
    tmp_path: Path,
) -> None:
    engine = _engine()
    project_id, _ = _project(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        project = db.get(Project, project_id)
        assert project is not None
        created = tasks.create_task(
            db, project, goal="Durable state", acceptance_criteria=[], constraints=[]
        )
        task_id = UUID(created["id"])
    with Session(engine, expire_on_commit=False) as db:
        task = db.get(Task, task_id)
        assert task is not None and task.baseline_snapshot_id is not None
        snapshot = db.get(RepositorySnapshot, task.baseline_snapshot_id)
        assert snapshot is not None
        assert snapshot.digest == task.baseline_digest
        stage = db.scalar(
            select(TaskStage).where(TaskStage.task_id == task.id, TaskStage.status == "active")
        )
        assert stage is not None and stage.start_snapshot_id is not None
