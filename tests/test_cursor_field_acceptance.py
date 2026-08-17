from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.core.jsonutil import wire_value
from ai_layer.db.base import Base
from ai_layer.db.models import Project, Task
from ai_layer.mcp.tool_schema import WorkCheckInput
from ai_layer.memory.project_map_semantics import reconcile_project_map
from ai_layer.work.service import begin_work, finish_work


def _project(db: Session, root: str = "/tmp/cursor-field-acceptance") -> Project:
    project = Project(
        name="cursor-field-acceptance",
        root_path=root,
        languages={"typescript": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.flush()
    return project


def test_natural_cursor_check_report_normalizes_before_durable_work_evidence() -> None:
    schema = WorkCheckInput.model_json_schema()
    assert {"command", "result"} <= set(schema["properties"])
    assert "name" not in schema.get("required", [])
    assert "status" not in schema.get("required", [])
    result_schema = schema["properties"]["result"]
    assert any(item.get("maxLength") == 4000 for item in result_schema.get("anyOf", []))

    check = WorkCheckInput(
        command="npx tsc --noEmit (mobile)",
        result="pre-existing errors elsewhere, no errors in changed files",
    )
    assert wire_value([check]) == [
        {
            "name": "reported check",
            "status": "reported",
            "summary": "pre-existing errors elsewhere, no errors in changed files",
        }
    ]


def test_terminal_work_derives_summary_when_cursor_omits_it() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = _project(db)
        _work, _run = begin_work(db, project, goal="Fix mobile TypeScript errors")
        completed, _runs = finish_work(
            db,
            project,
            work_key_value="W-0001",
            status="completed",
            summary="",
            changed_paths=["mobile/src/app.ts"],
        )
        assert completed.status == "completed"
        assert completed.result_summary == "Completed work: Fix mobile TypeScript errors"


def test_task_linked_reconcile_derives_scope_from_backing_work() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = _project(db, "/tmp/cursor-task-map")
        task = Task(
            project_id=project.id,
            sequence=1,
            goal="Fix mobile TypeScript errors",
            acceptance_criteria=[],
            constraints=[],
            status="completed",
            final_changes={"modified": ["mobile/src/app.ts"]},
        )
        db.add(task)
        db.flush()
        work, _run = begin_work(
            db,
            project,
            goal=task.goal,
            linked_task_key="T-0001",
        )
        work.reviewed_paths = ["mobile/src/app.ts"]
        work.changed_paths = ["mobile/src/app.ts"]
        db.flush()

        result = reconcile_project_map(
            db,
            project,
            entries=None,
            remove_paths=None,
            scope_paths=None,
            source_task_key="T-0001",
            source_work_key=None,
            no_changes_reason="Existing navigation facts remain accurate.",
        )
        assert result["source_ref"] == "T-0001"
        assert result["scope_paths"] == ["mobile/src/app.ts"]
        assert result["map_disposition"]["status"] == "reconciled"
        assert work.map_disposition["scope"] == ["mobile/src/app.ts"]


def test_task_linked_reconcile_falls_back_to_known_final_changes_without_work() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = _project(db, "/tmp/cursor-task-map-fallback")
        db.add(
            Task(
                project_id=project.id,
                sequence=1,
                goal="Fix mobile TypeScript errors",
                acceptance_criteria=[],
                constraints=[],
                status="completed",
                final_changes={"modified": ["mobile/src/app.ts"]},
            )
        )
        db.flush()

        result = reconcile_project_map(
            db,
            project,
            entries=None,
            remove_paths=None,
            scope_paths=None,
            source_task_key="T-0001",
            source_work_key=None,
            no_changes_reason="Existing navigation facts remain accurate.",
        )
        assert result["scope_paths"] == ["mobile/src/app.ts"]


def test_natural_check_uses_explicit_machine_status_when_available() -> None:
    assert WorkCheckInput(command="npx tsc --noEmit", result=0).status == "passed"
    assert WorkCheckInput(command="npx tsc --noEmit", result=2).status == "failed"
    assert WorkCheckInput(name="lint", status="failed", summary="lint failed").status == "failed"
