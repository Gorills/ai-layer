from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ai_layer import __version__
from ai_layer.application import epics as epic_app
from ai_layer.application.tasks import _delegate_envelopes, _idle_managed_task_payload
from ai_layer.domain.agent_contract import (
    AGENT_RUNTIME_CONTRACT_VERSION,
    ENVELOPE_MANAGED_NEXT,
    ENVELOPE_ORDINARY,
    ENVELOPE_WORKER,
    agent_runtime_bootstrap_line,
    agent_runtime_contract,
)
from ai_layer.domain.orchestrator import mcp_bootstrap_instructions, native_bootstrap_markdown
from ai_layer.domain.static_policy import static_policy_markdown
from ai_layer.integrations import global_install
from ai_layer.integrations import service as integration_service
from ai_layer.integrations.global_install import GLOBAL_BOOTSTRAP_MARKER, GLOBAL_BOOTSTRAP_VERSION
from ai_layer.integrations.status import _bootstrap_file_status, _bootstrap_version_current
from ai_layer.integrations.versioning import (
    GLOBAL_BOOTSTRAP_MARKER as CANONICAL_BOOTSTRAP_MARKER,
)
from ai_layer.integrations.versioning import (
    GLOBAL_BOOTSTRAP_VERSION as CANONICAL_BOOTSTRAP_VERSION,
)
from ai_layer.integrations.versioning import (
    INTEGRATION_TEMPLATE_VERSION as CANONICAL_TEMPLATE_VERSION,
)
from ai_layer.memory.knowledge_contract import public_card
from ai_layer.tasks.delegation_contract import worker_job_packet

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
    assert contract["version"] == AGENT_RUNTIME_CONTRACT_VERSION == 4
    assert contract["delivery"]["envelopes"] == ["ordinary", "managed_next", "worker"]
    assert "do not reprint" in contract["delivery"]["rule"].casefold()
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


def test_native_bootstrap_contains_one_procedure_copy() -> None:
    bootstrap = native_bootstrap_markdown()
    fallback = mcp_bootstrap_instructions()
    contract_line = agent_runtime_contract()
    assert bootstrap.count("## AI Layer control-plane boundary") == 1
    assert bootstrap.count("## Mandatory engineering discipline") == 1
    assert "Mandatory project-intelligence startup" not in bootstrap
    assert "1. The first AI Layer project-state call MUST be" not in bootstrap
    assert agent_runtime_bootstrap_line() not in bootstrap
    assert "`source_work_key`" in bootstrap
    assert "`source_task_key`" in bootstrap
    assert "never both" in bootstrap
    assert agent_runtime_bootstrap_line() in fallback
    assert fallback.startswith("If native AI Layer bootstrap is not already in context:")
    assert contract_line["startup"]["tool"] == "project_status"
    assert contract_line["work"]["idle_next"] == "work_begin"
    route = contract_line["work"]["new_request_routing"]["explicit_managed_task"]
    assert route["tool"] == "task_create"
    assert route["backing_work"] == "automatic"
    assert "`work.continuation.kind` is `none`" in bootstrap
    assert "`task_create` directly" in bootstrap
    assert "When continuation.kind is none" in agent_runtime_bootstrap_line()


def test_mcp_catalog_keeps_task_and_epic_tools_without_host_filtering() -> None:
    from ai_layer.mcp.runtime import TOOL_HANDLERS
    from ai_layer.mcp.server import mcp

    names = set(TOOL_HANDLERS)
    for required in (
        "epic_create",
        "epic_next",
        "task_create",
        "task_next",
        "work_begin",
        "project_status",
    ):
        assert required in names
        assert mcp._tool_manager.get_tool(required) is not None
    runtime = (ROOT / "src/ai_layer/mcp/runtime.py").read_text(encoding="utf-8")
    assert "tool_search" not in runtime
    assert "filtered_catalog" not in runtime
    assert "cursor tool search" not in runtime.casefold()


