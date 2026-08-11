from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.application import epic_execution, epic_lifecycle, epics
from ai_layer.core.config import get_settings
from ai_layer.db.base import Base
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.models import Project, RuntimeEvent, Task, utcnow
from ai_layer.epics.contracts import spec_quality
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
    # Importing Epic ORM models above registers them on the shared Base metadata.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "CURRENT_STATE.md").write_text("# Current state\n\nBaseline.\n", encoding="utf-8")
    project = Project(
        name="epic-demo",
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
            "proposed_plan": ["Implement the selected scope", "Run final whole-Epic review"],
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


def _approved_phase0_plan(tmp_path: Path, monkeypatch):
    db, project, root = _db_project(tmp_path, monkeypatch)
    created = epics.create(root, title="Полный Epic workflow", spec_markdown=RUSSIAN_SPEC)
    approved = epics.approve(root, key=created["key"])
    assert approved["approved_spec_version"] == 1
    phase0 = epics.start_next(root, key=created["key"])
    assert phase0["task"]["workflow_profile"] == "analysis_only"
    assert phase0["task"]["active_stage"]["kind"] == "discovery"
    _complete_analysis_task(db, project)
    reconciled = epics.reconcile_complete(
        root,
        key=created["key"],
        summary="Source requires one obvious wording correction; no product trade-off exists.",
        updated_spec=RUSSIAN_SPEC
        + "\n\n## Проверенная реальность\nТекущий код подтверждён Phase 0.\n",
        corrections=[{"kind": "non_branching", "summary": "Recorded current source reality"}],
    )
    assert reconciled["approved_spec_version"] == 1
    assert reconciled["execution_spec_version"] == 2
    assert reconciled["current_spec_version"] == 2
    assert reconciled["status"] == "planning"
    planned = epics.set_plan(
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
    return db, project, root, created["key"], planned


def test_spec_quality_accepts_russian_contract_and_flags_shortcut_language() -> None:
    quality = spec_quality(RUSSIAN_SPEC)
    assert quality["ready_for_human_review"] is True
    assert quality["missing_recommended_sections"] == []
    warning = spec_quality(RUSSIAN_SPEC + "\nПока что сделаем временно и потом доделаем.\n")
    assert warning["completeness_warnings"]


def test_draft_supports_unlimited_audits_and_immutable_approved_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, _, root = _db_project(tmp_path, monkeypatch)
    try:
        created = epics.create(root, title="Audit me", spec_markdown=RUSSIAN_SPEC)
        first = epics.record_audit(
            root,
            key=created["key"],
            summary="Architecture audit",
            findings=[{"severity": "medium", "problem": "Clarify failure recovery"}],
        )
        second = epics.record_audit(
            root,
            key=created["key"],
            summary="Security audit",
            findings=[],
            scope="security",
        )
        assert first["spec_version"] == second["spec_version"] == 1
        state = epics.get(root, key=created["key"])
        assert len(state["audits"]) == 2
        approved = epics.approve(root, key=created["key"])
        assert approved["approved_spec_version"] == 1
        assert approved["current_spec_version"] == 1
    finally:
        db.close()
        get_settings.cache_clear()


def test_phase0_is_mandatory_before_task_plan_and_creates_execution_spec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, project, root = _db_project(tmp_path, monkeypatch)
    try:
        created = epics.create(root, title="Phase zero", spec_markdown=RUSSIAN_SPEC)
        epics.approve(root, key=created["key"])
        try:
            epics.set_plan(root, key=created["key"], work_items=[{"title": "x", "goal": "y"}])
        except RuntimeError as exc:
            assert "Phase 0" in str(exc)
        else:
            raise AssertionError("implementation plan must be forbidden before Phase 0")
        phase0 = epics.start_next(root, key=created["key"])
        assert phase0["task"]["workflow_profile"] == "analysis_only"
        _complete_analysis_task(db, project)
        result = epics.reconcile_complete(
            root,
            key=created["key"],
            summary="Automatic source reconciliation",
            updated_spec=RUSSIAN_SPEC + "\n\n## Phase 0\nПроверено по source.\n",
            corrections=[
                {"kind": "strong_recommendation", "summary": "Use existing extension point"}
            ],
        )
        assert result["approved_spec_version"] == 1
        assert result["execution_spec_version"] == 2
        assert result["status"] == "planning"
    finally:
        db.close()
        get_settings.cache_clear()


def test_material_phase0_tradeoff_blocks_for_human_decision(tmp_path: Path, monkeypatch) -> None:
    db, project, root = _db_project(tmp_path, monkeypatch)
    try:
        created = epics.create(root, title="Decision", spec_markdown=RUSSIAN_SPEC)
        epics.approve(root, key=created["key"])
        epics.start_next(root, key=created["key"])
        _complete_analysis_task(db, project)
        blocked = epics.reconcile_complete(
            root,
            key=created["key"],
            summary="Two durable product contracts remain genuinely different.",
            human_decisions=[
                {
                    "question": "Which public compatibility contract is desired?",
                    "options": ["preserve legacy", "intentional breaking change"],
                }
            ],
        )
        assert blocked["status"] == "blocked"
        assert blocked["decision_required"]
        action = epics.next_action(root, key=created["key"])["next_action"]
        assert action["action"] == "human_attention_required"
    finally:
        db.close()
        get_settings.cache_clear()


def test_plan_forces_standard_tasks_and_appends_final_whole_epic_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, _, root, key, planned = _approved_phase0_plan(tmp_path, monkeypatch)
    try:
        assert [item["kind"] for item in planned["plan"]] == ["phase0", "work", "final"]
        final = planned["plan"][-1]
        assert "Project Knowledge" in final["goal"]
        assert "whole Epic" in final["goal"] or "whole-Epic" in final["goal"]
        started = epics.start_next(root, key=key)
        assert started["task"]["workflow_profile"] == "standard"
        assert started["task"]["active_stage"]["kind"] == "implement"
    finally:
        db.close()
        get_settings.cache_clear()


def test_repository_drift_requires_targeted_reconciliation_before_next_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, project, root, key, _ = _approved_phase0_plan(tmp_path, monkeypatch)
    try:
        epics.start_next(root, key=key)
        completed = _complete_standard_task(
            db,
            project,
            root,
            worker_prefix="work",
            path="app.py",
            content="VALUE = 2\n",
        )
        assert completed["status"] == "completed"
        next_after_task = epics.next_action(root, key=key)["next_action"]
        assert next_after_task["action"] == "start_final_review"
        (root / "external.py").write_text("EXTERNAL = True\n", encoding="utf-8")
        drift = epics.next_action(root, key=key)
        assert drift["epic"]["status"] == "blocked"
        assert drift["next_action"]["action"] == "start_drift_reconciliation"
        started = epics.start_drift_reconciliation(root, key=key)
        assert started["task"]["workflow_profile"] == "analysis_only"
        _complete_analysis_task(db, project, worker="drift")
        navigation = epics.next_action(root, key=key)["next_action"]
        assert navigation["action"] == "record_drift_reconciliation"
        reconciled = epics.reconcile_complete(
            root,
            key=key,
            summary="External file does not alter remaining final-review assumptions.",
            corrections=[{"kind": "non_branching", "summary": "No remaining contract change"}],
        )
        assert reconciled["status"] == "running"
        assert epics.next_action(root, key=key)["next_action"]["action"] == "start_final_review"
    finally:
        db.close()
        get_settings.cache_clear()


def test_final_epic_gate_requires_docs_and_reviewed_project_knowledge(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db, project, root, key, _ = _approved_phase0_plan(tmp_path, monkeypatch)
    try:
        epics.start_next(root, key=key)
        _complete_standard_task(
            db,
            project,
            root,
            worker_prefix="work",
            path="app.py",
            content="VALUE = 2\n",
        )
        assert epics.next_action(root, key=key)["next_action"]["action"] == "start_final_review"
        final_started = epics.start_next(root, key=key)
        final_task_id = final_started["task"]["id"]
        final_completed = _complete_standard_task(
            db,
            project,
            root,
            worker_prefix="final",
            path="CURRENT_STATE.md",
            content="# Current state\n\nEpic behavior is implemented and reviewed.\n",
        )
        assert final_completed["status"] == "completed"

        first_close = epics.next_action(root, key=key)
        assert first_close["epic"]["status"] == "final_review"
        assert first_close["next_action"]["action"] == "start_final_review"
        assert len(first_close["epic"]["plan"]) == 4

        retry = epics.start_next(root, key=key)
        retry_task = db.get(Task, UUID(retry["task"]["id"]))
        assert retry_task is not None
        # Simulate the existing Task Engine's already-tested Knowledge publication contract for the retry.
        retry_task.status = "completed"
        retry_task.completed_at = utcnow()
        retry_task.final_changes = {
            "added": [],
            "modified": ["CURRENT_STATE.md"],
            "deleted": [],
            "total": 1,
        }
        db.add(
            RuntimeEvent(
                project_id=project.id,
                event_type="KnowledgePublished",
                aggregate_type="task",
                aggregate_id=str(retry_task.id),
                correlation_id="epic-test",
                actor_id="test",
                actor_kind="system",
                interface="test",
                schema_version=1,
                payload={"published": 1, "superseded": 0},
            )
        )
        db.commit()
        closed = epics.next_action(root, key=key)
        assert closed["epic"]["status"] == "completed"
        assert closed["next_action"]["action"] == "archive"
        archived = epics.archive(root, key=key)
        assert archived["status"] == "archived"
        assert archived["archived_at"]
        assert str(final_task_id)
        assert db.scalar(select(Epic).where(Epic.project_id == project.id)) is not None
        assert db.scalars(
            select(EpicPlanItem).where(EpicPlanItem.epic_id == UUID(archived["id"]))
        ).all()
    finally:
        db.close()
        get_settings.cache_clear()
