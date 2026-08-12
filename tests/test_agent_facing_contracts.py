from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ai_layer.application import epics as epic_app
from ai_layer.application.tasks import _idle_managed_task_payload
from ai_layer.domain.agent_contract import agent_runtime_contract
from ai_layer.domain.orchestrator import mcp_bootstrap_instructions, native_bootstrap_markdown
from ai_layer.domain.static_policy import static_policy_markdown
from ai_layer.integrations.global_install import GLOBAL_BOOTSTRAP_MARKER, GLOBAL_BOOTSTRAP_VERSION
from ai_layer.integrations.status import _bootstrap_file_status, _bootstrap_version_current

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_contract_names_current_control_plane_surfaces() -> None:
    contract = agent_runtime_contract()
    assert contract["architecture"] == "project_intelligence_control_plane"
    assert contract["startup"]["tool"] == "project_status"
    assert contract["navigation"]["unknown_location"] == "project_search"
    assert contract["project_map"] == {
        "read": "project_search",
        "update": "project_map_reconcile",
    }
    assert contract["knowledge"]["read"] == "knowledge_search"
    assert contract["decisions"]["read"] == "decision_search"
    assert contract["skills"]["routing_owner"] == "host-native"
    assert contract["managed_work"]["task_resume"] == "task_next"
    assert contract["managed_work"]["epic_resume"] == "epic_next"
    assert contract["legacy"]["memory_context"] == "compatibility_only"
    assert contract["legacy"]["memory_search"] == "alias_of_knowledge_search"
    precedence = contract["precedence"]
    assert precedence.index("current AI Layer runtime/tool contracts") < precedence.index(
        "stored Task/Epic prose and historical documentation"
    )


def test_bootstrap_and_static_policy_do_not_restore_legacy_permission_layer() -> None:
    text = "\n".join(
        [native_bootstrap_markdown(), mcp_bootstrap_instructions(), static_policy_markdown()]
    ).casefold()
    assert "project_status" in text
    assert "project_search" in text
    assert "project_map_reconcile" in text
    assert "knowledge_search" in text
    assert "host-native" in text
    assert "reuse the initial `memory_context`" not in text
    assert "create a task before implementation" not in text
    assert "edit repository before task_create" not in text
    assert "load only the relevant skill section" not in text


def test_idle_managed_task_contract_is_native_first_and_task_create_is_optional() -> None:
    result = _idle_managed_task_payload({"active": False, "state": "no_active_task"})
    action = result["next_action"]
    assert action["action"] == "host_native"
    assert action["tool"] is None
    assert action["managed_option"]["tool"] == "task_create"
    assert action["managed_option"]["required"] == ["goal"]
    assert "not required" in result["agent_contract"]["managed_work"]["idle"].casefold()


def test_epic_application_navigation_always_attaches_current_runtime_contract(monkeypatch) -> None:
    monkeypatch.setattr(epic_app, "_next_action", lambda *args, **kwargs: {"state": "running"})
    result = epic_app.next_action("/tmp/project", key="E-0001")
    assert result["state"] == "running"
    assert result["agent_contract"]["startup"]["tool"] == "project_status"
    assert result["agent_contract"]["project_map"]["update"] == "project_map_reconcile"


def test_product_skills_match_live_task_and_epic_state_machines() -> None:
    workflow = (ROOT / "src/ai_layer/builtin_skills/ai-layer-workflow.md").read_text(
        encoding="utf-8"
    )
    epics = (ROOT / "src/ai_layer/builtin_skills/epics.md").read_text(encoding="utf-8")
    assert "`project_status`" in workflow
    assert "`knowledge_search`" in workflow
    assert "review-gated managed" in workflow
    assert "`epic_next`" in epics
    assert "`project_map_reconcile`" in epics
    assert "ProjectMapReconciled" in epics
    assert "ordered sequential" in epics
    assert "generic parallel DAG" in epics
    assert "Create a task DAG" not in epics


def test_installed_bootstrap_readiness_requires_current_version_marker(tmp_path: Path) -> None:
    deps = SimpleNamespace(
        managed_start="<!-- AI-LAYER:START -->",
        global_bootstrap_marker=GLOBAL_BOOTSTRAP_MARKER,
    )
    path = tmp_path / "AGENTS.md"
    path.write_text("<!-- AI-LAYER:START -->\nold instructions\n", encoding="utf-8")
    assert _bootstrap_file_status(path, deps) is False
    assert _bootstrap_version_current(path, deps) is False

    path.write_text(
        f"<!-- AI-LAYER:START -->\n{GLOBAL_BOOTSTRAP_MARKER}\ncurrent instructions\n",
        encoding="utf-8",
    )
    assert _bootstrap_file_status(path, deps) is True
    assert _bootstrap_version_current(path, deps) is True
    assert f"v{GLOBAL_BOOTSTRAP_VERSION}" in GLOBAL_BOOTSTRAP_MARKER


def test_known_agent_facing_files_do_not_contain_removed_workflow_phrases() -> None:
    paths = [
        "src/ai_layer/domain/static_policy.py",
        "src/ai_layer/mcp/context.py",
        "src/ai_layer/mcp/tools/tasks.py",
        "src/ai_layer/mcp/tools/sessions.py",
        "src/ai_layer/memory/guidance.py",
        "src/ai_layer/memory/presentation.py",
        "src/ai_layer/tasks/navigation.py",
        "src/ai_layer/tasks/views.py",
        "src/ai_layer/integrations/templates.py",
    ]
    removed = [
        "after memory_context",
        "reuse the initial `memory_context`",
        "create a task before implementation",
        "edit repository before task_create",
        "mcp task layer",
        "curated project facts belong to memory_search",
        "do not bypass task layer",
        "task layer",
    ]
    for relative in paths:
        text = (ROOT / relative).read_text(encoding="utf-8").casefold()
        for phrase in removed:
            assert phrase not in text, f"stale agent-facing phrase in {relative}: {phrase}"
