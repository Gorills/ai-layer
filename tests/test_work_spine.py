from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from ai_layer.application.project_intelligence import _fuse_search, _search_queries
from ai_layer.db.models import RuntimeEvent
from ai_layer.db.work_models import RuntimeEventContext
from ai_layer.domain.agent_contract import agent_runtime_contract
from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.observability.work_events import safe_event_payload
from ai_layer.policy import project_policy as project_policy_module
from ai_layer.projections.dashboard_work_state import _truthful_state


def test_agent_contract_separates_work_from_managed_assurance_and_defines_search_protocol():
    contract = agent_runtime_contract()
    assert contract["work"]["begin"] == "work_begin"
    assert contract["work"]["managed_task_relation"].startswith("ManagedTask is optional assurance")
    assert contract["search"]["max_queries"] == 2
    assert "English code-centric" in contract["search"]["primary"]
    assert "Preserve exact paths" in contract["search"]["identifiers"]
    bootstrap = native_bootstrap_markdown()
    assert "work_begin" in bootstrap
    assert "Managed Task is optional assurance" in bootstrap
    assert "English code-centric primary query" in bootstrap
    assert "query_variants" in bootstrap
    assert "project_status.project_policy" not in bootstrap
    assert "project_policy.text" in bootstrap


def test_project_search_query_variants_are_bounded_and_fused_without_duplicate_paths():
    assert _search_queries("iiko retry order", ["повторная отправка заказа iiko"]) == [
        "iiko retry order",
        "повторная отправка заказа iiko",
    ]
    assert _search_queries("Same Query", ["same query"]) == ["Same Query"]
    with pytest.raises(ValueError):
        _search_queries("primary", ["second", "third"])
    fused = _fuse_search(
        [
            (
                "retry order service",
                {"matches": [{"path": "src/orders.py", "score": 0.7, "semantic": {}}]},
            ),
            (
                "повтор заказа",
                {
                    "matches": [
                        {"path": "src/orders.py", "score": 0.8, "semantic": {"freshness": "current"}},
                        {"path": "tests/test_orders.py", "score": 0.6, "semantic": {}},
                    ]
                },
            ),
        ],
        8,
    )
    assert [item["path"] for item in fused["matches"]] == [
        "src/orders.py",
        "tests/test_orders.py",
    ]
    assert fused["matches"][0]["matched_queries"] == [
        "retry order service",
        "повтор заказа",
    ]


def test_dashboard_work_state_does_not_infer_working_from_task_or_mcp_bridge_only():
    project = {
        "task": {"key": "T-0001", "status": "active"},
        "agents": [{"activity_state": "WORKING"}],
    }
    assert _truthful_state(project, {"active": [], "live": []}) == ("idle", "healthy")
    live = {"active": [{"status": "active"}], "live": [{"status": "active", "live": True}]}
    assert _truthful_state(project, live) == ("active", "working")
    blocked = {"active": [{"status": "blocked"}], "live": []}
    assert _truthful_state(project, blocked) == ("blocked", "attention")


def test_runtime_event_presenter_never_exposes_unapproved_payload_fields():
    event = RuntimeEvent(
        id=uuid4(),
        project_id=uuid4(),
        event_type="OperationCompleted",
        aggregate_type="operation",
        aggregate_id="corr",
        correlation_id="corr",
        actor_id="agent:test",
        actor_kind="agent",
        interface="mcp",
        schema_version=2,
        payload={
            "tool": "project_search",
            "status": "completed",
            "duration_ms": 12.5,
            "raw_prompt": "must-not-leak",
            "source_body": "must-not-leak",
        },
        created_at=datetime.now(UTC),
    )
    context = RuntimeEventContext(
        event_id=event.id,
        host="cursor",
        client="mcp",
        session_id="session-1",
        turn_id="turn-1",
        model="model-a",
        retention_class="durable",
        importance="normal",
    )
    rendered = safe_event_payload(event, context)
    assert rendered["payload"]["tool"] == "project_search"
    assert "raw_prompt" not in rendered["payload"]
    assert "source_body" not in rendered["payload"]
    assert "must-not-leak" not in repr(rendered)


def test_project_policy_snapshot_is_bounded_versioned_and_hashed(monkeypatch):
    monkeypatch.setattr(project_policy_module, "dynamic_policy", lambda _root: "project rule")
    payload = project_policy_module.project_policy_snapshot("/tmp/project")
    assert payload["version"] == 1
    assert payload["text"] == "project rule"
    assert payload["chars"] == len("project rule")
    assert len(payload["sha256"]) == 64
    assert payload["truncated"] is False