def test_idle_managed_task_contract_is_native_first_and_task_create_is_optional() -> None:
    result = _idle_managed_task_payload({"active": False, "state": "no_active_task"})
    action = result["next_action"]
    assert result["active"] is False
    assert result["envelope"] == ENVELOPE_MANAGED_NEXT
    assert result["runtime_contract_version"] == 4
    assert action["action"] == "host_native"
    assert action["tool"] is None
    assert action["managed_option"]["tool"] == "task_create"
    assert action["managed_option"]["required"] == ["goal"]
    assert "agent_contract" not in result
    assert "latest" not in result


def test_idle_epic_next_is_compact_host_native_without_key(monkeypatch) -> None:
    monkeypatch.setattr(
        epic_app,
        "_next_action",
        lambda *args, **kwargs: {
            "active": False,
            "state": "no_active_epic",
            "next_action": {"action": "host_native", "tool": None},
        },
    )
    result = epic_app.next_action("/tmp/project")
    assert result["active"] is False
    assert result["envelope"] == ENVELOPE_MANAGED_NEXT
    assert result["runtime_contract_version"] == 4
    assert result["next_action"]["action"] == "host_native"
    assert "agent_contract" not in result
    assert "epic" not in result
    assert "latest" not in result


def test_epic_application_navigation_uses_managed_next_envelope_without_full_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(epic_app, "_next_action", lambda *args, **kwargs: {"state": "running"})
    result = epic_app.next_action("/tmp/project", key="E-0001")
    assert result["state"] == "running"
    assert result["envelope"] == ENVELOPE_MANAGED_NEXT
    assert result["runtime_contract_version"] == 4
    assert "agent_contract" not in result
    assert "project_map" not in result


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
    assert "Do not invent parallel execution" in epics
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


