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


def test_critical_orchestrator_contract_is_readable_mandatory_first_call_kernel(tmp_path: Path):
    project_text = workflow(tmp_path)
    global_text = global_bootstrap_workflow()

    assert "Mandatory AI Layer role boundary" in global_text
    assert "These rules are mandatory" in global_text
    assert "top-level chat is the ORCHESTRATOR" in global_text
    assert "MUST NOT edit repository files or mutate external systems" in global_text
    assert "`inline_micro_implement`" in global_text
    assert "IMPLEMENT and FIX stages belong to one explicitly bound writable worker" in global_text
    assert "DISCOVERY and REVIEW stages belong to one explicitly bound read-only worker" in global_text
    assert "must never perform a delegated stage as fallback" in global_text
    assert "STOP and report the blocker" in global_text

    assert "Mandatory startup and navigation" in global_text
    assert "FIRST project-related tool call MUST be `memory_context" in global_text
    assert "Until `memory_context` succeeds, you MUST NOT read/search/grep project files" in global_text
    assert "Do not bypass this rule for a small, obvious, read-only or diagnostic request" in global_text
    assert "canonical project root returned by AI Layer" in global_text
    assert 'skill_get(slug="ai-layer-workflow"' in global_text
    assert 'section="core"' in global_text
    assert "once per chat" in global_text
    assert "call `epic_next`; otherwise call `task_next`" in global_text
    assert "NEVER infer the next stage from chat history or memory" in global_text
    assert "After every Task/Epic transition" in global_text
    assert "dirty worktree is a valid baseline" in global_text
    assert "Never stash, reset, restore, discard or commit user changes" in global_text
    assert "Native Agent Skills provide domain expertise" in global_text

    assert "Mandatory engineering discipline" in global_text
    assert "at or below 100 words" in global_text
    assert "at or below 60 words" in global_text
    assert global_text.count("Mandatory engineering discipline") == 1
    for rule in STATIC_POLICY_RULES:
        assert f"- {rule}" in global_text

    # This is a comprehension budget, not byte golf. Procedure/state/domain expertise still remain
    # progressive, but the mandatory first-call discipline must be readable by weak models.
    assert len(global_text.encode("utf-8")) < 9000

    # Standard projects still do not materialize a duplicate text workflow bridge.
    assert "project binding (legacy compatibility)" in project_text
    assert "Canonical project root" in project_text
    assert "global native bootstrap and MCP Task Layer" in project_text
    assert "## Mandatory AI Layer role boundary" not in project_text
    assert len(project_text.encode("utf-8")) < 500


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
