from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.application import epic_lifecycle, epics
from ai_layer.core.config import get_settings
from ai_layer.db.base import Base
from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.work_models import RuntimeEventContext
from ai_layer.observability.domain_events import EVENT_TYPES, append_event
from ai_layer.observability.work_events import append_contextual_event
from ai_layer.projections import dashboard_activity, dashboard_work
from ai_layer.projections.dashboard_activity import MILESTONE_EVENT_TYPES
from ai_layer.tasks import service as tasks
from ai_layer.work.service import begin_work

EPIC_SPEC = """# Goal
Ship filterable Task and Epic activity.

# Product outcome
Operators can filter Activity by Task and Epic identity.

# Accepted decisions
New lifecycle events carry RuntimeEventContext identities.

# Functional requirements
TaskCreated and EpicCreated populate correlation context.

# Acceptance criteria
activity_payload returns those events for the matching id.

# Definition of done
Default milestones include Epic lifecycle types.
"""


def _engine_project(tmp_path: Path) -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    return engine, root


def _bind_activity(monkeypatch, engine, root: Path, *, key: str = "activity-project"):
    entry = {"root": str(root.resolve()), "project_id": key, "name": "Activity Project"}

    @contextmanager
    def scope():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    monkeypatch.setattr(dashboard_activity, "selected_entries", lambda _key: [entry])
    monkeypatch.setattr(dashboard_activity, "project_options", lambda: [{"key": key}])
    monkeypatch.setattr(dashboard_activity, "session_scope", scope)
    monkeypatch.setattr(dashboard_work, "selected_entries", lambda _key: [entry])

    def entry_for_key(wanted: str):
        return entry if wanted == key else None

    monkeypatch.setattr(dashboard_work, "entry_for_key", entry_for_key)
    monkeypatch.setattr(dashboard_work, "project_options", lambda: [{"key": key}])
    monkeypatch.setattr(dashboard_work, "session_scope", scope)
    return entry


def test_new_task_created_is_returned_by_activity_task_id_filter(monkeypatch, tmp_path: Path):
    engine, root = _engine_project(tmp_path)
    _bind_activity(monkeypatch, engine, root)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Activity Project",
            root_path=str(root.resolve()),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        created = tasks.create_task(
            db,
            project,
            goal="Make TaskCreated filterable",
            acceptance_criteria=["activity_payload returns TaskCreated"],
            constraints=["do not rewrite historical events"],
        )
        task_id = UUID(created["id"])
        context_ids = set(
            db.scalars(
                select(RuntimeEventContext.event_id).where(RuntimeEventContext.task_id == task_id)
            ).all()
        )
        created_events = db.scalars(
            select(RuntimeEvent).where(
                RuntimeEvent.event_type == "TaskCreated",
                RuntimeEvent.aggregate_id == str(task_id),
            )
        ).all()
        assert created_events
        assert {row.id for row in created_events} <= context_ids

    payload = dashboard_activity.activity_payload(task_id=task_id)
    assert payload is not None
    assert [item["event_type"] for item in payload["items"]] == ["TaskCreated"]
    assert payload["items"][0]["task_id"] == str(task_id)

    all_events = dashboard_activity.activity_payload(mode="all", task_id=task_id)
    assert all_events is not None
    assert "TaskCreated" in [item["event_type"] for item in all_events["items"]]
    assert "TaskClassified" in [item["event_type"] for item in all_events["items"]]


def test_historical_task_created_without_context_stays_unfilterable(monkeypatch, tmp_path: Path):
    engine, root = _engine_project(tmp_path)
    _bind_activity(monkeypatch, engine, root)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Activity Project",
            root_path=str(root.resolve()),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        task_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        append_event(
            db,
            event_type="TaskCreated",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task_id),
            payload={"key": "T-0001"},
        )
        db.commit()

    payload = dashboard_activity.activity_payload(task_id=task_id, mode="all")
    assert payload is not None
    assert payload["items"] == []
    unfiltered = dashboard_activity.activity_payload()
    assert unfiltered is not None
    assert [item["event_type"] for item in unfiltered["items"]] == ["TaskCreated"]
    assert unfiltered["items"][0]["task_id"] is None


def test_new_epic_created_is_default_milestone_and_epic_id_filterable(monkeypatch, tmp_path: Path):
    engine, root = _engine_project(tmp_path)
    _bind_activity(monkeypatch, engine, root)
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Activity Project",
            root_path=str(root.resolve()),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
            project_intelligence={},
        )
        db.add(project)
        db.commit()

        @contextmanager
        def scope():
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

        monkeypatch.setattr(epic_lifecycle, "session_scope", scope)
        created = epics.create(root, title="Filterable Epic", spec_markdown=EPIC_SPEC)
        epic_id = UUID(created["id"])

    try:
        payload = dashboard_activity.activity_payload(epic_id=epic_id)
        assert payload is not None
        assert [item["event_type"] for item in payload["items"]] == ["EpicCreated"]
        assert payload["items"][0]["epic_id"] == str(epic_id)
        default = dashboard_activity.activity_payload()
        assert default is not None
        assert "EpicCreated" in [item["event_type"] for item in default["items"]]
        assert {"EpicCreated", "EpicCompleted", "EpicArchived"} <= MILESTONE_EVENT_TYPES
        assert {name for name in EVENT_TYPES if name.startswith("Epic")} <= MILESTONE_EVENT_TYPES
    finally:
        get_settings.cache_clear()


def test_work_detail_includes_linked_task_milestones_not_internal_history(
    monkeypatch, tmp_path: Path
):
    engine, root = _engine_project(tmp_path)
    _bind_activity(monkeypatch, engine, root)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Activity Project",
            root_path=str(root.resolve()),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        created = tasks.create_task(
            db,
            project,
            goal="Link Work to this Task",
            acceptance_criteria=["Work detail shows TaskCreated"],
            constraints=["do not duplicate Task internal history"],
        )
        work, run = begin_work(
            db,
            project,
            goal="Inspect linked Task milestones",
            kind="diagnose",
            linked_task_key=created["key"],
        )
        append_contextual_event(
            db,
            event_type="WorkStarted",
            project=project,
            aggregate_type="work",
            aggregate_id=str(work.id),
            work=work,
            run=run,
            payload={"goal": work.goal, "status": work.status},
            importance="high",
        )
        db.commit()

    detail = dashboard_work.work_detail_payload("activity-project", "W-0001")
    assert detail is not None
    types = [item["event_type"] for item in detail["timeline"]]
    assert "WorkStarted" in types
    assert "TaskCreated" in types
    assert "TaskClassified" not in types
    assert detail["work"]["linked_task_key"] == created["key"]
