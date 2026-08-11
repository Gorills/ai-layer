from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.application import (
    epic_execution,
    epic_lifecycle,
    epic_navigation,
    epic_planning,
    epics,
)
from ai_layer.core.config import get_settings
from ai_layer.db.base import Base
from ai_layer.db.epic_models import Epic
from ai_layer.db.models import Project
from ai_layer.tasks import service as tasks

SPEC = """# Цель
Реализовать полный Epic workflow.

# Конечный результат
Пользователь получает готовый durable workflow.

# Принятые решения
Epic планирует, Task Engine выполняет задачи.

# Функциональные требования
Согласование, Phase 0, задачи, review и archive обязательны.

# Критерии приёмки
Полный выбранный scope реализован и проверен.

# Критерии готовности
Документация и Project Knowledge актуальны, final review прошёл.
"""


def _environment(tmp_path: Path, monkeypatch) -> tuple[Session, Project, Path]:
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="human-gates",
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

    for module in (epic_lifecycle, epic_execution, epic_navigation, epic_planning):
        monkeypatch.setattr(module, "session_scope", scope)
    return db, project, root


def _complete_analysis(db: Session, project: Project, worker: str) -> None:
    tasks.delegate_current_stage(db, project, worker_id=worker)
    result = tasks.complete_current_stage(
        db,
        project,
        expected_kind="discovery",
        summary="Current source inspected.",
        checks=["source inspection"],
        outcome="analysis_complete",
        result_data={
            "verified_facts": ["Source inspected"],
            "risks": [],
            "proposed_plan": ["Implement selected scope"],
            "proposed_acceptance_criteria": ["Selected scope complete"],
        },
    )
    assert result["status"] == "completed"


def _phase0_ready(db: Session, project: Project, root: Path) -> str:
    created = epics.create(root, title="Human gates", spec_markdown=SPEC)
    epics.approve(root, key=created["key"])
    epics.start_next(root, key=created["key"])
    _complete_analysis(db, project, "phase0")
    return created["key"]


def test_approved_spec_can_be_reaudited_and_revision_requires_reapproval(
    tmp_path: Path, monkeypatch
) -> None:
    db, _, root = _environment(tmp_path, monkeypatch)
    try:
        created = epics.create(root, title="Re-audit", spec_markdown=SPEC)
        approved = epics.approve(root, key=created["key"])
        assert approved["status"] == "approved"

        audit = epics.record_audit(
            root,
            key=created["key"],
            summary="Independent audit after approval but before execution.",
            findings=[{"severity": "medium", "problem": "Clarify one contract"}],
        )
        assert audit["spec_version"] == approved["approved_spec_version"] == 1

        revised = epics.revise_spec(
            root,
            key=created["key"],
            spec_markdown=SPEC + "\n## Уточнение\nКонтракт уточнён после аудита.\n",
            change_summary="Resolve post-approval audit finding.",
        )
        assert revised["status"] == "draft"
        assert revised["current_spec_version"] == 2
        assert revised["approved_spec_version"] is None
        assert revised["execution_spec_version"] is None
        assert epics.next_action(root, key=created["key"])["next_action"]["action"] == (
            "audit_revise_or_approve"
        )
    finally:
        db.close()
        get_settings.cache_clear()


def test_phase0_human_decision_resumes_through_reconciliation(tmp_path: Path, monkeypatch) -> None:
    db, project, root = _environment(tmp_path, monkeypatch)
    try:
        key = _phase0_ready(db, project, root)
        blocked = epics.reconcile_complete(
            root,
            key=key,
            summary="A material public-contract trade-off remains.",
            human_decisions=[
                {"question": "Compatibility contract?", "options": ["legacy", "new"]}
            ],
        )
        assert blocked["status"] == "blocked"
        navigation = epics.next_action(root, key=key)["next_action"]
        assert navigation["action"] == "human_attention_required"
        assert navigation["resolution_tool"] == "epic_reconcile_complete"

        resolved = epics.reconcile_complete(
            root,
            key=key,
            summary="User selected the legacy-compatible contract.",
            updated_spec=SPEC + "\n## Решение Phase 0\nСохраняем legacy compatibility.\n",
            corrections=[{"kind": "human_resolution", "summary": "Preserve legacy contract"}],
            human_decisions=[],
        )
        assert resolved["status"] == "planning"
        assert resolved["decision_required"] == []
        assert resolved["execution_spec_version"] == 2
    finally:
        db.close()
        get_settings.cache_clear()


def test_drift_human_decision_preserves_reconciliation_task_until_resolved(
    tmp_path: Path, monkeypatch
) -> None:
    db, project, root = _environment(tmp_path, monkeypatch)
    try:
        key = _phase0_ready(db, project, root)
        epics.reconcile_complete(root, key=key, summary="Phase 0 matched source.")
        epics.set_plan(
            root,
            key=key,
            work_items=[
                {
                    "title": "Implement selected scope",
                    "goal": "Implement selected scope.",
                    "acceptance_criteria": ["Selected scope complete"],
                    "constraints": [],
                }
            ],
        )

        (root / "external.py").write_text("EXTERNAL = True\n", encoding="utf-8")
        drift = epics.next_action(root, key=key)
        assert drift["next_action"]["action"] == "start_drift_reconciliation"
        started = epics.start_drift_reconciliation(root, key=key)
        _complete_analysis(db, project, "drift")

        blocked = epics.reconcile_complete(
            root,
            key=key,
            summary="Drift creates a material API choice.",
            human_decisions=[{"question": "API choice?", "options": ["A", "B"]}],
        )
        assert blocked["status"] == "blocked"
        assert blocked["drift_task_id"] == started["task"]["id"]
        navigation = epics.next_action(root, key=key)["next_action"]
        assert navigation["resolution_tool"] == "epic_reconcile_complete"

        resolved = epics.reconcile_complete(
            root,
            key=key,
            summary="User selected API A; remaining plan stays valid.",
            updated_spec=SPEC + "\n## Drift decision\nUse API A.\n",
            human_decisions=[],
        )
        assert resolved["status"] == "running"
        assert resolved["drift_task_id"] is None
        assert resolved["decision_required"] == []
        assert db.query(Epic).count() == 1
    finally:
        db.close()
        get_settings.cache_clear()


def test_phase0_post_completion_change_is_not_silently_accepted(tmp_path: Path, monkeypatch) -> None:
    db, project, root = _environment(tmp_path, monkeypatch)
    try:
        key = _phase0_ready(db, project, root)
        (root / "after-phase0.py").write_text("CHANGED_AFTER_REVIEW = True\n", encoding="utf-8")
        reconciled = epics.reconcile_complete(root, key=key, summary="Phase 0 findings recorded.")
        assert reconciled["status"] == "planning"
        epics.set_plan(
            root,
            key=key,
            work_items=[
                {
                    "title": "Implement scope",
                    "goal": "Implement scope.",
                    "acceptance_criteria": ["Scope complete"],
                    "constraints": [],
                }
            ],
        )
        navigation = epics.next_action(root, key=key)
        assert navigation["epic"]["status"] == "blocked"
        assert navigation["next_action"]["action"] == "start_drift_reconciliation"
    finally:
        db.close()
        get_settings.cache_clear()
