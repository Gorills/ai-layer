from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.dashboard.work_contracts import WorkDetailRead, WorkListRead
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.observability.work_events import append_contextual_event
from ai_layer.projections import dashboard_work
from ai_layer.work.service import begin_work, checkpoint_work, finish_work


def test_work_list_and_detail_are_bounded_safe_durable_read_models(monkeypatch, tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = str((tmp_path / "project").resolve())
    Path(root).mkdir()

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Dashboard Work",
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
            goal="Inspect checkout flow",
            kind="diagnose",
            host="codex",
            client="mcp",
            session_id="session-1",
        )
        append_contextual_event(
            db,
            event_type="WorkStarted",
            project=project,
            aggregate_type="work",
            aggregate_id=str(work.id),
            work=work,
            run=run,
            payload={"goal": work.goal, "raw_prompt": "must-not-leak"},
            importance="high",
        )
        checkpoint_work(
            db,
            project,
            work_key_value="W-0001",
            summary="Checkout flow inspected.",
            reviewed_paths=["src/checkout.py"],
        )
        append_contextual_event(
            db,
            event_type="WorkCheckpointed",
            project=project,
            aggregate_type="work",
            aggregate_id=str(work.id),
            work=work,
            run=run,
            payload={"summary": "Checkout flow inspected.", "source_body": "must-not-leak"},
        )
        finish_work(
            db,
            project,
            work_key_value="W-0001",
            status="completed",
            summary="Checkout flow verified.",
            checks=[{"name": "focused tests", "status": "passed", "summary": "1 passed"}],
            map_disposition={
                "status": "checked_no_change",
                "scope": ["src/checkout.py"],
                "reason": "Existing navigation remains accurate.",
            },
        )
        append_contextual_event(
            db,
            event_type="WorkCompleted",
            project=project,
            aggregate_type="work",
            aggregate_id=str(work.id),
            work=work,
            payload={"status": "completed", "summary": "Checkout flow verified."},
            importance="high",
        )
        db.commit()

    entry = {"root": root, "project_id": "dashboard-work", "name": "Dashboard Work"}
    monkeypatch.setattr(dashboard_work, "selected_entries", lambda _key: [entry])
    monkeypatch.setattr(
        dashboard_work, "entry_for_key", lambda key: entry if key == "dashboard-work" else None
    )
    monkeypatch.setattr(dashboard_work, "project_options", lambda: [{"key": "dashboard-work"}])

    @contextmanager
    def scope():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    monkeypatch.setattr(dashboard_work, "session_scope", scope)

    listing = dashboard_work.work_items_payload(status="completed", page=1, page_size=10)
    assert listing is not None
    assert listing["contract_version"] == 1
    assert listing["pagination"]["total"] == 1
    assert listing["ordering"] == ["updated_at:desc", "id:desc"]
    assert listing["items"][0]["key"] == "W-0001"
    assert listing["items"][0]["project"]["key"] == "dashboard-work"
    assert listing["items"][0]["runs"][0]["host"] == "codex"
    WorkListRead.model_validate(listing)

    detail = dashboard_work.work_detail_payload("dashboard-work", "W-0001")
    assert detail is not None
    assert detail["work"]["status"] == "completed"
    assert [item["event_type"] for item in detail["timeline"]] == [
        "WorkStarted",
        "WorkCheckpointed",
        "WorkCompleted",
    ]
    assert detail["timeline_total"] == 3
    assert detail["timeline_truncated"] is False
    assert "must-not-leak" not in repr(detail)
    WorkDetailRead.model_validate(detail)


def test_work_list_rejects_unknown_status_before_querying(monkeypatch):
    def fail_scope():
        raise AssertionError("invalid filter must fail before database access")

    monkeypatch.setattr(dashboard_work, "session_scope", fail_scope)
    try:
        dashboard_work.work_items_payload(status="working")
    except ValueError as exc:
        assert "status must be one of" in str(exc)
    else:
        raise AssertionError("unknown Work status must be rejected")
