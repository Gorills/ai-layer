from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.core.config import get_settings
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.tasks import service as tasks
from ai_layer.tasks.agent_policy import install_cursor_profiles


def _db_project(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="adaptive-demo",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
        project_intelligence={"legacy": {"level": "low", "score": 0, "signals": []}},
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


def test_standard_clean_review_completes_without_noop_fixer(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Change application behavior", acceptance_criteria=[], constraints=[]
        )
        assert created["workflow_profile"] == "standard"
        tasks.delegate_current_stage(db, project, worker_id="impl")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db, project, expected_kind="implement", summary="Changed value", checks=["focused test"]
        )
        assert review["active_stage"]["kind"] == "review"
        tasks.delegate_current_stage(db, project, worker_id="review")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="review",
            summary="Clean independent review",
            checks=["inspection"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        assert completed["active_stage"] is None
        assert [stage["kind"] for stage in completed["stages"]] == ["implement", "review"]
        assert completed["fix_round"] == 0
    finally:
        db.close()


def test_discovery_first_is_read_only_then_implements_without_fake_fixer(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Investigate current app behavior before implementing a safe change",
            acceptance_criteria=["understand existing behavior", "then change VALUE"],
            constraints=[],
        )
        assert created["workflow_profile"] == "discovery_first"
        assert created["active_stage"]["kind"] == "discovery"
        assert created["active_stage"]["agent_policy"]["readonly"] is True
        assert created["delegation_contract"]["repository_mode"] == "read-only"
        tasks.delegate_current_stage(db, project, worker_id="discovery-worker")
        discovered = tasks.complete_current_stage(
            db,
            project,
            expected_kind="discovery",
            summary="Verified the existing VALUE path and identified the safe edit.",
            checks=["read source", "traced entrypoint"],
            outcome="ready_for_implementation",
            result_data={
                "verified_facts": ["app.py owns VALUE"],
                "risks": ["low local regression risk"],
                "proposed_plan": ["change app.py", "run focused test"],
                "proposed_acceptance_criteria": ["VALUE becomes 2"],
            },
        )
        assert discovered["active_stage"]["kind"] == "implement"
        assert discovered["discovery_result"]["verified_facts"] == ["app.py owns VALUE"]
        tasks.delegate_current_stage(db, project, worker_id="impl-worker")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Applied discovered plan",
            checks=["focused test"],
        )
        tasks.delegate_current_stage(db, project, worker_id="review-worker")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="review",
            summary="Implementation matches discovery and task contract",
            checks=["inspection"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        assert [stage["kind"] for stage in completed["stages"]] == [
            "discovery",
            "implement",
            "review",
        ]
        assert completed["fix_round"] == 0
    finally:
        db.close()


def test_analysis_only_discovery_completes_without_implementation_or_fixer(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Analyze current app architecture and risks",
            acceptance_criteria=[],
            constraints=[],
        )
        assert created["workflow_profile"] == "analysis_only"
        assert created["active_stage"]["kind"] == "discovery"
        tasks.delegate_current_stage(db, project, worker_id="analysis-worker")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="discovery",
            summary="Analysis complete",
            checks=["source inspection"],
            outcome="analysis_complete",
            result_data={"verified_facts": ["single app entrypoint"], "risks": []},
        )
        assert completed["status"] == "completed"
        assert [stage["kind"] for stage in completed["stages"]] == ["discovery"]
        assert completed["review_round"] == 0
        assert completed["fix_round"] == 0
    finally:
        db.close()


def test_micro_low_risk_one_file_change_completes_with_one_worker(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git(root)
        created = tasks.create_task(
            db, project, goal="Fix one line typo in app.py", acceptance_criteria=[], constraints=[]
        )
        assert created["workflow_profile"] == "micro"
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["agent_policy"]["tier"] == "economy"
        assert nav["next_action"]["agent_policy"]["profile"] == "ai-layer-economy-write"
        tasks.delegate_current_stage(db, project, worker_id="micro-worker")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Fixed localized line",
            checks=["focused check"],
        )
        assert completed["status"] == "completed"
        assert [stage["kind"] for stage in completed["stages"]] == ["implement"]
        assert completed["review_round"] == 0
    finally:
        db.close()


