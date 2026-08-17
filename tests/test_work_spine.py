from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.application.project_intelligence import _fuse_search, _search_queries
from ai_layer.db.base import Base
from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.work_models import RuntimeEventContext
from ai_layer.domain.agent_contract import agent_runtime_contract
from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.memory.project_map_semantics import reconcile_project_map
from ai_layer.observability.operation_events import _result_context
from ai_layer.observability.work_events import safe_event_payload
from ai_layer.policy import project_policy as project_policy_module
from ai_layer.projections.dashboard_work_state import _truthful_state
from ai_layer.work.evidence import check_evidence, map_disposition, project_paths, repository_delta
from ai_layer.work.service import begin_work, finish_work


def test_agent_contract_separates_work_from_managed_assurance_and_defines_search_protocol():
    contract = agent_runtime_contract()
    assert contract["version"] == 3
    assert contract["delivery"]["envelopes"] == ["ordinary", "managed_next", "worker"]
    assert contract["work"]["begin"] == "work_begin"
    assert contract["work"]["idle_next"] == "work_begin"
    assert contract["work"]["kinds"] == [
        "change",
        "diagnose",
        "review",
        "research",
        "planning",
        "ops",
    ]
    assert "tiny one-shot" in contract["work"]["unmaterialized"]
    assert contract["work"]["managed_task_relation"].startswith("ManagedTask is optional assurance")
    assert contract["search"]["max_queries"] == 2
    assert "English code-centric" in contract["search"]["primary"]
    assert "Preserve exact paths" in contract["search"]["identifiers"]
    bootstrap = native_bootstrap_markdown()
    assert "work_begin" in bootstrap
    assert "`work.continuation.kind` is `none`" in bootstrap
    assert "call `work_begin` before other tools" in bootstrap
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
                        {
                            "path": "src/orders.py",
                            "score": 0.8,
                            "semantic": {"freshness": "current"},
                        },
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
    assert "query_contract" not in fused
    assert "language_contract" not in fused
    assert "source_contract" not in fused
    assert fused["queries_used"] == ["retry order service", "повтор заказа"]


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
            "summary": "token=must-not-leak",
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
    assert rendered["payload"]["summary"] == "token=<redacted>"
    assert "raw_prompt" not in rendered["payload"]
    assert "source_body" not in rendered["payload"]
    assert "must-not-leak" not in repr(rendered)


def test_project_policy_snapshot_is_bounded_versioned_and_hashed(monkeypatch):
    monkeypatch.setattr(
        project_policy_module,
        "dynamic_policy_parts",
        lambda _root, read_only=False: [("project", "project rule")],
    )
    payload = project_policy_module.project_policy_snapshot("/tmp/project")
    assert payload["version"] == 1
    assert payload["text"] == "project rule"
    assert payload["chars"] == len("project rule")
    assert len(payload["sha256"]) == 64
    assert payload["truncated"] is False


def test_work_lifecycle_has_an_explicit_architecture_owner():
    root = Path(__file__).parents[1]
    policy = json.loads((root / "release" / "architecture-policy.json").read_text(encoding="utf-8"))
    owners = {item["prefix"]: item["capability"] for item in policy["capabilities"]}
    assert owners["ai_layer.work"] == "Work"


def test_terminal_operation_context_links_the_work_and_root_run():
    work_id = uuid4()
    run_id = uuid4()
    context = _result_context(
        {
            "work": {
                "id": str(work_id),
                "runs": [
                    {
                        "id": str(run_id),
                        "role": "root",
                        "host": "codex",
                        "session_id": "session-1",
                    }
                ],
            }
        }
    )
    assert context["work_id"] == work_id
    assert context["run_id"] == run_id
    assert context["host"] == "codex"


