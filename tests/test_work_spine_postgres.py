from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application import work as work_uc
from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.work_models import AgentRun, RuntimeEventContext, WorkItem

POSTGRES_URL = os.getenv("AI_LAYER_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.postgres


def _engine():
    if not POSTGRES_URL:
        pytest.skip("AI_LAYER_TEST_POSTGRES_URL is not configured")
    return create_engine(POSTGRES_URL, pool_pre_ping=True)


def test_work_lifecycle_is_parallel_idempotent_and_durably_observable(monkeypatch) -> None:
    import ai_layer.db.session as db_session

    engine = _engine()
    root = f"/tmp/work-spine-{uuid4().hex}"
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name=f"work-spine-{uuid4().hex}",
            root_path=root,
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        project_id = project.id

    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    from sqlalchemy.orm import sessionmaker

    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        first = work_uc.begin(
            root,
            goal="Inspect checkout retry flow",
            kind="diagnose",
            host="cursor",
            client="mcp",
            session_id="session-1",
            turn_id="turn-1",
            model="model-a",
            idempotency_key="work-begin-1",
        )
        repeated = work_uc.begin(
            root,
            goal="Inspect checkout retry flow",
            kind="diagnose",
            host="cursor",
            client="mcp",
            session_id="session-1",
            turn_id="turn-1",
            model="model-a",
            idempotency_key="work-begin-1",
        )
        second = work_uc.begin(
            root,
            goal="Review unrelated docs",
            kind="review",
            idempotency_key="work-begin-2",
        )
        assert first["work"]["id"] == repeated["work"]["id"]
        assert first["work"]["key"] == "W-0001"
        assert second["work"]["key"] == "W-0002"

        completed = work_uc.complete(
            root,
            work_key="W-0001",
            summary="Retry flow inspected and verified.",
            reviewed_paths=["src/orders/retry.py"],
            changed_paths=[],
            checks=[
                {"name": "pytest tests/test_orders.py", "status": "passed", "summary": "1 passed"}
            ],
            repository_delta={"changed_files": 0},
            map_disposition={
                "status": "checked_no_change",
                "scope": ["src/orders/retry.py"],
                "reason": "Existing map semantics remain accurate.",
            },
            idempotency_key="work-complete-1",
        )
        assert completed["work"]["status"] == "completed"
        assert completed["work"]["map_disposition"]["status"] == "checked_no_change"
        state = work_uc.state(root)
        assert [item["key"] for item in state["active"]] == ["W-0002"]
        assert state["recent"][0]["key"] == "W-0001"

        with Session(engine, expire_on_commit=False) as db:
            assert (
                db.scalar(select(func.count(WorkItem.id)).where(WorkItem.project_id == project_id))
                == 2
            )
            assert (
                db.scalar(
                    select(func.count(AgentRun.id))
                    .join(WorkItem)
                    .where(WorkItem.project_id == project_id)
                )
                == 2
            )
            work_started = db.scalars(
                select(RuntimeEvent).where(
                    RuntimeEvent.project_id == project_id,
                    RuntimeEvent.event_type == "WorkStarted",
                )
            ).all()
            assert len(work_started) == 2
            contexts = db.scalars(
                select(RuntimeEventContext).where(
                    RuntimeEventContext.event_id.in_([item.id for item in work_started])
                )
            ).all()
            assert len(contexts) == 2
            assert all(item.work_id is not None for item in contexts)
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session
        with Session(engine) as db:
            project = db.get(Project, project_id)
            if project is not None:
                db.delete(project)
                db.commit()
