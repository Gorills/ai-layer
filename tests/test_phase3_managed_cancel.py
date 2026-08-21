from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.application.action_engine import continue_action, current_action, finish_action
from ai_layer.db.base import Base
from ai_layer.db.models import Project, Task
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import TaskWorkRelation
from ai_layer.work.service import begin_work


def _init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "AI Layer Tests"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)


def test_managed_block_cancel_requires_done_before_work_closure(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _init_git(root)

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="phase3-managed-cancel",
            root_path=str(root),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
            project_intelligence={"legacy": {"level": "low", "score": 0, "signals": []}},
        )
        db.add(project)
        db.commit()
        work, _run = begin_work(db, project, goal="Managed work that becomes blocked")
        db.commit()

        native = current_action(db, project, work)["next_action"]
        managed = continue_action(
            db,
            action_token=native["action_token"],
            report={
                "kind": "assurance_request",
                "summary": "Require reviewed assurance",
                "outcome": "escalate",
            },
        )["next_action"]
        assert managed["kind"] == "run_worker"

        decision = continue_action(
            db,
            action_token=managed["action_token"],
            report={
                "kind": "worker_result",
                "summary": "Implementation cannot proceed safely",
                "checks": ["dependency check"],
                "outcome": "blocked",
            },
        )["next_action"]
        assert decision["kind"] == "human_decision"

        done = continue_action(
            db,
            action_token=decision["action_token"],
            report={
                "kind": "human_choice",
                "summary": "Cancel managed assurance",
                "selection": "cancel",
            },
        )["next_action"]
        assert done["kind"] == "done"

        relation = db.query(TaskWorkRelation).filter_by(work_id=work.id, role="outcome").one()
        task = db.get(Task, relation.task_id)
        assert task is not None and task.status == "cancelled"

        finished = finish_action(
            db,
            action_token=done["action_token"],
            summary="Cancelled after managed blocker",
            status="cancelled",
            map_disposition={"status": "not_applicable", "reason": "No navigation change"},
        )
        assert finished["next_action"]["action_token"] is None
        refreshed = db.get(WorkItem, work.id)
        assert refreshed is not None and refreshed.status == "abandoned"