def test_integration_and_bootstrap_versions_have_one_canonical_source() -> None:
    assert integration_service.INTEGRATION_TEMPLATE_VERSION == CANONICAL_TEMPLATE_VERSION
    assert global_install.GLOBAL_BOOTSTRAP_VERSION == CANONICAL_BOOTSTRAP_VERSION
    assert global_install.GLOBAL_BOOTSTRAP_MARKER == CANONICAL_BOOTSTRAP_MARKER

    for relative in (
        "src/ai_layer/integrations/global_install.py",
        "src/ai_layer/integrations/service.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "INTEGRATION_TEMPLATE_VERSION =" not in text
        assert "GLOBAL_BOOTSTRAP_VERSION =" not in text


def test_release_facing_state_tracks_current_runtime_contract() -> None:
    manifest = json.loads((ROOT / "release/release-manifest.json").read_text(encoding="utf-8"))
    current_state = (ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert manifest["version"] == __version__
    assert manifest["migration_compatibility"]["target_schema"] == "0020_server_owned_actions"
    assert current_state.startswith(f"# Current State — v{__version__} ")
    assert f"Release candidate **{__version__}** targets" in current_state
    assert "versioned live runtime contract" in current_state
    assert f"## {__version__} —" in changelog
    assert f"Current package version: **{__version__}**" in readme
    assert "Project Intelligence, durable work state" in pyproject
    assert "project memory" not in pyproject.casefold()
    assert "Release **0.13.1** is promoted" not in current_state


def test_legacy_terms_are_explicit_compatibility_only_outside_historical_detectors() -> None:
    runtime = (ROOT / "src/ai_layer/core/runtime.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "src/ai_layer/projections/dashboard.py").read_text(encoding="utf-8")
    audit_cli = (ROOT / "src/ai_layer/cli/commands/operations.py").read_text(encoding="utf-8")
    legacy_detector = (ROOT / "src/ai_layer/integrations/config_files.py").read_text(
        encoding="utf-8"
    )

    assert "Task Layer schema" not in runtime
    assert "def _latest_memory_context_skill_state" not in dashboard
    assert "memory_context -> ... -> session_save" not in audit_cli
    assert "Historical markers are intentionally preserved" in legacy_detector


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


def test_epic_next_attaches_project_map_only_when_reconciling(monkeypatch) -> None:
    monkeypatch.setattr(
        epic_app,
        "_next_action",
        lambda *args, **kwargs: {
            "next_action": {
                "action": "reconcile_project_map",
                "tool": "project_map_reconcile",
            },
            "project_map": {"update": {"tool": "project_map_reconcile"}},
        },
    )
    result = epic_app.next_action("/tmp/project", key="E-0001")
    assert result["envelope"] == ENVELOPE_MANAGED_NEXT
    assert result["runtime_contract_version"] == 4
    assert "agent_contract" not in result
    assert result["project_map"]["update"]["tool"] == "project_map_reconcile"


def test_worker_job_packet_keeps_completion_fields_without_orchestrator_essays() -> None:
    packet = worker_job_packet(
        {
            "goal": "Fix retry",
            "role": "implementer",
            "acceptance_criteria": ["passes"],
            "constraints": [],
            "repository_mode": "write",
            "completion_contract": {
                "tool": "task_implementation_complete",
                "required": ["summary", "checks"],
            },
            "provenance_notice": "dirty baseline",
            "context_policy": {
                "mode": "isolated_review",
                "host_requirement": "Start the reviewer from this compact contract.",
            },
            "orchestrator_contract": {"role": "orchestrator"},
            "identity_enforcement": "essay",
            "expertise_contract": {"routing_owner": "essay"},
            "check_evidence_assurance": "essay",
        }
    )
    assert packet["envelope"] == ENVELOPE_WORKER
    assert packet["goal"] == "Fix retry"
    assert packet["completion_contract"]["tool"] == "task_implementation_complete"
    assert packet["provenance_notice"] == "dirty baseline"
    assert packet["context_policy"]["host_requirement"].startswith("Start the reviewer")
    assert "orchestrator_contract" not in packet
    assert "identity_enforcement" not in packet
    assert "expertise_contract" not in packet
    assert "check_evidence_assurance" not in packet


def test_delegate_mcp_payload_splits_orchestrator_and_worker_envelopes() -> None:
    result = _delegate_envelopes(
        {
            "id": "task-1",
            "key": "T-0001",
            "status": "active",
            "active_stage": {"id": "stage-1", "kind": "implement", "worker_id": "w1"},
            "orchestrator_handoff": {
                "next_host_action": "START_THE_DELEGATED_WORKER_NOW",
            },
            "next_action": {
                "orchestrator_contract": {"role": "managed_task_orchestrator"},
            },
            "delegation_contract": {
                "goal": "Fix retry",
                "role": "implementer",
                "acceptance_criteria": ["passes"],
                "constraints": [],
                "repository_mode": "write",
                "completion_contract": {
                    "tool": "task_implementation_complete",
                    "required": ["summary"],
                },
                "orchestrator_contract": {"role": "orchestrator"},
                "identity_enforcement": "essay",
            },
        }
    )
    next_action = result["orchestrator"]["next_action"]
    assert result["envelope"] == ENVELOPE_MANAGED_NEXT
    assert result["runtime_contract_version"] == 4
    assert next_action["action"] == "START_THE_DELEGATED_WORKER_NOW"
    assert next_action.get("tool") is None
    assert next_action["worker_id"] == "w1"
    assert next_action["stage"] == "implement"
    assert next_action["stage_id"] == "stage-1"
    assert next_action["orchestrator_contract"]["role"] == "managed_task_orchestrator"
    assert result["worker"]["envelope"] == ENVELOPE_WORKER
    assert result["worker"]["completion_contract"]["tool"] == "task_implementation_complete"
    assert "orchestrator_contract" not in result["worker"]
    assert "agent_contract" not in result


def test_delegate_envelopes_ignores_persisted_completion_tool_on_orchestrator() -> None:
    result = _delegate_envelopes(
        {
            "id": "task-1",
            "key": "T-0001",
            "status": "active",
            "active_stage": {"id": "stage-1", "kind": "implement", "worker_id": "w1"},
            "next_action": {
                "action": "record_stage_result",
                "tool": "task_implementation_complete",
                "stage": "implement",
                "stage_id": "stage-1",
                "worker_id": "w1",
                "orchestrator_contract": {"role": "managed_task_orchestrator"},
            },
            "orchestrator_handoff": {
                "next_host_action": "START_THE_DELEGATED_WORKER_NOW",
            },
            "delegation_contract": {
                "goal": "Fix retry",
                "completion_contract": {
                    "tool": "task_implementation_complete",
                    "required": ["summary"],
                },
            },
        }
    )
    next_action = result["orchestrator"]["next_action"]
    assert next_action["action"] == "START_THE_DELEGATED_WORKER_NOW"
    assert next_action.get("tool") is None
    assert next_action["action"] != "record_stage_result"
    assert next_action["worker_id"] == "w1"
    assert next_action["stage"] == "implement"
    assert next_action["stage_id"] == "stage-1"
    assert result["worker"]["completion_contract"]["tool"] == "task_implementation_complete"


def test_compact_open_transition_keeps_managed_next_envelope(monkeypatch) -> None:
    from ai_layer.mcp import runtime as mcp_runtime

    current = {
        "envelope": ENVELOPE_MANAGED_NEXT,
        "runtime_contract_version": 3,
        "active": True,
        "state": "active",
        "task": {
            "key": "T-0001",
            "status": "active",
            "active_stage": {"kind": "review"},
        },
        "next_action": {"action": "delegate_stage", "tool": "task_stage_delegate"},
    }
    monkeypatch.setattr(mcp_runtime, "db_current_task", lambda db, project, **kwargs: current)
    result = mcp_runtime._compact_open_transition(
        object(),
        object(),
        {
            "status": "active",
            "key": "T-0001",
            "task": {"delegation_contract": {"essay": True}},
            "idempotent": True,
        },
    )
    assert result["envelope"] == ENVELOPE_MANAGED_NEXT
    assert result["active"] is True
    assert result["idempotent"] is True
    assert result["next_action"]["tool"] == "task_stage_delegate"
    assert result["task"]["key"] == "T-0001"
    assert result.get("key") is None
    assert "delegation_contract" not in result
    assert "delegation_contract" not in result["task"]


def test_knowledge_search_mcp_returns_ordinary_envelope_with_items(
    monkeypatch, tmp_path: Path
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    from ai_layer.mcp.tools import project_context as project_tools

    project_root = tmp_path / "food"
    project_root.mkdir()

    @contextmanager
    def fake_session_scope():
        yield object()

    @contextmanager
    def fake_audit(*args, **kwargs):
        yield {}

    monkeypatch.setattr(project_tools, "session_scope", fake_session_scope)
    monkeypatch.setattr(project_tools, "mcp_audit", fake_audit)
    monkeypatch.setattr(
        project_tools, "_project", lambda db, root: SimpleNamespace(root_path=root, id="p1")
    )
    monkeypatch.setattr(
        project_tools,
        "search_knowledge",
        lambda db, project, query, limit: [{"title": "Retry invariant"}],
    )
    result = project_tools.knowledge_search(query="retry", project_root=str(project_root))
    assert isinstance(result, dict)
    assert result["envelope"] == ENVELOPE_ORDINARY
    assert result["items"] == [{"title": "Retry invariant"}]


def test_knowledge_search_public_card_omits_evidence_hashes() -> None:
    item = SimpleNamespace(
        id="card-1",
        title="Retry invariant",
        content="body",
        meta={
            "knowledge_key": "retry",
            "category": "invariant",
            "summary": "Retries failed orders.",
            "claims": ["bounded"],
            "constraints": [],
            "unknowns": [],
            "evidence": [{"path": "src/retry.py", "sha256": "abc123", "scanner_schema": 5}],
            "status": "VERIFIED",
            "stale_reason": None,
        },
    )
    search = public_card(item, include_evidence=False)
    listed = public_card(item)
    assert "evidence" not in search
    assert search["source_pointers"] == ["src/retry.py"]
    assert search["stale_reason"] is None
    assert listed["evidence"][0]["sha256"] == "abc123"
