from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.agents.policy import install_cursor_profiles
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.domain.static_policy import STATIC_POLICY_RULES
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


def test_global_bootstrap_is_project_intelligence_first_and_host_native(tmp_path: Path):
    project_text = workflow(tmp_path)
    global_text = global_bootstrap_workflow()

    assert "AI Layer control-plane boundary" in global_text
    assert "host agent runtime remains the execution engine" in global_text
    assert "project_status" in global_text
    assert "project_search" in global_text
    assert "knowledge_search" in global_text
    assert (
        "Native read/edit/search/shell/test/subagent capabilities remain available" in global_text
    )
    assert "managed Tasks and Epics remain durable workflows" in global_text
    assert "Current repository source is final code truth" in global_text
    assert "Never stash, reset, restore, discard or commit user changes" in global_text
    assert "memory_context(task=<actual user task>" not in global_text
    assert "top-level chat is the ORCHESTRATOR" not in global_text

    assert "Mandatory engineering discipline" in global_text
    assert "at or below 100 words" in global_text
    assert "at or below 60 words" in global_text
    assert global_text.count("Mandatory engineering discipline") == 1
    for rule in STATIC_POLICY_RULES:
        assert f"- {rule}" in global_text

    assert "project binding (legacy compatibility)" in project_text
    assert "Canonical project root" in project_text
    assert "global native bootstrap and MCP Project Intelligence/control-plane tools" in project_text
    assert "## AI Layer control-plane boundary" not in project_text
    assert "Mandatory engineering discipline" not in project_text


def test_task_navigation_repeats_orchestrator_contract_at_delegation_and_completion_boundary(
    tmp_path: Path,
):
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
        assert (
            before["next_action"]["orchestrator_contract"]["repository_mutation"]
            == "forbidden_during_delegated_stage"
        )
        assert "START that native worker" in before["next_action"]["message"]
        assert "orchestrator fallback implementation" in before["next_action"]["forbidden"]

        delegated = tasks.delegate_current_stage(db, project, worker_id="implementer-one")
        handoff = delegated["orchestrator_handoff"]
        assert handoff["next_host_action"] == "START_THE_DELEGATED_WORKER_NOW"
        assert handoff["worker_id"] == "implementer-one"
        assert handoff["repository_mutation"] == "forbidden_during_delegated_stage"
        assert handoff["delegation_contract"]["worker_role_contract"].startswith(
            "This delegated worker is the only actor allowed"
        )
        assert delegated["next_action"]["completion_precondition"].startswith(
            "The bound worker actually ran this stage"
        )

        after = tasks.next_task_action(db, project)
        assert after["next_action"]["action"] == "record_stage_result"
        assert (
            "If the worker has not actually run yet, start it now"
            in after["next_action"]["message"]
        )
        assert "completion from orchestrator-authored work" in after["next_action"]["forbidden"]
        assert "actually ran and returned" in after["next_action"]["completion_precondition"]
    finally:
        db.close()


def test_cursor_worker_profiles_have_explicit_role_contracts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    user_home = tmp_path / "user-home"
    install_cursor_profiles(user_home)

    writable = (user_home / ".cursor" / "agents" / "ai-layer-economy-write.md").read_text(
        encoding="utf-8"
    )
    readonly = (user_home / ".cursor" / "agents" / "ai-layer-economy-readonly.md").read_text(
        encoding="utf-8"
    )

    assert "CRITICAL ROLE CONTRACT" in writable
    assert "delegated WRITABLE stage worker" in writable
    assert "belong to you, not the parent orchestrator" in writable
    assert "return the blocker" in writable

    assert "CRITICAL ROLE CONTRACT" in readonly
    assert "You are READ-ONLY" in readonly
    assert "Never edit repository files" in readonly
