from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.db.base import Base
from ai_layer.db.models import Project, Task
from ai_layer.tasks import service as tasks
from ai_layer.tasks import views as task_views


def _db_project(tmp_path: Path, *, fragility: str | None = None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir(parents=True)
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    legacy = {} if fragility is None else {"level": fragility, "score": 0, "signals": []}
    project = Project(
        name="inline-micro-demo",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
        project_intelligence={"legacy": legacy},
    )
    db.add(project)
    db.commit()
    return db, project, root


def _init_git(root: Path):
    import subprocess

    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "AI Layer Tests"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)


def test_explicit_micro_natural_language_runs_inline_with_unknown_fragility(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git(root)
        created = tasks.create_task(
            db,
            project,
            goal="Remove the required attribute from the textarea and keep the focused regression covered",
            acceptance_criteria=["textarea no longer blocks empty submission"],
            constraints=[],
            workflow="micro",
        )
        assert created["workflow_version"] == 3
        assert created["workflow_profile"] == "micro"
        assert created["risk_level"] == "low"
        assert created["complexity_level"] == "low"
        assert created["uncertainty_level"] == "low"
        assert created["active_stage"]["execution_mode"] == "inline_micro"
        assert created["active_stage"]["delegation_required"] is False
        assert created["active_stage"]["worker_id"] is None
        assert created["next_action"]["action"] == "inline_micro_implement"
        assert created["next_action"]["orchestrator_contract"]["repository_mutation"] == (
            "allowed_current_micro_stage_only"
        )
        assert created["delegation_contract"]["fresh_subagent_required"] is False
        assert created["delegation_contract"]["orchestrator_edits_forbidden"] is False
        assert created["agent_usage"]["delegated_stages"] == 0

        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Applied localized textarea behavior correction",
            checks=["focused regression test"],
        )
        assert completed["status"] == "completed"
        assert completed["review_round"] == 0
        assert [stage["kind"] for stage in completed["stages"]] == ["implement"]
        assert completed["stages"][0]["execution_mode"] == "inline_micro"
    finally:
        db.close()


def test_inline_micro_real_diff_auto_escalates_to_delegated_review(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git(root)
        created = tasks.create_task(
            db,
            project,
            goal="Adjust the local display behavior",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
        )
        assert created["next_action"]["action"] == "inline_micro_implement"

        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (root / "helper.py").write_text("HELPER = True\n", encoding="utf-8")
        escalated = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Actual change exceeded the intended local envelope",
            checks=["focused check"],
        )
        assert escalated["status"] == "active"
        assert escalated["workflow_profile"] == "standard"
        assert escalated["active_stage"]["kind"] == "review"
        assert escalated["active_stage"]["delegation_required"] is True
        assert escalated["next_action"]["action"] == "delegate_stage"
        assert any("micro escalation" in reason for reason in escalated["risk_reasons"])
    finally:
        db.close()


def test_high_risk_or_fragile_micro_request_never_gets_inline_authority(tmp_path: Path):
    db, project, _root = _db_project(tmp_path)
    try:
        high_risk = tasks.create_task(
            db,
            project,
            goal="Remove required from authentication permission form",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
            risk="low",
        )
        assert high_risk["workflow_profile"] == "standard"
        assert high_risk["risk_level"] == "high"
        assert high_risk["active_stage"]["delegation_required"] is True
        tasks.cancel_task(db, project, reason="test")
    finally:
        db.close()

    db, project, _root = _db_project(tmp_path / "fragile", fragility="medium")
    try:
        fragile = tasks.create_task(
            db,
            project,
            goal="Adjust a local label",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
        )
        assert fragile["workflow_profile"] == "standard"
        assert fragile["risk_level"] == "normal"
        assert fragile["active_stage"]["delegation_required"] is True
    finally:
        db.close()


def test_review_contract_mentions_project_knowledge_only_when_drafts_exist(
    tmp_path: Path, monkeypatch
):
    db, project, root = _db_project(tmp_path, fragility="low")
    try:
        tasks.create_task(
            db,
            project,
            goal="Change application behavior",
            acceptance_criteria=[],
            constraints=[],
            workflow="standard",
        )
        tasks.delegate_current_stage(db, project, worker_id="impl")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Changed behavior",
            checks=["focused test"],
        )
        assert review["active_stage"]["kind"] == "review"
        assert "project_knowledge_review" not in review["delegation_contract"]
        assert not any(
            "knowledge_list" in item for item in review["delegation_contract"]["requirements"]
        )

        monkeypatch.setattr(task_views, "has_task_drafts", lambda *args, **kwargs: True)
        task = db.scalar(select(Task).where(Task.project_id == project.id, Task.status == "active"))
        assert task is not None
        with_drafts = task_views.task_to_dict(db, task)
        assert with_drafts["delegation_contract"]["project_knowledge_review"]["tool"] == (
            "knowledge_list"
        )
        assert any(
            "knowledge_list" in item for item in with_drafts["delegation_contract"]["requirements"]
        )
    finally:
        db.close()