def test_work_evidence_accepts_only_bounded_safe_metadata():
    assert (
        repository_delta(
            {
                "base_revision": "abc123",
                "final_revision": "def456",
                "changed_files": 2,
                "insertions": 10,
                "deletions": 3,
                "dirty": True,
                "assurance": "host_reported",
            }
        )["changed_files"]
        == 2
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        repository_delta({"source_body": "must-not-be-durable"})
    with pytest.raises(ValueError, match="non-negative integer"):
        repository_delta({"changed_files": True})
    with pytest.raises(ValueError, match="unsupported fields"):
        check_evidence([{"command": "pytest --token=secret", "status": "passed"}])
    with pytest.raises(ValueError, match="checks.status must be one of"):
        check_evidence([{"name": "tests", "status": "arbitrary"}])
    with pytest.raises(ValueError, match="unsupported fields"):
        check_evidence([{"name": "tests", "status": "passed", "output": "must-not-be-durable"}])
    assert (
        check_evidence([{"name": "tests", "status": "passed", "summary": "token=secret-value"}])[0][
            "summary"
        ]
        == "token=<redacted>"
    )
    with pytest.raises(ValueError, match="project-relative"):
        project_paths(["src/.."], field="reviewed_paths")
    with pytest.raises(ValueError, match="scope and map_disposition.reason"):
        map_disposition({"status": "checked_no_change", "scope": ["src/app.py"]})
    with pytest.raises(ValueError, match="event_id must be a UUID"):
        map_disposition(
            {"status": "reconciled", "scope": ["src/app.py"], "event_id": "not-an-event"}
        )
    assert map_disposition(
        {
            "status": "reconciled",
            "scope_paths": ["src/app.py"],
            "event_id": "00000000-0000-4000-8000-000000000001",
        }
    ) == {
        "status": "reconciled",
        "scope": ["src/app.py"],
        "reason": "",
        "event_id": "00000000-0000-4000-8000-000000000001",
    }
    with pytest.raises(ValueError, match="must match"):
        map_disposition(
            {
                "status": "reconciled",
                "scope": ["src/app.py"],
                "scope_paths": ["src/other.py"],
                "event_id": "00000000-0000-4000-8000-000000000001",
            }
        )


def test_reconciled_work_disposition_requires_matching_durable_event():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Work map evidence",
            root_path="/tmp/work-map-evidence",
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        work, run = begin_work(db, project, goal="Verify map closure")
        event = RuntimeEvent(
            project_id=project.id,
            event_type="ProjectMapReconciled",
            aggregate_type="work",
            aggregate_id=str(work.id),
            payload={"scope_paths": ["src/app.py"]},
        )
        db.add(event)
        db.flush()
        db.add(RuntimeEventContext(event_id=event.id, work_id=work.id, run_id=run.id))
        db.flush()

        with pytest.raises(ValueError, match="must identify a ProjectMapReconciled event"):
            finish_work(
                db,
                project,
                work_key_value="W-0001",
                status="completed",
                summary="Done",
                map_disposition={
                    "status": "reconciled",
                    "scope": ["src/app.py"],
                    "event_id": str(uuid4()),
                },
            )
        with pytest.raises(ValueError, match="must match"):
            finish_work(
                db,
                project,
                work_key_value="W-0001",
                status="completed",
                summary="Done",
                map_disposition={
                    "status": "reconciled",
                    "scope": ["src/other.py"],
                    "event_id": str(event.id),
                },
            )
        completed, _runs = finish_work(
            db,
            project,
            work_key_value="W-0001",
            status="completed",
            summary="Done token=secret-value",
            map_disposition={
                "status": "reconciled",
                "scope_paths": ["src/app.py"],
                "event_id": str(event.id),
            },
        )
        assert completed.result_summary == "Done token=<redacted>"
        assert completed.map_disposition["status"] == "reconciled"
        assert completed.map_disposition["scope"] == ["src/app.py"]
        assert completed.map_disposition["event_id"] == str(event.id)


def test_project_map_provenance_keys_are_mutually_exclusive_before_database_access():
    with pytest.raises(ValueError, match="mutually exclusive"):
        reconcile_project_map(
            object(),
            object(),
            entries=None,
            remove_paths=None,
            scope_paths=["src/app.py"],
            source_task_key="T-0001",
            source_work_key="W-0001",
            no_changes_reason="Existing map is accurate.",
        )


def test_work_linked_reconcile_persists_disposition_and_finish_keeps_omitted_value():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Work map persist",
            root_path="/tmp/work-map-persist",
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        work, _run = begin_work(db, project, goal="Keep map closure in sync")
        work.reviewed_paths = ["src/app.py"]
        db.flush()
        result = reconcile_project_map(
            db,
            project,
            entries=None,
            remove_paths=None,
            scope_paths=None,
            source_task_key=None,
            no_changes_reason="Existing map is accurate.",
            source_work_key="W-0001",
        )
        assert result["map_disposition"]["status"] == "reconciled"
        assert result["map_disposition"]["event_id"] == result["event_id"]
        assert result["map_disposition"]["scope"] == ["src/app.py"]
        assert work.map_disposition == result["map_disposition"]

        completed, _runs = finish_work(
            db,
            project,
            work_key_value="W-0001",
            status="completed",
            summary="Done without repeating map_disposition",
        )
        assert completed.map_disposition["status"] == "reconciled"
        assert completed.map_disposition["event_id"] == result["event_id"]
        assert completed.map_disposition["scope"] == ["src/app.py"]
        assert completed.map_disposition["status"] != "pending"


def test_terminal_work_converts_unresolved_pending_map_state_to_truthful_deferred():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Work map deferred",
            root_path="/tmp/work-map-deferred",
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        _work, _run = begin_work(db, project, goal="Finish without inventing map facts")
        completed, _runs = finish_work(
            db,
            project,
            work_key_value="W-0001",
            status="completed",
            summary="Done",
            reviewed_paths=["src/app.py"],
        )
        assert completed.map_disposition["status"] == "deferred"
        assert completed.map_disposition["scope"] == ["src/app.py"]
        assert "No Project Map reconciliation was recorded" in completed.map_disposition["reason"]
