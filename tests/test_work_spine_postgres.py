from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.application import work as work_uc
from ai_layer.application.commands import _legacy_request_hash, execute_idempotent
from ai_layer.db.models import CommandReceipt, Project, RuntimeEvent
from ai_layer.db.work_models import AgentRun, RuntimeEventContext, WorkItem
from ai_layer.domain.security import Actor, Capability
from ai_layer.projections import dashboard_activity

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

        entry = {"root": root, "project_id": "work-spine", "name": "Work Spine"}
        monkeypatch.setattr(dashboard_activity, "selected_entries", lambda _key: [entry])
        monkeypatch.setattr(dashboard_activity, "project_options", lambda: [{"key": "work-spine"}])
        activity_first = dashboard_activity.activity_payload(
            project_key_value="work-spine",
            mode="milestones",
            work_id=UUID(first["work"]["id"]),
            limit=1,
        )
        assert activity_first is not None
        assert activity_first["has_more"] is True
        activity_second = dashboard_activity.activity_payload(
            project_key_value="work-spine",
            mode="milestones",
            work_id=UUID(first["work"]["id"]),
            cursor=activity_first["next_cursor"],
            limit=1,
        )
        assert activity_second is not None
        assert {
            activity_first["items"][0]["event_id"],
            activity_second["items"][0]["event_id"],
        } == {
            item["event_id"]
            for item in dashboard_activity.activity_payload(
                project_key_value="work-spine",
                mode="milestones",
                work_id=UUID(first["work"]["id"]),
                limit=10,
            )["items"]
        }
        completed_activity = dashboard_activity.activity_payload(
            project_key_value="work-spine",
            status="completed",
            work_id=UUID(first["work"]["id"]),
        )
        assert completed_activity is not None
        assert [item["event_type"] for item in completed_activity["items"]] == ["WorkCompleted"]

        def concurrent_begin(number: int) -> dict:
            return work_uc.begin(
                root,
                goal=f"Concurrent work {number}",
                kind="review",
                idempotency_key=f"work-concurrent-{number}-{uuid4().hex}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent = list(executor.map(concurrent_begin, (1, 2)))
        assert {item["work"]["key"] for item in concurrent} == {"W-0003", "W-0004"}

        with Session(engine, expire_on_commit=False) as db:
            assert (
                db.scalar(select(func.count(WorkItem.id)).where(WorkItem.project_id == project_id))
                == 4
            )
            assert (
                db.scalar(
                    select(func.count(AgentRun.id))
                    .join(WorkItem)
                    .where(WorkItem.project_id == project_id)
                )
                == 4
            )
            work_started = db.scalars(
                select(RuntimeEvent).where(
                    RuntimeEvent.project_id == project_id,
                    RuntimeEvent.event_type == "WorkStarted",
                )
            ).all()
            assert len(work_started) == 4
            contexts = db.scalars(
                select(RuntimeEventContext).where(
                    RuntimeEventContext.event_id.in_([item.id for item in work_started])
                )
            ).all()
            assert len(contexts) == 4
            assert all(item.work_id is not None for item in contexts)
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session
        with Session(engine) as db:
            project = db.get(Project, project_id)
            if project is not None:
                db.delete(project)
                db.commit()


def _constraint_names(db: Session, table: str) -> set[str]:
    rows = db.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = :table AND c.contype = 'u'"
        ),
        {"table": table},
    ).fetchall()
    return {row[0] for row in rows}


def test_command_receipts_unique_constraint_is_project_and_command(tmp_path) -> None:
    engine = _engine()
    actor = Actor("user:pg", "user", frozenset({Capability.TASK_CREATE}), authenticated=True)
    with Session(engine, expire_on_commit=False) as db:
        assert "uq_command_receipts_project_command" in _constraint_names(db, "command_receipts")
        assert "uq_command_receipts_command_id" not in _constraint_names(db, "command_receipts")
        project_a = Project(
            name=f"cmd-a-{uuid4().hex}",
            root_path=str(tmp_path / f"a-{uuid4().hex}"),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        project_b = Project(
            name=f"cmd-b-{uuid4().hex}",
            root_path=str(tmp_path / f"b-{uuid4().hex}"),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add_all([project_a, project_b])
        db.flush()
        shared = "shared-pg-key"
        db.add(
            CommandReceipt(
                project_id=project_a.id,
                command_id=shared,
                command_name="work_begin",
                request_hash=_legacy_request_hash("work_begin", {"goal": "kept"}),
                status="completed",
                result={"created": 1},
            )
        )
        db.add(
            CommandReceipt(
                project_id=project_b.id,
                command_id=shared,
                command_name="work_begin",
                request_hash="b" * 64,
                status="completed",
                result={"created": 2},
            )
        )
        db.commit()
        duplicate = CommandReceipt(
            project_id=project_a.id,
            command_id=shared,
            command_name="work_begin",
            request_hash="c" * 64,
            status="completed",
            result={"created": 3},
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        calls = {"count": 0}

        def handler() -> dict:
            calls["count"] += 1
            return {"created": 99}

        replayed = execute_idempotent(
            db,
            command_id=shared,
            command_name="work_begin",
            request={"goal": "kept"},
            actor=actor,
            correlation_id="corr-legacy-pg",
            project_id=project_a.id,
            handler=handler,
        )
        assert replayed == {"created": 1}
        assert calls["count"] == 0
        db.delete(project_a)
        db.delete(project_b)
        db.commit()


def test_postgres_work_begin_same_key_is_independent_across_projects() -> None:
    import ai_layer.db.session as db_session

    engine = _engine()
    root_a = f"/tmp/work-scope-a-{uuid4().hex}"
    root_b = f"/tmp/work-scope-b-{uuid4().hex}"
    with Session(engine, expire_on_commit=False) as db:
        project_a = Project(
            name=f"scope-a-{uuid4().hex}",
            root_path=root_a,
            languages={},
            dependencies={},
            architecture_summary="",
        )
        project_b = Project(
            name=f"scope-b-{uuid4().hex}",
            root_path=root_b,
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add_all([project_a, project_b])
        db.commit()
        ids = (project_a.id, project_b.id)

    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:

        def begin_on(root: str) -> dict:
            return work_uc.begin(
                root, goal="Same goal", kind="change", idempotency_key="shared-work-key"
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = list(executor.map(begin_on, (root_a, root_b)))
        assert first["work"]["id"] != second["work"]["id"]
        replay = work_uc.begin(
            root_a, goal="Same goal", kind="change", idempotency_key="shared-work-key"
        )
        assert replay["work"]["id"] == first["work"]["id"]
        with Session(engine) as db:
            assert (
                db.scalar(select(func.count(WorkItem.id)).where(WorkItem.project_id.in_(ids))) == 2
            )
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session
        with Session(engine) as db:
            for project_id in ids:
                project = db.get(Project, project_id)
                if project is not None:
                    db.delete(project)
            db.commit()
