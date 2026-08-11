from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.agents.policy import install_cursor_profiles
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.integrations.templates import global_bootstrap_workflow, workflow
from ai_layer.tasks import service as tasks


def _db_project(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="demo",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()
    return db, project, root


def test_critical_orchestrator_contract_has_one_compact_global_owner_without_project_duplication(tmp_path: Path):
    project_text = workflow(tmp_path)
    global_text = global_bootstrap_workflow()

    assert "AI Layer orchestrator boundary" in global_text
    assert "top-level chat coordinates only" in global_text
    assert "Never edit repository files or mutate external systems yourself" in global_text
    assert "task_stage_delegate" in global_text
    assert "never do the stage yourself as fallback" in global_text
    assert "smallest coherent change" in global_text
    assert "never claim a check passed unless it ran" in global_text
    assert len(global_text.encode("utf-8")) < 2600

    # Standard projects no longer materialize a text workflow bridge. This renderer survives only
    # as a tiny compatibility helper for legacy callers; sparse project MCP config owns identity.
    assert "project binding (legacy compatibility)" in project_text
    assert "Canonical project root" in project_text
    assert "global native bootstrap and MCP Task Layer" in project_text
    assert "orchestrator boundary" not in project_text
    assert len(project_text.encode("utf-8")) < 500


def test_task_navigation_repeats_orchestrator_contract_at_delegation_and_completion_boundary(tmp_path: Path):
    db, project, _root = _db_project(tmp_path)
    try:
        tasks.create_task(
            db,
            project,
            goal="Change application behavior",
            acceptance_criteria=["VALUE changes safely"],
            constraints=[],
        )
        before = tasks.next_task_action(db, project)
        assert before["orchestrator_contract"]["role"] == "orchestrator"
        assert before["orchestrator_contract"]["repository_mutation"] == "forbidden"
        assert before["next_action"]["action"] == "delegate_stage"
        assert before["next_action"]["orchestrator_contract"]["repository_mutation"] == "forbidden"
        assert "START that native worker" in before["next_action"]["message"]
        assert "orchestrator fallback implementation" in before["next_action"]["forbidden"]

        delegated = tasks.delegate_current_stage(db, project, worker_id="implementer-one")
        handoff = delegated["orchestrator_handoff"]
        assert handoff["next_host_action"] == "START_THE_DELEGATED_WORKER_NOW"
        assert handoff["worker_id"] == "implementer-one"
        assert handoff["repository_mutation"] == "forbidden"
        assert handoff["delegation_contract"]["worker_role_contract"].startswith(
            "This delegated worker is the only actor allowed"
        )
        assert delegated["next_action"]["completion_precondition"].startswith(
            "The bound worker actually ran this stage"
        )

        after = tasks.next_task_action(db, project)
        assert after["next_action"]["action"] == "record_stage_result"
        assert "If the worker has not actually run yet, start it now" in after["next_action"]["message"]
        assert "completion from orchestrator-authored work" in after["next_action"]["forbidden"]
        assert "actually ran and returned" in after["next_action"]["completion_precondition"]
    finally:
        db.close()


def test_cursor_worker_profiles_have_explicit_role_contracts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    user_home = tmp_path / "user-home"
    install_cursor_profiles(user_home)

    writable = (user_home / ".cursor" / "agents" / "ai-layer-economy-write.md").read_text(encoding="utf-8")
    readonly = (user_home / ".cursor" / "agents" / "ai-layer-economy-readonly.md").read_text(encoding="utf-8")

    assert "CRITICAL ROLE CONTRACT" in writable
    assert "delegated WRITABLE stage worker" in writable
    assert "belong to you, not the parent orchestrator" in writable
    assert "return the blocker" in writable

    assert "CRITICAL ROLE CONTRACT" in readonly
    assert "You are READ-ONLY" in readonly
    assert "Never edit repository files" in readonly