def test_micro_envelope_excess_auto_escalates_to_standard_review(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git(root)
        created = tasks.create_task(
            db,
            project,
            goal="Small fix in app.py",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
        )
        assert created["workflow_profile"] == "micro"
        tasks.delegate_current_stage(db, project, worker_id="micro-worker")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (root / "helper.py").write_text("HELPER = True\n", encoding="utf-8")
        escalated = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Change grew beyond expected scope",
            checks=["focused check"],
        )
        assert escalated["status"] == "active"
        assert escalated["workflow_profile"] == "standard"
        assert escalated["active_stage"]["kind"] == "review"
        assert any("micro escalation" in reason for reason in escalated["risk_reasons"])
        assert escalated["active_stage"]["agent_policy"]["tier"] == "balanced"
    finally:
        db.close()


def test_high_risk_review_requests_strong_readonly_profile(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Fix authentication permission security bug",
            acceptance_criteria=[],
            constraints=[],
        )
        assert created["risk_level"] == "high"
        assert created["active_stage"]["agent_policy"]["tier"] == "balanced"
        tasks.delegate_current_stage(db, project, worker_id="impl")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Security fix implemented",
            checks=["focused security test"],
        )
        assert review["active_stage"]["kind"] == "review"
        assert review["active_stage"]["agent_policy"]["tier"] == "strong"
        assert review["active_stage"]["agent_policy"]["profile"] == "ai-layer-strong-readonly"
    finally:
        db.close()


