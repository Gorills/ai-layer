import json
from pathlib import Path

from typer.testing import CliRunner

from ai_layer.audit.service import mcp_audit
from ai_layer.cli.app import app
from ai_layer.core.config import get_settings
from ai_layer.core.mcp_process import list_mcp_processes, registered_mcp_process
from ai_layer.core.registry import register_project
from ai_layer.observability.service import event_path, observability_snapshot, read_events, resolve_registered_root


def _home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    return home


def test_mcp_observability_has_live_started_and_terminal_events_without_payload(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "obs-project", "obs-project")
    monkeypatch.setenv("AI_LAYER_CLIENT", "cursor")

    with registered_mcp_process() as process:
        with mcp_audit(project, "memory_context", arg_keys=["task"]) as audit:
            live = list_mcp_processes()[0]
            assert live["current_tool"] == "memory_context"
            assert live["client"] == "cursor"
            assert live["session_id"] == process["session_id"]
            audit["metrics"] = {"memory_hits": 4, "skills": 2, "payload": "secret prompt text"}

        idle = list_mcp_processes()[0]
        assert idle["current_tool"] is None

    events = read_events(project, limit=10)
    assert [item["status"] for item in events] == ["started", "completed"]
    assert events[0]["correlation_id"] == events[1]["correlation_id"]
    assert events[1]["client"] == "cursor"
    assert events[1]["metrics"]["memory_hits"] == 4
    raw = event_path(project).read_text(encoding="utf-8")
    assert "task" in raw  # argument name is safe metadata
    assert "secret prompt text" not in raw
    assert "payload" not in events[1].get("metrics", {})


