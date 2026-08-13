from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.dashboard.activity_contracts import ActivityRead
from ai_layer.db.base import Base
from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.work_models import RuntimeEventContext
from ai_layer.projections import dashboard_activity
from ai_layer.work.service import begin_work


def _event(
    project: Project,
    *,
    event_id: int,
    event_type: str,
    occurred_at: datetime,
    payload: dict | None = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        id=UUID(int=event_id),
        project_id=project.id,
        event_type=event_type,
        aggregate_type="work",
        aggregate_id="W-0001",
        correlation_id="timeline-correlation",
        actor_id="agent:root",
        actor_kind="agent",
        interface="mcp",
        payload=payload or {},
        created_at=occurred_at,
    )


def test_activity_is_milestone_first_filterable_and_cursor_stable(monkeypatch, tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = str((tmp_path / "project").resolve())
    Path(root).mkdir()
    occurred_at = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Activity Project",
            root_path=root,
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        work, run = begin_work(
            db,
            project,
            goal="Build durable timeline",
            kind="change",
            host="codex",
            client="mcp",
            assurance="host_reported",
        )
        rows = [
            _event(project, event_id=1, event_type="WorkStarted", occurred_at=occurred_at),
            _event(
                project,
                event_id=2,
                event_type="WorkCheckpointed",
                occurred_at=occurred_at,
                payload={"status": "active", "source_body": "must-not-leak"},
            ),
            _event(
                project,
                event_id=3,
                event_type="OperationCompleted",
                occurred_at=occurred_at,
                payload={"status": "passed", "tool": "project_status"},
            ),
            _event(
                project,
                event_id=4,
                event_type="WorkCompleted",
                occurred_at=occurred_at,
                payload={"status": "completed", "summary": "Timeline shipped"},
            ),
        ]
        db.add_all(rows)
        db.flush()
        db.add_all(
            [
                RuntimeEventContext(
                    event_id=row.id,
                    work_id=work.id,
                    run_id=run.id,
                    host="codex",
                    client="mcp",
                    importance="high" if row.id.int in {1, 4} else "normal",
                )
                for row in rows
            ]
        )
        db.commit()

    entry = {"root": root, "project_id": "activity-project", "name": "Activity Project"}
    monkeypatch.setattr(dashboard_activity, "selected_entries", lambda _key: [entry])
    monkeypatch.setattr(
        dashboard_activity, "project_options", lambda: [{"key": "activity-project"}]
    )

    @contextmanager
    def scope():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    monkeypatch.setattr(dashboard_activity, "session_scope", scope)

    first = dashboard_activity.activity_payload(limit=2)
    assert first is not None
    assert first["contract_version"] == 2
    assert [item["event_id"] for item in first["items"]] == [str(UUID(int=4)), str(UUID(int=2))]
    assert first["has_more"] is True
    assert first["next_cursor"]
    assert first["ordering"] == ["occurred_at:desc", "event_id:desc"]
    assert first["items"][0]["assurance"] == "host_reported"
    assert "must-not-leak" not in repr(first)
    ActivityRead.model_validate(first)

    with Session(engine, expire_on_commit=False) as db:
        project = db.query(Project).one()
        work = (
            db.query(RuntimeEventContext).filter(RuntimeEventContext.work_id.is_not(None)).first()
        )
        assert work is not None
        inserted = _event(
            project,
            event_id=5,
            event_type="WorkStarted",
            occurred_at=occurred_at + timedelta(seconds=1),
        )
        db.add(inserted)
        db.flush()
        db.add(
            RuntimeEventContext(
                event_id=inserted.id,
                work_id=work.work_id,
                run_id=work.run_id,
                host="codex",
                client="mcp",
                importance="high",
            )
        )
        db.commit()

    second = dashboard_activity.activity_payload(cursor=first["next_cursor"], limit=2)
    assert second is not None
    assert [item["event_id"] for item in second["items"]] == [str(UUID(int=1))]
    assert second["has_more"] is False

    all_events = dashboard_activity.activity_payload(mode="all", limit=10)
    assert all_events is not None
    assert [item["event_type"] for item in all_events["items"]] == [
        "WorkStarted",
        "WorkCompleted",
        "OperationCompleted",
        "WorkCheckpointed",
        "WorkStarted",
    ]
    completed = dashboard_activity.activity_payload(status="completed", limit=10)
    assert completed is not None
    assert [item["event_type"] for item in completed["items"]] == ["WorkCompleted"]
    filtered = dashboard_activity.activity_payload(
        actor_id="agent:root",
        event_type="WorkCheckpointed",
        importance="normal",
        assurance="host_reported",
        occurred_after=occurred_at - timedelta(seconds=1),
        occurred_before=occurred_at + timedelta(seconds=1),
    )
    assert filtered is not None
    assert [item["event_type"] for item in filtered["items"]] == ["WorkCheckpointed"]

    with pytest.raises(ValueError, match="current filters"):
        dashboard_activity.activity_payload(mode="all", cursor=first["next_cursor"])
    with pytest.raises(ValueError, match="cursor is invalid"):
        dashboard_activity.activity_payload(cursor=f"{first['next_cursor']}!")


def test_activity_rejects_invalid_filters_before_database_access(monkeypatch):
    def fail_scope():
        raise AssertionError("invalid filters must fail before database access")

    monkeypatch.setattr(dashboard_activity, "session_scope", fail_scope)
    with pytest.raises(ValueError, match="mode must be one of"):
        dashboard_activity.activity_payload(mode="noise")
    with pytest.raises(ValueError, match="occurred_after must be earlier"):
        dashboard_activity.activity_payload(
            occurred_after=datetime(2026, 8, 14, tzinfo=UTC),
            occurred_before=datetime(2026, 8, 13, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="cursor is invalid"):
        dashboard_activity.activity_payload(cursor="not-a-cursor")
