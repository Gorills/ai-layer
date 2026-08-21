from __future__ import annotations

import os
from pathlib import Path
from threading import Barrier, Lock, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application.action_engine import ActionProtocolError, continue_action, current_action
from ai_layer.db.action_models import WorkActionSubmission
from ai_layer.db.models import Project, Task, TaskStage
from ai_layer.db.work_relation_models import TaskWorkRelation
from ai_layer.work.service import begin_work

POSTGRES_URL = os.getenv("AI_LAYER_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.postgres


def _engine():
    if not POSTGRES_URL:
        pytest.skip("AI_LAYER_TEST_POSTGRES_URL is not configured")
    return create_engine(POSTGRES_URL, pool_pre_ping=True)


def test_concurrent_same_worker_result_advances_managed_stage_once(tmp_path: Path) -> None:
    engine = _engine()
    root = tmp_path / f"phase3-pg-{uuid4().hex}"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name=f"phase3-{uuid4().hex}",
            root_path=str(root),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
            project_intelligence={"legacy": {"level": "low", "score": 0, "signals": []}},
        )
        db.add(project)
        db.commit()
        work, _run = begin_work(db, project, goal="Concurrent managed transition")
        db.commit()
        native = current_action(db, project, work)
        promoted = continue_action(
            db,
            action_token=native["next_action"]["action_token"],
            report={
                "kind": "assurance_request",
                "summary": "Use STANDARD assurance",
                "outcome": "escalate",
            },
        )
        implement_token = promoted["next_action"]["action_token"]
        work_id = work.id

    (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    barrier = Barrier(2)
    guard = Lock()
    outcomes: list[str] = []
    report = {
        "kind": "worker_result",
        "summary": "Concurrent delivery of one real worker result",
        "checks": ["focused check"],
        "outcome": "done",
    }

    def submit() -> None:
        with Session(engine, expire_on_commit=False) as db:
            barrier.wait()
            try:
                response = continue_action(db, action_token=implement_token, report=report)
                outcome = f"ok:{response['next_action']['kind']}"
            except ActionProtocolError as exc:
                outcome = f"error:{exc.code}"
            with guard:
                outcomes.append(outcome)

    threads = [Thread(target=submit), Thread(target=submit)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert len(outcomes) == 2
    assert any(item == "ok:run_worker" for item in outcomes)
    assert set(outcomes) <= {"ok:run_worker", "error:ACTION_IN_PROGRESS"}

    with Session(engine, expire_on_commit=False) as db:
        task = db.scalar(
            select(Task)
            .join(TaskWorkRelation, TaskWorkRelation.task_id == Task.id)
            .where(TaskWorkRelation.work_id == work_id, TaskWorkRelation.role == "outcome")
        )
        assert task is not None
        stages = list(
            db.scalars(
                select(TaskStage).where(TaskStage.task_id == task.id).order_by(TaskStage.ordinal)
            ).all()
        )
        assert [stage.kind for stage in stages] == ["implement", "review"]
        assert stages[0].status == "completed"
        assert stages[1].status == "active"
        assert stages[1].worker_id.startswith("facade-")
        assert (
            db.scalar(
                select(func.count())
                .select_from(WorkActionSubmission)
                .where(WorkActionSubmission.action_token == implement_token)
            )
            == 1
        )
