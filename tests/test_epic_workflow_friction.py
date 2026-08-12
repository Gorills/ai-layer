from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.application import context as context_app
from ai_layer.application import (
    epic_execution,
    epic_lifecycle,
    epic_navigation,
    epic_planning,
    epic_review,
    epics,
)
from ai_layer.core.config import get_settings
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.tasks import service as tasks

RUSSIAN_SPEC = """# Цель
Сделать полноценную функцию управления большим изменением.

# Конечный результат
Пользователь получает готовый к использованию Epic workflow, а не эксперимент.

# Принятые решения
Epic хранит спецификацию и план, а существующий Task Engine выполняет каждую задачу.

# Функциональные требования
Спека версионируется, Phase 0 обязателен, задачи идут последовательно, финальный review проверяет весь Epic.

# Критерии приёмки
Все выбранные требования реализованы и проверены, документация и знания актуальны.

# Критерии готовности
Epic можно архивировать только после финального review и обновления Project Knowledge.
"""


def _db_project(tmp_path: Path, monkeypatch) -> tuple[Session, Project, Path]:
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "CURRENT_STATE.md").write_text("# Current state\n\nBaseline.\n", encoding="utf-8")
    project = Project(
        name="epic-friction",
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
    monkeypatch.setattr(epic_execution, "session_scope", scope)
    monkeypatch.setattr(epic_navigation, "session_scope", scope)
    monkeypatch.setattr(epic_planning, "session_scope", scope)
    monkeypatch.setattr(epic_review, "session_scope", scope)
    return db, project, root


def _complete_analysis_task(db: Session, project: Project, *, worker: str = "phase0") -> None:
    tasks.delegate_current_stage(db, project, worker_id=worker)
    completed = tasks.complete_current_stage(
        db,
        project,
        expected_kind="discovery",
        summary="Verified current source against the Epic assumptions.",
        checks=["source inspection"],
        outcome="analysis_complete",
        result_data={
            "verified_facts": ["Current source matches the durable boundary"],
            "risks": [],
            "proposed_plan": ["Implement selected scope", "Run final whole-Epic review"],
            "proposed_acceptance_criteria": ["Selected scope is complete"],
        },
    )
    assert completed["status"] == "completed"


def _complete_standard_task(
    db: Session,
    project: Project,
    root: Path,
    *,
    worker_prefix: str,
    path: str,
    content: str,
) -> dict:
    tasks.delegate_current_stage(db, project, worker_id=f"{worker_prefix}-impl")
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    review = tasks.complete_current_stage(
        db,
        project,
        expected_kind="implement",
        summary=f"Updated {path}",
        checks=["focused verification"],
    )
    assert review["active_stage"]["kind"] == "review"
    tasks.delegate_current_stage(db, project, worker_id=f"{worker_prefix}-review")
    return tasks.complete_current_stage(
        db,
        project,
        expected_kind="review",
        summary="Independent review passed.",
        checks=["whole contract inspection"],
        verdict="pass",
    )


def _running_epic(tmp_path: Path, monkeypatch):
    db, project, root = _db_project(tmp_path, monkeypatch)
    created = epics.create(root, title="Long lived Epic", spec_markdown=RUSSIAN_SPEC)
    epics.approve(root, key=created["key"])
    epics.start_next(root, key=created["key"])
    _complete_analysis_task(db, project)
    epics.reconcile_complete(
        root,
        key=created["key"],
        summary="Current source matches the approved direction.",
        corrections=[],
    )
    epics.set_plan(
        root,
        key=created["key"],
        work_items=[
            {
                "title": "Implement selected scope",
                "goal": "Implement the complete selected Epic behavior.",
                "acceptance_criteria": ["Selected behavior works end-to-end"],
                "constraints": ["Preserve existing public contracts"],
            }
        ],
    )
    return db, project, root, created["key"]


def test_document_style_spec_edit_is_atomic_versioned_and_compact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, _, root = _db_project(tmp_path, monkeypatch)
    try:
        created = epics.create(root, title="Editable Epic", spec_markdown=RUSSIAN_SPEC)
        epics.record_audit(
            root,
            key=created["key"],
            summary="Audit v1",
            findings=[{"severity": "medium", "problem": "Clarify sequencing"}],
        )
        prepared = epics.prepare_spec_audit(root, key=created["key"])
        assert prepared["audit_state"]["status"] == "current"
        assert "audits" not in prepared
        assert prepared["audit_contract"]["task_stage"] is False

        target = (
            "Спека версионируется, Phase 0 обязателен, задачи идут последовательно, "
            "финальный review проверяет весь Epic."
        )
        replacement = (
            "Спека версионируется, Phase 0 обязателен, обычные Task могут выполняться между "
            "Epic Task, а финальный review проверяет весь Epic."
        )
        edited = epics.edit_spec(
            root,
            key=created["key"],
            expected_spec_version=1,
            edits=[
                {"op": "replace", "target": target, "replacement": replacement},
                {
                    "op": "insert_before",
                    "target": "# Критерии готовности",
                    "text": "## Пауза Epic\nDRAFT/APPROVED Epic не резервирует Task Engine.\n\n",
                },
            ],
            change_summary="Clarify long-lived Epic and Task coexistence.",
        )
        assert edited["current_spec_version"] == 2
        assert edited["revision"]["edit_count"] == 2
        assert edited["revision"]["next_tool"] == "epic_next"
        assert "spec" not in edited
        assert "spec_versions" not in edited

        state = epics.get(root, key=created["key"])
        assert replacement in state["spec"]["content"]
        assert state["audit_state"]["status"] == "stale_after_revision"
        assert state["audit_state"]["reaudit_recommended"] is True
        assert state["audits"][0]["is_current_spec"] is False
        assert "content" not in state["spec_versions"][0]

        old = epics.get_spec_version(root, key=created["key"], version=1)
        assert target in old["spec"]["content"]
        assert old["is_current"] is False

        with pytest.raises(RuntimeError, match="SPEC_VERSION_CONFLICT"):
            epics.edit_spec(
                root,
                key=created["key"],
                expected_spec_version=1,
                edits=[{"op": "delete", "target": "## Пауза Epic\n"}],
                change_summary="Stale edit must fail.",
            )
    finally:
        db.close()
        get_settings.cache_clear()


def test_memory_context_keeps_passive_epic_from_hijacking_normal_task_navigation(
    monkeypatch,
) -> None:
    rows = [
        {
            "key": "E-0001",
            "title": "Large dashboard redesign",
            "status": "draft",
            "execution_spec_version": None,
        }
    ]
    monkeypatch.setattr(context_app.epic_uc, "list_for_project", lambda *args, **kwargs: rows)
    runtime = {
        "active": False,
        "next_action": {"action": "create_task", "tool": "task_create"},
    }

    ordinary = context_app._epic_context("/tmp/project", "Fix payment timeout", runtime)
    assert ordinary["open"][0]["passive"] is True
    assert ordinary["workflow_focus"]["authority"] == "task"
    assert ordinary["workflow_focus"]["tool"] == "task_create"

    explicit = context_app._epic_context("/tmp/project", "Продолжим E-0001", runtime)
    assert explicit["workflow_focus"]["authority"] == "epic"
    assert explicit["workflow_focus"]["tool"] == "epic_next"

    active_runtime = {
        "active": True,
        "next_action": {"action": "continue_stage", "tool": "task_next"},
    }
    active = context_app._epic_context("/tmp/project", "Продолжим E-0001", active_runtime)
    assert active["workflow_focus"]["authority"] == "task"
    assert active["workflow_focus"]["tool"] == "task_next"


def test_running_epic_allows_standalone_task_then_uses_narrow_impact_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, project, root, key = _running_epic(tmp_path, monkeypatch)
    try:
        epics.start_next(root, key=key)
        _complete_standard_task(
            db,
            project,
            root,
            worker_prefix="epic-work",
            path="app.py",
            content="VALUE = 2\n",
        )
        assert epics.next_action(root, key=key)["next_action"]["action"] == "start_final_review"

        standalone = tasks.create_task(
            db,
            project,
            goal="Fix an unrelated production timeout.",
            acceptance_criteria=["Hotfix is reviewed"],
            constraints=["Do not change Epic contract"],
            workflow="standard",
        )
        assert standalone["status"] == "active"

        paused = epics.next_action(root, key=key)
        assert paused["epic"]["status"] == "running"
        assert paused["next_action"]["action"] == "continue_standalone_task"
        assert paused["next_action"]["tool"] == "task_next"

        completed = _complete_standard_task(
            db,
            project,
            root,
            worker_prefix="hotfix",
            path="hotfix.py",
            content="TIMEOUT = 10\n",
        )
        assert completed["status"] == "completed"

        with pytest.raises(RuntimeError, match="Call epic_next"):
            epics.start_next(root, key=key)

        review_needed = epics.next_action(root, key=key)
        assert review_needed["epic"]["status"] == "blocked"
        assert review_needed["next_action"]["action"] == "review_intervening_tasks"

        packet = epics.prepare_intervening_review(root, key=key)
        assert packet["expected_task_keys"] == [standalone["key"]]
        assert packet["review_contract"]["repository_mutation"] == "forbidden"
        assert packet["intervening_tasks"][0]["changed_paths"] == ["hotfix.py"]

        accepted = epics.record_intervening_review(
            root,
            key=key,
            expected_task_keys=packet["expected_task_keys"],
            outcome="unaffected",
            summary="The standalone hotfix does not affect any remaining Epic assumption.",
        )
        assert accepted["intervening_review"]["outcome"] == "unaffected"
        assert epics.next_action(root, key=key)["next_action"]["action"] == "start_final_review"
    finally:
        db.close()
        get_settings.cache_clear()
