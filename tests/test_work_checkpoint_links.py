from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.db.base import Base
from ai_layer.db.epic_models import Epic
from ai_layer.db.models import Project, Task
from ai_layer.domain.errors import StructuredError
from ai_layer.mcp.tools import work as work_tools
from ai_layer.work.service import begin_work, checkpoint_work, work_to_dict


def _add_project(db: Session, tmp_path: Path, name: str) -> tuple[Project, Path]:
    root = tmp_path / name
    root.mkdir()
    project = Project(
        name=name,
        root_path=str(root.resolve()),
        languages={},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.flush()
    return project, root.resolve()


def _add_task(db: Session, project: Project, *, sequence: int = 1) -> Task:
    task = Task(project_id=project.id, sequence=sequence, goal=f"Task {sequence}")
    db.add(task)
    db.flush()
    return task


def _add_epic(db: Session, project: Project, *, sequence: int = 1) -> Epic:
    epic = Epic(project_id=project.id, sequence=sequence, title=f"Epic {sequence}")
    db.add(epic)
    db.flush()
    return epic


@contextmanager
def _bound_work_db(tmp_path: Path):
    import ai_layer.db.session as db_session

    engine = create_engine(f"sqlite:///{tmp_path / 'work-links.db'}")
    Base.metadata.create_all(engine)
    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield engine
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session


def test_checkpoint_can_set_task_and_epic_links_after_unlinked_begin(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'checkpoint-links.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project, _root = _add_project(db, tmp_path, "proj")
        task = _add_task(db, project)
        epic = _add_epic(db, project)
        work, _run = begin_work(db, project, goal="Link later")
        assert work.linked_task_id is None
        assert work.linked_epic_id is None

        checkpoint_work(
            db,
            project,
            work_key_value="W-0001",
            summary="Attach managed identities",
            linked_task_key="T-0001",
            linked_epic_key="E-0001",
        )
        rendered = work_to_dict(db, work)
        assert rendered["linked_task_id"] == str(task.id)
        assert rendered["linked_epic_id"] == str(epic.id)


def test_checkpoint_rejects_invalid_and_foreign_link_keys(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'checkpoint-scope.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        local, _local_root = _add_project(db, tmp_path, "local")
        foreign, _foreign_root = _add_project(db, tmp_path, "foreign")
        local_task = _add_task(db, local)
        local_epic = _add_epic(db, local)
        foreign_task = _add_task(db, foreign)
        foreign_epic = _add_epic(db, foreign)
        work, _run = begin_work(db, local, goal="Stay in project")

        with pytest.raises(ValueError, match="linked_task_key must look like T-0001"):
            checkpoint_work(db, local, work_key_value="W-0001", linked_task_key="not-a-task")
        with pytest.raises(ValueError, match="linked_epic_key must look like E-0001"):
            checkpoint_work(db, local, work_key_value="W-0001", linked_epic_key="not-an-epic")
        with pytest.raises(ValueError, match="managed task T-0009 does not exist in this project"):
            checkpoint_work(db, local, work_key_value="W-0001", linked_task_key="T-0009")
        with pytest.raises(ValueError, match="epic E-0009 does not exist in this project"):
            checkpoint_work(db, local, work_key_value="W-0001", linked_epic_key="E-0009")

        outsider, _outsider_root = _add_project(db, tmp_path, "outsider")
        begin_work(db, outsider, goal="No local Task or Epic")
        with pytest.raises(ValueError, match="managed task T-0001 does not exist in this project"):
            checkpoint_work(db, outsider, work_key_value="W-0001", linked_task_key="T-0001")
        with pytest.raises(ValueError, match="epic E-0001 does not exist in this project"):
            checkpoint_work(db, outsider, work_key_value="W-0001", linked_epic_key="E-0001")

        checkpoint_work(
            db,
            local,
            work_key_value="W-0001",
            linked_task_key="T-0001",
            linked_epic_key="E-0001",
        )
        assert work.linked_task_id == local_task.id
        assert work.linked_epic_id == local_epic.id
        assert work.linked_task_id != foreign_task.id
        assert work.linked_epic_id != foreign_epic.id


def test_checkpoint_without_keys_preserves_begin_links_and_blank_keys_do_not_clear(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'begin-links.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project, _root = _add_project(db, tmp_path, "proj")
        task = _add_task(db, project)
        epic = _add_epic(db, project)
        work, _run = begin_work(
            db,
            project,
            goal="Linked at begin",
            linked_task_key="T-0001",
            linked_epic_key="E-0001",
        )
        assert work.linked_task_id == task.id
        assert work.linked_epic_id == epic.id

        checkpoint_work(db, project, work_key_value="W-0001", summary="No link change")
        assert work.linked_task_id == task.id
        assert work.linked_epic_id == epic.id

        checkpoint_work(
            db,
            project,
            work_key_value="W-0001",
            linked_task_key="  ",
            linked_epic_key="",
        )
        assert work.linked_task_id == task.id
        assert work.linked_epic_id == epic.id


def test_mcp_work_checkpoint_sets_project_scoped_links(monkeypatch, tmp_path: Path) -> None:
    @contextmanager
    def fake_audit(*_args, **_kwargs):
        yield {}

    monkeypatch.setattr(work_tools, "mcp_audit", fake_audit)
    with _bound_work_db(tmp_path) as engine:
        with Session(engine) as db:
            local, local_root = _add_project(db, tmp_path, "proj-a")
            foreign, _foreign_root = _add_project(db, tmp_path, "proj-b")
            local_task_id = str(_add_task(db, local).id)
            local_epic_id = str(_add_epic(db, local).id)
            _add_task(db, foreign)
            _add_epic(db, foreign)
            db.commit()

        started = work_tools.work_begin(
            goal="Link at checkpoint",
            kind="change",
            project_root=str(local_root),
        )
        assert started["work"]["linked_task_id"] is None
        assert started["work"]["linked_epic_id"] is None

        linked = work_tools.work_checkpoint(
            work_key=started["work"]["key"],
            summary="Attach local Task and Epic",
            linked_task_key="T-0001",
            linked_epic_key="E-0001",
            project_root=str(local_root),
        )
        assert linked["work"]["linked_task_id"] == local_task_id
        assert linked["work"]["linked_epic_id"] == local_epic_id

        missing = "managed task T-0009 does not exist in this project"
        with pytest.raises(StructuredError, match=missing):
            work_tools.work_checkpoint(
                work_key=started["work"]["key"],
                linked_task_key="T-0009",
                project_root=str(local_root),
            )