def test_observability_resolves_registered_parent_from_subdirectory(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    nested = project / "src" / "feature"
    nested.mkdir(parents=True)
    register_project(project, "obs-parent", "project")
    assert resolve_registered_root(nested) == project.resolve()


def test_snapshot_is_lightweight_and_reports_recent_operations(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "obs-snapshot", "project")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    with mcp_audit(project, "memory_search", arg_keys=["query"]):
        pass

    snapshot = observability_snapshot(project)
    assert snapshot["database"]["connected"] is True
    assert snapshot["projects"][0]["root"] == str(project.resolve())
    assert snapshot["projects"][0]["last_5m"]["operations"]["memory_search"] == 1
    assert snapshot["privacy"].startswith("metadata-only")


def test_monitor_once_renders_human_runtime_view(monkeypatch):
    from ai_layer.cli.commands import operations as cli_operations

    monkeypatch.setattr(
        cli_operations,
        "observability_snapshot",
        lambda *args, **kwargs: {
            "version": "test",
            "database": {"connected": True, "pgvector": True},
            "mcp_processes": [
                {
                    "pid": 42,
                    "client": "cursor",
                    "session_id": "abcdef1234",
                    "activity_state": "ACTIVE",
                    "current_tool": "memory_context",
                    "last_project_root": "/tmp/food",
                    "idle_seconds": 0,
                }
            ],
            "projects": [
                {
                    "name": "food",
                    "root": "/tmp/food",
                    "mode": "strict-private",
                    "last_scan": None,
                    "scan_files": 120,
                    "scan_reason": "manual_scan",
                    "active_operations": [],
                    "last_5m": {"completed": 3, "failed": 0, "operations": {}},
                    "recent_events": [
                        {
                            "ts": "2026-08-09T00:00:00+00:00",
                            "category": "mcp",
                            "operation": "memory_context",
                            "status": "completed",
                            "duration_ms": 31.2,
                            "metrics": {"memory_hits": 4, "skills": 2},
                        }
                    ],
                }
            ],
        },
    )
    result = CliRunner().invoke(app, ["monitor", "--once"])
    assert result.exit_code == 0, result.output
    assert "AI Layer test  LIVE" in result.output
    assert "cursor" in result.output
    assert "memory_context" in result.output
    assert "strict-private" in result.output
    assert "metadata only" in result.output


def test_monitor_json_is_single_snapshot(monkeypatch):
    from ai_layer.cli.commands import operations as cli_operations

    payload = {"version": "test", "database": {}, "mcp_processes": [], "projects": []}
    monkeypatch.setattr(cli_operations, "observability_snapshot", lambda *args, **kwargs: payload)
    result = CliRunner().invoke(app, ["monitor", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload


def test_legacy_context_flow_does_not_claim_agent_is_working(monkeypatch, tmp_path: Path):
    import ai_layer.observability.snapshot as obs_snapshot

    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "obs-flow", "project")
    monkeypatch.setenv("AI_LAYER_CLIENT", "cursor")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    obs_snapshot._DB_STATUS_CACHE = None

    with registered_mcp_process():
        with mcp_audit(project, "memory_context", arg_keys=["task"]):
            pass
        snapshot = observability_snapshot(project)
        assert snapshot["mcp_processes"][0]["activity_state"] == "IDLE"
        assert snapshot["projects"][0]["open_task_flows"][0]["last_operation"] == "memory_context"
        assert snapshot["projects"][0]["task_active"] is False

        with mcp_audit(project, "memory_search", arg_keys=["query"]):
            pass
        snapshot = observability_snapshot(project)
        assert snapshot["projects"][0]["open_task_flows"][0]["last_operation"] == "memory_search"

        with mcp_audit(project, "session_save", arg_keys=["goal", "current_state"]):
            pass
        snapshot = observability_snapshot(project)
        assert snapshot["projects"][0]["open_task_flows"] == []


def test_exact_event_aggregation_is_not_capped_by_tail_limits(monkeypatch, tmp_path: Path):
    from ai_layer.observability.events import aggregate_events, emit_event

    _home(monkeypatch, tmp_path)
    project = tmp_path / "many-events"
    project.mkdir()
    register_project(project, "obs-many", "many-events")
    for index in range(620):
        emit_event(
            project,
            category="mcp",
            operation="memory_search" if index % 2 else "memory_context",
            status="failed" if index % 31 == 0 else "completed",
            client="cursor",
            duration_ms=10.0,
        )

    five_minutes = aggregate_events(project, since_seconds=300, recent_limit=10)
    day = aggregate_events(project, since_seconds=24 * 3600, recent_limit=10)
    assert five_minutes["terminal"] == 620
    assert day["terminal"] == 620
    assert five_minutes["failed"] == 20
    assert len(day["recent_terminal"]) == 10


def test_exact_aggregate_advances_from_appended_bytes(tmp_path: Path, monkeypatch):
    from ai_layer.observability import event_aggregation as event_service

    project = tmp_path / "incremental-aggregate"
    project.mkdir()
    monkeypatch.setattr(event_service, "_event_dir", lambda project_root: project)
    event_service._AGGREGATE_CACHE.clear()
    path = project / f"{event_service.utcnow().date().isoformat()}.jsonl"
    path.write_text(
        "".join(
            json.dumps({
                "ts": event_service.utcnow().isoformat(),
                "status": "completed",
                "operation": "memory_context",
                "client": "cursor",
                "duration_ms": 10,
            }) + "\n"
            for _ in range(25)
        ),
        encoding="utf-8",
    )
    first = event_service.aggregate_events(None, since_seconds=300)
    assert first["terminal"] == 25
    first_offset = next(iter(event_service._AGGREGATE_CACHE.values())).files[str(path)][1]

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "ts": event_service.utcnow().isoformat(),
            "status": "failed",
            "operation": "task_stage_complete",
            "client": "cursor",
            "duration_ms": 20,
        }) + "\n")
    second = event_service.aggregate_events(None, since_seconds=300)
    second_offset = next(iter(event_service._AGGREGATE_CACHE.values())).files[str(path)][1]
    assert second["terminal"] == 26
    assert second["failed"] == 1
    assert second["operations"]["memory_context"] == 25
    assert second["operations"]["task_stage_complete"] == 1
    assert second_offset > first_offset


def test_handoff_telemetry_ignores_uncommitted_disk_snapshot(monkeypatch, tmp_path: Path):
    from ai_layer.core.paths import project_state_path
    from ai_layer.sessions.service import SNAPSHOT_SCHEMA

    _home(monkeypatch, tmp_path)
    project = tmp_path / "handoff-state"
    project.mkdir()
    register_project(project, "obs-handoff", "handoff-state")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )

    latest = project_state_path(project, "sessions", "latest.json")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({
        "id": "provisional",
        "goal": "must not leak",
        "current_state": "rolled back",
        "created_at": "2026-08-09T00:00:00+00:00",
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "commit_state": "provisional",
    }), encoding="utf-8")
    assert observability_snapshot(project, include_handoff_text=True)["projects"][0]["last_handoff"] is None

    latest.write_text(json.dumps({
        "id": "committed",
        "goal": "safe handoff",
        "current_state": "committed",
        "created_at": "2026-08-09T00:00:01+00:00",
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "commit_state": "committed",
    }), encoding="utf-8")
    handoff = observability_snapshot(project, include_handoff_text=True)["projects"][0]["last_handoff"]
    assert handoff["goal"] == "safe handoff"
    assert handoff["current_state"] == "committed"
