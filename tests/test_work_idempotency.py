from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.application import work as work_uc
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.mcp.runtime import _scoped
from ai_layer.mcp.tools import work as work_tools


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
        root_a = _project(db, tmp_path, "proj-a")
        root_b = _project(db, tmp_path, "proj-b")
        db.commit()
    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield root_a, root_b
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session


def test_work_begin_same_key_creates_independent_work_per_project(tmp_path: Path) -> None:
    with _bound_work_db(tmp_path) as (root_a, root_b):
        first = work_uc.begin(root_a, goal="Same goal", kind="change", idempotency_key="shared-key")
        replay = work_uc.begin(
            root_a, goal="Same goal", kind="change", idempotency_key="shared-key"
        )
        second = work_uc.begin(
            root_b, goal="Same goal", kind="change", idempotency_key="shared-key"
        )
        assert first["work"]["id"] == replay["work"]["id"]
        assert first["work"]["id"] != second["work"]["id"]
        assert first["project_root"] == str(root_a)
        assert second["project_root"] == str(root_b)
        with pytest.raises(RuntimeError, match="IDEMPOTENCY_KEY_REUSED"):
            work_uc.begin(
                root_a, goal="Different goal", kind="change", idempotency_key="shared-key"
            )


def test_mcp_work_tools_do_not_stamp_foreign_work_as_requested_root(
    monkeypatch, tmp_path: Path
) -> None:
    @contextmanager
    def fake_audit(*_args, **_kwargs):
        yield {}

    monkeypatch.setattr(work_tools, "mcp_audit", fake_audit)
    with _bound_work_db(tmp_path) as (root_a, root_b):
        started_a = work_tools.work_begin(
            goal="Same goal",
            kind="change",
            idempotency_key="begin-shared",
            project_root=str(root_a),
        )
        started_b = work_tools.work_begin(
            goal="Same goal",
            kind="change",
            idempotency_key="begin-shared",
            project_root=str(root_b),
        )
        assert started_a["work"]["id"] != started_b["work"]["id"]
        assert started_a["project_root"] == str(root_a)
        assert started_b["project_root"] == str(root_b)
        with pytest.raises(RuntimeError, match="WORK_PROJECT_MISMATCH"):
            _scoped(dict(started_a), str(root_b))

        checkpoint_a = work_tools.work_checkpoint(
            work_key=started_a["work"]["key"],
            summary="milestone",
            idempotency_key="checkpoint-shared",
            project_root=str(root_a),
        )
        checkpoint_b = work_tools.work_checkpoint(
            work_key=started_b["work"]["key"],
            summary="milestone",
            idempotency_key="checkpoint-shared",
            project_root=str(root_b),
        )
        assert checkpoint_a["work"]["id"] == started_a["work"]["id"]
        assert checkpoint_b["work"]["id"] == started_b["work"]["id"]
        with pytest.raises(RuntimeError, match="WORK_PROJECT_MISMATCH"):
            _scoped(dict(checkpoint_a), str(root_b))

        completed_a = work_tools.work_complete(
            work_key=started_a["work"]["key"],
            summary="done",
            idempotency_key="complete-shared",
            project_root=str(root_a),
        )
        completed_b = work_tools.work_complete(
            work_key=started_b["work"]["key"],
            summary="done",
            idempotency_key="complete-shared",
            project_root=str(root_b),
        )
        assert completed_a["work"]["id"] != completed_b["work"]["id"]
        assert completed_a["project_root"] == str(root_a)
        with pytest.raises(RuntimeError, match="WORK_PROJECT_MISMATCH"):
            _scoped(dict(completed_a), str(root_b))


def test_mcp_scoped_task_payloads_still_receive_requested_root(tmp_path: Path) -> None:
    root = tmp_path / "task-root"
    root.mkdir()
    payload = _scoped({"task": {"key": "T-0001"}}, str(root))
    assert payload["project_root"] == str(root.resolve())
    assert payload["task"]["project_root"] == str(root.resolve())
