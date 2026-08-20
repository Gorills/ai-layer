from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.application import project_intelligence as pi
from ai_layer.application import work as work_uc
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.db.session import session_scope
from ai_layer.db.work_models import AgentRun
from ai_layer.projections.dashboard_work_state import _truthful_state, enrich_overview
from ai_layer.work.service import WORK_RUN_STALE_SECONDS


def _project(db: Session, tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    db.add(
        Project(
            name=name,
            root_path=str(root.resolve()),
            languages={},
            dependencies={},
            architecture_summary="",
        )
    )
    return root.resolve()


@contextmanager
def _bound_work_db(tmp_path: Path):
    import ai_layer.db.session as db_session

    engine = create_engine(f"sqlite:///{tmp_path / 'work.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        root = _project(db, tmp_path, "stale-proj")
        db.commit()
    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield root
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session


def _expire_heartbeat(run_id: str) -> None:
    with session_scope() as db:
        run = db.get(AgentRun, UUID(run_id))
        assert run is not None
        run.heartbeat_at = datetime.now(UTC) - timedelta(seconds=WORK_RUN_STALE_SECONDS + 5)
        db.commit()


def _stub_status_reads(monkeypatch) -> None:
    monkeypatch.setattr(
        pi,
        "interactive_freshness",
        lambda _project: {
            "status": "fresh",
            "snapshot_available": True,
            "background_refresh": False,
            "refresh_job": None,
            "changed_paths": [],
            "read_contract": "fresh",
        },
    )
    monkeypatch.setattr(pi, "project_map_status", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(pi, "semantic_map_status", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        pi,
        "project_policy_snapshot",
        lambda *_args, **_kwargs: {
            "version": 1,
            "text": "",
            "chars": 0,
            "sha256": "0" * 64,
            "truncated": False,
        },
    )
    monkeypatch.setattr(pi.epic_uc, "list_for_project", lambda *_args, **_kwargs: [])


def test_stale_heartbeat_drops_live_but_keeps_work_in_attention(tmp_path: Path) -> None:
    with _bound_work_db(tmp_path) as root:
        started = work_uc.begin(root, goal="Finish the recovery path", kind="change")
        key = started["work"]["key"]
        fresh = work_uc.state(root)
        assert any(item["key"] == key and item["live"] is True for item in fresh["live"])
        assert all(item["key"] != key for item in fresh["attention"])

        _expire_heartbeat(started["root_run"]["id"])
        stale = work_uc.state(root)
        item = next(row for row in stale["active"] if row["key"] == key)
        assert item["live"] is False
        assert item["status"] == "active"
        assert item["runs"][0]["stale"] is True
        assert item["runs"][0]["effective_status"] == "stale"
        assert stale["live"] == []
        assert any(row["key"] == key for row in stale["attention"])


def test_fresh_work_stays_live_and_out_of_attention(monkeypatch, tmp_path: Path) -> None:
    _stub_status_reads(monkeypatch)
    with _bound_work_db(tmp_path) as root:
        started = work_uc.begin(root, goal="Keep the same WorkItem", kind="change")
        key = started["work"]["key"]
        status = pi.project_status(root)
        work = status["work"]
        assert any(item["key"] == key and item["live"] is True for item in work["live_work"])
        assert all(item["key"] != key for item in work["work_attention"])
        continuation = work["continuation"]
        assert continuation["kind"] == "work"
        assert continuation["key"] == key
        assert continuation.get("navigator") is None
        assert "next_action" not in continuation
        assert "instruction" not in continuation
        live_row = next(item for item in work["live_work"] if item["key"] == key)
        assert "runs" not in live_row
        assert "guidance" not in status
        assert "agent_contract" not in status
        assert "latest_task" not in work


def test_project_status_does_not_start_new_work_while_stale_active_exists(
    monkeypatch, tmp_path: Path
) -> None:
    _stub_status_reads(monkeypatch)
    with _bound_work_db(tmp_path) as root:
        started = work_uc.begin(root, goal="Resume or terminate this item", kind="change")
        _expire_heartbeat(started["root_run"]["id"])
        status = pi.project_status(root)
        work = status["work"]
        key = started["work"]["key"]
        assert work["live_work"] == []
        assert any(item["key"] == key for item in work["work_attention"])
        continuation = work["continuation"]
        assert continuation["kind"] == "work"
        assert continuation["key"] == key
        assert work["current_focus"] == {
            "kind": "work",
            "key": key,
            "goal": "Resume or terminate this item",
        }
        assert continuation.get("navigator") is None
        assert "next_action" not in continuation
        assert "instruction" not in continuation


def test_project_status_idle_continuation_points_to_work_begin(monkeypatch, tmp_path: Path) -> None:
    _stub_status_reads(monkeypatch)
    monkeypatch.setattr(
        pi.task_uc,
        "read_state",
        lambda *_args, **_kwargs: {"current": None, "source": "db"},
    )
    with _bound_work_db(tmp_path) as root:
        status = pi.project_status(root)
        continuation = status["work"]["continuation"]
        next_action = continuation["next_action"]
        assert status["envelope"] == "ordinary"
        assert "next_action" not in status
        assert "agent_contract" not in status
        assert "guidance" not in status
        assert continuation["kind"] == "none"
        assert continuation["navigator"] == "work_begin"
        assert next_action["action"] == "begin_ordinary_work"
        assert next_action["tool"] == "work_begin"
        assert next_action["required"] == ["goal"]
        assert "research" in next_action["kind"]
        assert "diagnose" in next_action["kind"]
        assert "tiny one-shot" in next_action["skip_when"].casefold()
        assert "instruction" not in continuation
        assert status["work"]["current_focus"] is None
        assert status["active"] is False


def test_project_status_task_continuation_requires_authoritative_task_next() -> None:
    task = pi._compact_task(
        {
            "id": "task-1",
            "key": "T-0001",
            "goal": "Review the change",
            "status": "active",
            "workflow_profile": "STANDARD",
            "risk_level": "normal",
            "updated_at": "2026-08-20T00:00:00+00:00",
            "active_stage": {
                "id": "stage-1",
                "kind": "review",
                "status": "active",
                "worker_id": None,
            },
            "next_action": {
                "action": "delegate_stage",
                "tool": "task_stage_delegate",
                "message": "Projected state must not become live navigation.",
            },
            "open_findings": 0,
        }
    )
    assert task is not None
    assert "next_action" not in task
    assert pi._continuation(task, None, None) == {
        "kind": "task",
        "key": "T-0001",
        "goal": "Review the change",
        "navigator": "task_next",
    }


def test_project_status_omits_idle_latest_task_and_procedure_payloads(
    monkeypatch, tmp_path: Path
) -> None:
    _stub_status_reads(monkeypatch)
    monkeypatch.setattr(
        pi.task_uc,
        "read_state",
        lambda *_args, **_kwargs: {
            "current": None,
            "latest": {
                "id": "closed-task",
                "key": "T-0009",
                "goal": "Closed managed work",
                "status": "completed",
                "workflow_profile": "STANDARD",
                "risk_level": "normal",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "active_stage": None,
                "next_action": None,
                "open_findings": 0,
            },
            "source": "db",
        },
    )
    with _bound_work_db(tmp_path) as root:
        status = pi.project_status(root)
        work = status["work"]
        assert "latest_task" not in work
        assert "open_epics" not in work
        assert "observability_contract" not in work
        assert "guidance" not in status
        assert "agent_contract" not in status
        assert status["envelope"] == "ordinary"
        assert "languages" not in status["project"]
        assert "refresh_job" not in status["index"]["freshness"]
        assert "contract" not in status["index"]["project_map"]
        assert "language_policy" not in status["index"]["project_map"]


def test_completed_unreconciled_map_is_deferred_on_dashboard_not_mcp_attention(
    monkeypatch, tmp_path: Path
) -> None:
    _stub_status_reads(monkeypatch)
    with _bound_work_db(tmp_path) as root:
        started = work_uc.begin(root, goal="Land the change", kind="change")
        key = started["work"]["key"]
        work_uc.complete(root, work_key=key, summary="Done without map reconcile")
        dashboard = work_uc.state(root)
        assert any(
            item["key"] == key
            and item["status"] == "completed"
            and (item.get("map_disposition") or {}).get("status") == "deferred"
            for item in dashboard["attention"]
        )
        status = pi.project_status(root)
        assert all(item["key"] != key for item in status["work"]["work_attention"])
        overview = enrich_overview(
            {"projects": [{"root": str(root), "task": {}, "agents": []}], "summary": {}}
        )
        assert any(item["key"] == key for item in overview["projects"][0]["work"]["attention"])


def test_dashboard_is_not_healthy_because_the_run_went_stale(monkeypatch) -> None:
    project = {
        "task": {"key": "T-0001", "status": "active"},
        "agents": [{"activity_state": "WORKING"}],
    }
    stale = {
        "active": [{"key": "W-0001", "status": "active", "live": False}],
        "live": [],
        "attention": [{"key": "W-0001", "status": "active", "live": False}],
        "recent": [],
    }
    runtime_state, project_state = _truthful_state(project, stale)
    assert runtime_state != "idle"
    assert project_state == "attention"
    assert runtime_state in {"stale", "attention"}

    monkeypatch.setattr(
        "ai_layer.projections.dashboard_work_state.work_uc.state",
        lambda *_args, **_kwargs: stale,
    )
    monkeypatch.setattr(
        "ai_layer.projections.dashboard_work_state._map_state",
        lambda *_args, **_kwargs: {},
    )
    overview = enrich_overview(
        {"projects": [{"root": "/tmp/stale-proj", "task": {}, "agents": []}], "summary": {}}
    )
    card = overview["projects"][0]
    assert card["project_state"] == "attention"
    assert card["runtime_state"] != "idle"
    assert card["work"]["live"] == []
    assert card["work"]["attention"][0]["key"] == "W-0001"
