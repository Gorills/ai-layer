from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.application.project_intelligence import _continuation, _mcp_work_attention
from ai_layer.application.work import _attention_work, _effective_work_payload
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.db.work_models import AgentRun, WorkItem
from ai_layer.domain.agent_contract import agent_runtime_bootstrap_line, agent_runtime_contract
from ai_layer.domain.orchestrator import critical_orchestrator_contract, native_bootstrap_markdown
from ai_layer.observability.domain_events import EVENT_TYPES
from ai_layer.observability.work_events import MILESTONE_EVENT_TYPES
from ai_layer.projections.dashboard_work import _normalized_status, _status_condition, _work_items
from ai_layer.projections.dashboard_work_state import _truthful_state
from ai_layer.work.lifecycle import effective_work_status, resume_work, wait_work
from ai_layer.work.service import begin_work, finish_work


def _project(db: Session) -> Project:
    project = Project(
        name="Feedback lifecycle",
        root_path="/tmp/work-feedback-lifecycle",
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.flush()
    return project


def test_wait_and_resume_rotate_agent_runs_without_closing_work() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = _project(db)
        project_metadata = {
            project.id: {
                "key": "project",
                "name": project.name,
                "root": project.root_path,
            }
        }
        work, first_run = begin_work(
            db,
            project,
            goal="Prepare a PDF and refine it from user feedback",
            host="codex",
            session_id="session-1",
        )

        waiting, stopped_runs = wait_work(
            db,
            project,
            work_key_value="W-0001",
            summary="Initial PDF is ready for feedback",
        )
        assert waiting.id == work.id
        assert waiting.status == "active"
        assert waiting.completed_at is None
        assert [run.id for run in stopped_runs] == [first_run.id]
        assert stopped_runs[0].status == "completed"
        assert stopped_runs[0].ended_at is not None
        assert effective_work_status(waiting, stopped_runs) == "awaiting_feedback"
        assert _work_items(db, [waiting], project_metadata)[0]["status"] == "awaiting_feedback"
        assert _normalized_status("awaiting_feedback") == "awaiting_feedback"
        waiting_rows = list(
            db.scalars(select(WorkItem).where(_status_condition("awaiting_feedback")))
        )
        assert waiting_rows == [work]
        assert list(db.scalars(select(WorkItem).where(_status_condition("active")))) == []

        resumed, second_run = resume_work(
            db,
            project,
            work_key_value="W-0001",
            host="codex",
            session_id="session-2",
        )
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.work_id == work.id)
                .order_by(AgentRun.started_at, AgentRun.id)
            ).all()
        )
        assert resumed.id == work.id
        assert second_run.id != first_run.id
        assert second_run.status == "active"
        assert len(runs) == 2
        assert effective_work_status(resumed, runs) == "active"
        assert _work_items(db, [resumed], project_metadata)[0]["status"] == "active"
        assert list(db.scalars(select(WorkItem).where(_status_condition("active")))) == [work]

        completed, terminal_runs = finish_work(
            db,
            project,
            work_key_value="W-0001",
            status="completed",
            summary="PDF accepted",
        )
        assert completed.id == work.id
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert [run.id for run in terminal_runs] == [second_run.id]


def test_wait_is_repeatable_but_resume_refuses_duplicate_execution() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = _project(db)
        work, _run = begin_work(db, project, goal="Refine one logo placement")

        _waiting, first_stop = wait_work(db, project, work_key_value="W-0001")
        waiting_again, second_stop = wait_work(db, project, work_key_value="W-0001")
        assert len(first_stop) == 1
        assert second_stop == []
        assert effective_work_status(waiting_again, first_stop) == "awaiting_feedback"

        _resumed, active_run = resume_work(db, project, work_key_value="W-0001")
        assert active_run.status == "active"
        with pytest.raises(RuntimeError, match="already has an active AgentRun"):
            resume_work(db, project, work_key_value="W-0001")

        active_runs = list(
            db.scalars(
                select(AgentRun).where(AgentRun.work_id == work.id, AgentRun.status == "active")
            ).all()
        )
        assert [run.id for run in active_runs] == [active_run.id]


def test_awaiting_feedback_is_open_but_not_live_stale_or_attention() -> None:
    waiting = {
        "id": "work-1",
        "key": "W-0001",
        "goal": "Refine PDF",
        "status": "awaiting_feedback",
        "live": False,
        "map_disposition": {"status": "pending"},
    }
    effective = _effective_work_payload(
        {
            **waiting,
            "status": "active",
            "runs": [{"status": "completed"}],
        }
    )
    assert effective["status"] == "awaiting_feedback"
    assert _attention_work([waiting], []) == []
    assert _mcp_work_attention([waiting]) == []
    assert _truthful_state({}, {"active": [waiting], "live": []}) == ("idle", "healthy")

    continuation = _continuation(None, waiting, None)
    assert continuation["kind"] == "work"
    assert continuation["key"] == "W-0001"
    assert continuation["navigator"] == "work_resume"
    assert continuation["next_action"]["tool"] == "work_resume"


def test_agent_contract_keeps_one_work_across_feedback_iterations() -> None:
    contract = agent_runtime_contract()
    assert contract["work"]["wait"] == "work_wait"
    assert contract["work"]["resume"] == "work_resume"
    assert "same WorkItem" in contract["work"]["awaiting_feedback"]
    bootstrap = agent_runtime_bootstrap_line()
    assert "`work_wait`" in bootstrap
    assert "`work_resume`" in bootstrap
    assert "Terminal Work calls end the durable outcome itself" in bootstrap
    native = native_bootstrap_markdown()
    assert "`work_wait`" in native
    assert "`work_resume`" in native
    assert "same WorkItem" in native
    assert "work_wait/work_resume" in critical_orchestrator_contract()["work_rule"]
    assert {"WorkAwaitingFeedback", "WorkResumed"} <= EVENT_TYPES
    assert {"WorkAwaitingFeedback", "WorkResumed"} <= MILESTONE_EVENT_TYPES


def test_mcp_catalog_exposes_wait_and_resume() -> None:
    from ai_layer.mcp.runtime import TOOL_HANDLERS
    from ai_layer.mcp.server import mcp

    for name in ("work_wait", "work_resume"):
        assert name in TOOL_HANDLERS
        assert mcp._tool_manager.get_tool(name) is not None