def test_cursor_agent_profiles_are_machine_side_and_do_not_overwrite_unmanaged(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    cursor_home = tmp_path / "user-home"
    unmanaged = cursor_home / ".cursor" / "agents" / "ai-layer-strong-readonly.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("user owned\n", encoding="utf-8")
    result = install_cursor_profiles(cursor_home)
    try:
        assert str(unmanaged) in result["skipped_unmanaged"]
        assert unmanaged.read_text(encoding="utf-8") == "user owned\n"
        economy = cursor_home / ".cursor" / "agents" / "ai-layer-economy-write.md"
        text = economy.read_text(encoding="utf-8")
        assert "model: composer-2.5[fast=false]" in text
        assert "readonly: false" in text
        assert (tmp_path / "ai-home" / "agent-policy.json").exists()
    finally:
        get_settings.cache_clear()


def test_micro_one_file_large_rewrite_escalates_to_review(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git(root)
        created = tasks.create_task(
            db,
            project,
            goal="Fix one line in app.py",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
        )
        tasks.delegate_current_stage(db, project, worker_id="micro-large")
        (root / "app.py").write_text(
            "\n".join(f"VALUE_{i} = {i}" for i in range(80)) + "\n", encoding="utf-8"
        )
        escalated = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Rewrite exceeded intended scope",
            checks=["focused check"],
        )
        assert escalated["status"] == "active"
        assert escalated["workflow_profile"] == "standard"
        assert escalated["active_stage"]["kind"] == "review"
        assert any("changed lines" in reason for reason in escalated["risk_reasons"])
        impl = escalated["stages"][0]
        assert impl["changes"]["line_delta"]["total"] > 12
    finally:
        db.close()


def test_product_ui_wording_does_not_false_positive_as_production_high_risk(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Update product card layout and text",
            acceptance_criteria=["Product page remains responsive"],
            constraints=[],
        )
        assert created["risk_level"] == "normal"
    finally:
        db.close()


def test_unknown_fragility_never_auto_selects_micro(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        project.project_intelligence = {}
        db.commit()
        _init_git(root)
        created = tasks.create_task(
            db, project, goal="Fix one line typo in app.py", acceptance_criteria=[], constraints=[]
        )
        assert created["workflow_profile"] == "standard"
        assert created["risk_level"] == "normal"
    finally:
        db.close()


def test_discovery_rejects_external_mutation_actions(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Analyze current app architecture and risks",
            acceptance_criteria=[],
            constraints=[],
        )
        assert created["active_stage"]["kind"] == "discovery"
        tasks.delegate_current_stage(db, project, worker_id="discovery-readonly")
        import pytest

        with pytest.raises(ValueError, match="Read-only discovery"):
            tasks.complete_current_stage(
                db,
                project,
                expected_kind="discovery",
                summary="Tried to change staging",
                checks=["inspection"],
                outcome="analysis_complete",
                external_actions=[
                    {
                        "kind": "mutation",
                        "target": "staging-config",
                        "summary": "changed config",
                    }
                ],
            )
    finally:
        db.close()


def test_agent_policy_can_be_reconfigured_machine_side(tmp_path: Path, monkeypatch):
    from ai_layer.tasks import agent_policy

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    try:
        configured = agent_policy.configure_policy(
            economy_model="composer-2.5[fast=false]",
            balanced_model="gpt-5.6-luna",
            strong_model="gpt-5.6-sol",
            default_cost_policy="economy",
        )
        assert configured["cursor_models"]["balanced"] == "gpt-5.6-luna"
        assert configured["cursor_models"]["strong"] == "gpt-5.6-sol"
        assert Path(configured["path"]).is_file()
    finally:
        get_settings.cache_clear()


def test_discovery_can_run_write_producing_check_in_disposable_sandbox(tmp_path: Path):
    import sys

    db, project, root = _db_project(tmp_path)
    try:
        _init_git(root)
        created = tasks.create_task(
            db,
            project,
            goal="Analyze current app architecture and risks",
            acceptance_criteria=[],
            constraints=[],
            workflow="analysis_only",
        )
        assert created["active_stage"]["kind"] == "discovery"
        tasks.delegate_current_stage(db, project, worker_id="discovery-sandbox")
        result = tasks.run_current_review_check(
            db,
            project,
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; Path('generated.tmp').write_text('sandbox-only', encoding='utf-8')",
            ],
        )
        assert result["exit_code"] == 0
        assert not (root / "generated.tmp").exists()
        sandbox_path = Path(result["sandbox_path"])
        assert (sandbox_path / "generated.tmp").read_text(encoding="utf-8") == "sandbox-only"

        cancelled = tasks.cancel_task(db, project, reason="discovery test cleanup")
        assert cancelled["status"] == "cancelled"
        assert not sandbox_path.exists()
    finally:
        db.close()


def test_task_create_uses_machine_default_cost_policy_and_persists_requested_model(
    tmp_path: Path, monkeypatch
):
    from ai_layer.tasks import agent_policy

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    db, project, _ = _db_project(tmp_path)
    try:
        agent_policy.configure_policy(
            economy_model="economy-model",
            balanced_model="balanced-model-v1",
            strong_model="strong-model",
            default_cost_policy="balanced",
        )
        created = tasks.create_task(
            db,
            project,
            goal="Change application behavior",
            acceptance_criteria=[],
            constraints=[],
        )
        assert created["cost_policy"] == "balanced"
        assert created["active_stage"]["agent_policy"]["tier"] == "balanced"
        assert created["active_stage"]["agent_policy"]["cursor_model"] == "balanced-model-v1"

        # Policy changes affect future stages/tasks, not the historical request already bound to this stage.
        agent_policy.configure_policy(balanced_model="balanced-model-v2")
        current = tasks.current_task(db, project)
        assert (
            current["task"]["active_stage"]["agent_policy"]["cursor_model"] == "balanced-model-v1"
        )
    finally:
        db.close()
        get_settings.cache_clear()


def test_ui_delete_label_does_not_auto_classify_as_high_risk(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Rename Delete button label in product card",
            acceptance_criteria=["Only visible copy changes"],
            constraints=[],
        )
        assert created["risk_level"] != "high"
        assert created["workflow_profile"] == "micro"
    finally:
        db.close()


def test_explicit_start_with_review_phrase_selects_discovery_first(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Начать с ревью текущего модуля, затем исправить найденную причину ошибки",
            acceptance_criteria=[],
            constraints=[],
        )
        assert created["workflow_profile"] == "discovery_first"
        assert created["active_stage"]["kind"] == "discovery"
    finally:
        db.close()


def test_task_durable_payloads_redact_common_secrets(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Update integration token=super-secret-value",
            acceptance_criteria=["Authorization: Bearer abcdefghijklmnopqrstuvwxyz"],
            constraints=[],
            risk="normal",
            workflow="standard",
        )
        assert "super-secret-value" not in created["goal"]
        assert "abcdefghijklmnopqrstuvwxyz" not in " ".join(created["acceptance_criteria"])
        tasks.delegate_current_stage(db, project, worker_id="redaction-impl")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        reviewed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Used api_key=top-secret-key safely",
            checks=["Authorization: Bearer another-secret-token"],
            result_data={"note": "password=hunter2"},
        )
        impl = reviewed["stages"][0]
        serialized = str(impl)
        assert "top-secret-key" not in serialized
        assert "another-secret-token" not in serialized
        assert "hunter2" not in serialized
        assert "<redacted>" in serialized
    finally:
        db.close()


def test_worker_id_is_bounded_before_database_write():
    try:
        tasks._validate_worker_id(None, None, "w" * 129)  # type: ignore[arg-type]
    except ValueError as exc:
        assert "128-character limit" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("oversized worker id must be rejected")
