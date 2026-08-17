from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application import projects as projects_uc
from ai_layer.application import tasks as tasks_uc
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.db.work_models import AgentRun, WorkItem
from ai_layer.mcp import server
from ai_layer.mcp import context as mcp_context
from ai_layer.mcp.tools import tasks as task_tools


def test_mcp_task_create_returns_automatic_backing_work(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="mcp-managed-work",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()

    @contextmanager
    def db_scope():
        yield db

    @contextmanager
    def no_audit(*args, **kwargs):
        yield {"metrics": {}}

    monkeypatch.setattr(projects_uc, "session_scope", db_scope)
    monkeypatch.setattr(tasks_uc, "session_scope", db_scope)
    monkeypatch.setattr(task_tools, "mcp_audit", no_audit)
    monkeypatch.delenv("AI_LAYER_MCP_BRIDGE", raising=False)
    mcp_context.reset_project_bindings_for_tests()

    try:
        result = server.task_create(
            goal="Run this through the standard Task protocol",
            project_root=str(root),
        )

        assert result["key"] == "T-0001"
        assert result["project_root"] == str(root.resolve())
        assert result["work"]["key"] == "W-0001"
        assert result["work"]["linked_task_id"] == result["id"]
        assert result["work"]["observability_coverage"] == "control_plane_only"
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0

        current = server.task_current(project_root=str(root))
        assert current["work"]["id"] == result["work"]["id"]
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1
    finally:
        mcp_context.reset_project_bindings_for_tests()
        db.close()
