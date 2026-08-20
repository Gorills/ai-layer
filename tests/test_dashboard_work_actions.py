from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.application import work as work_uc
from ai_layer.dashboard import web as dashboard_web
from ai_layer.db.base import Base
from ai_layer.db.models import CommandReceipt, Project, RuntimeEvent
from ai_layer.db.work_models import AgentRun, WorkItem
from ai_layer.domain.security import LOCAL_TRUSTED_ACTOR

ROOT = Path(__file__).resolve().parents[1]
WORK_JS = ROOT / "src/ai_layer/dashboard/static/js/views/work.js"


@contextmanager
def _bound_work_db(tmp_path: Path):
    import ai_layer.db.session as db_session

    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard-work.db'}")
    root = (tmp_path / "project").resolve()
    root.mkdir()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Project(
                name="Dashboard Work",
                root_path=str(root),
                languages={},
                dependencies={},
                architecture_summary="",
            )
        )
        db.commit()

    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield engine, root
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session
        engine.dispose()


def _dashboard_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_web.router)
    return app


def test_dashboard_complete_work_is_same_origin_idempotent_and_attributed(
    monkeypatch, tmp_path: Path
) -> None:
    with _bound_work_db(tmp_path) as (engine, root):
        started = work_uc.begin(
            root,
            goal="Work was already finished in the host",
            kind="change",
            idempotency_key="dashboard-action-begin",
        )
        assert started["work"]["key"] == "W-0001"

        entry = {"root": str(root), "project_id": "alpha/beta", "name": "Dashboard Work"}
        monkeypatch.setattr(
            dashboard_web,
            "entry_for_key",
            lambda key: entry if key == "alpha/beta" else None,
        )
        client = TestClient(_dashboard_app(), base_url="http://127.0.0.1:8765")
        action = "/dashboard/actions/work/complete?project_key=alpha%2Fbeta&work_key=W-0001"

        missing_origin = client.post(action, follow_redirects=False)
        assert missing_origin.status_code == 403

        rejected = client.post(
            action,
            headers={"Origin": "https://example.com"},
            follow_redirects=False,
        )
        assert rejected.status_code == 403
        with Session(engine) as db:
            work = db.scalar(select(WorkItem))
            assert work is not None
            assert work.status == "active"

        for _ in range(2):
            response = client.post(
                action,
                headers={"Origin": "http://127.0.0.1:8765"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/dashboard#/work/alpha%2Fbeta/W-0001"

        with Session(engine) as db:
            work = db.scalar(select(WorkItem))
            assert work is not None
            assert work.status == "completed"
            assert work.completed_at is not None

            runs = list(db.scalars(select(AgentRun).where(AgentRun.work_id == work.id)).all())
            assert len(runs) == 1
            assert runs[0].status == "completed"
            assert runs[0].ended_at is not None

            events = list(
                db.scalars(
                    select(RuntimeEvent).where(RuntimeEvent.event_type == "WorkCompleted")
                ).all()
            )
            assert len(events) == 1
            event = events[0]
            assert event.actor_id == LOCAL_TRUSTED_ACTOR.actor_id
            assert event.actor_kind == LOCAL_TRUSTED_ACTOR.kind
            assert event.interface == "dashboard"
            assert event.command_id is not None
            assert event.command_id.startswith("dashboard-work-complete:")

            receipts = list(
                db.scalars(
                    select(CommandReceipt).where(CommandReceipt.command_name == "work_complete")
                ).all()
            )
            assert len(receipts) == 1
            assert receipts[0].actor_id == LOCAL_TRUSTED_ACTOR.actor_id
            assert receipts[0].command_id == event.command_id


def test_work_detail_completion_action_is_plain_post_non_live_only(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        raise AssertionError("node is required to execute Dashboard Work action helpers")
    source = WORK_JS.read_text(encoding="utf-8")
    assert "${workCompletionAction(project, work)}" in source

    script = tmp_path / "work_action_check.mjs"
    work_url = WORK_JS.resolve().as_uri()
    script.write_text(
        "\n".join(
            [
                f"import {{ workCompletionAction }} from '{work_url}';",
                "const project = { key: 'alpha/beta' };",
                "const waiting = { key: 'W-0001', status: 'awaiting_feedback', live: false };",
                "const stale = { key: 'W-0002', status: 'active', live: false };",
                "const live = { key: 'W-0003', status: 'active', live: true };",
                "const completed = { key: 'W-0004', status: 'completed', live: false };",
                "const waitingHtml = workCompletionAction(project, waiting);",
                "if (!waitingHtml.includes('method=\"post\"')) throw new Error('missing post form');",
                "if (!waitingHtml.includes('project_key=alpha%2Fbeta&amp;work_key=W-0001')) throw new Error('query action');",
                "if (!waitingHtml.includes('Завершить Work')) throw new Error('label');",
                "if (!workCompletionAction(project, stale)) throw new Error('stale action missing');",
                "if (workCompletionAction(project, live) !== '') throw new Error('live action leaked');",
                "if (workCompletionAction(project, completed) !== '') throw new Error('terminal action leaked');",
                "if (waitingHtml.includes('target=')) throw new Error('mutation must stay same-origin');",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", script],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
