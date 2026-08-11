import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ai_layer.cli.app import app as cli_app
from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.core.paths import project_state_path
from ai_layer.observability.events import emit_event


def _home(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    return home


def test_dashboard_web_and_overview_api(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "dash-project", "Dashboard Project")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot
    snapshot._DB_STATUS_CACHE = None
    emit_event(project, category="mcp", operation="memory_search", status="completed", client="cursor", metrics={"hits": 3})

    from ai_layer.api.app import create_app
    client = TestClient(create_app())
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["service"]["pid"]
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "AI Layer Dashboard" in page.text
    assert "/dashboard-assets/js/app.js" in page.text
    assert client.get("/dashboard-assets/js/app.js").status_code == 200
    assert client.get("/dashboard-assets/css/app.css").status_code == 200

    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["projects"] == 1
    assert "service" in data and "uptime_seconds" in data["service"]
    assert data["projects"][0]["key"] == "dash-project"
    assert data["projects"][0]["name"] == "Dashboard Project"
    assert data["summary"]["operations_5m"] >= 1
    assert '<html lang="ru">' in page.text
    assert "Текущие задачи, стадии" in page.text


def test_dashboard_uses_durable_task_state(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "task-dashboard", "Task Dashboard")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot
    snapshot._DB_STATUS_CACHE = None

    task_dir = project_state_path(project, "tasks")
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "current.json").write_text(
        json.dumps({
            "key": "T-0042",
            "goal": "Проверить новый workflow",
            "status": "active",
            "review_round": 1,
            "fix_round": 0,
            "open_findings": 2,
            "active_stage": {"kind": "review", "review_round": 1, "fix_round": 0},
            "next_action": {"action": "delegate_stage", "message": "Delegate reviewer"},
            "stages": [],
            "findings": [],
        }),
        encoding="utf-8",
    )

    from ai_layer.api.app import create_app
    client = TestClient(create_app())
    data = client.get("/api/v1/dashboard/overview").json()
    assert data["summary"]["active_tasks"] == 1
    card = data["projects"][0]
    assert card["runtime_state"] == "active"
    assert card["task"]["key"] == "T-0042"
    assert card["task"]["active_stage"]["kind"] == "review"
    assert "open_task_flows" not in card


def test_dashboard_project_detail_is_read_only_metadata(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "dash-detail", "Detail")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot
    snapshot._DB_STATUS_CACHE = None
    emit_event(project, category="mcp", operation="memory_context", status="completed", client="cursor", duration_ms=12.5, metrics={"memory_hits": 4, "payload": "secret prompt text"})

    from ai_layer.api.app import create_app
    client = TestClient(create_app())
    response = client.get("/api/v1/dashboard/projects/dash-detail")
    assert response.status_code == 200
    data = response.json()
    assert data["project"]["root"] == str(project.resolve())
    assert data["metrics"]["events_24h"] >= 1
    raw = response.text
    assert "secret prompt text" not in raw.lower()
    assert "\"payload\"" not in raw.lower()


def test_dashboard_cli_rejects_remote_bind(monkeypatch):
    result = CliRunner().invoke(cli_app, ["dashboard", "--host", "0.0.0.0", "--no-open"])
    assert result.exit_code != 0
    assert "loopback" in result.output


def test_dashboard_cli_opens_existing_service_without_starting_server(monkeypatch):
    monkeypatch.setattr(
        "ai_layer.cli.commands.service_commands.probe_service",
        lambda host, port: {"running": True, "version": "test"},
    )
    monkeypatch.setattr(
        "ai_layer.cli.commands.service_commands.uvicorn.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dashboard must not start uvicorn")),
    )
    result = CliRunner().invoke(cli_app, ["dashboard", "--no-open"])
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8765/dashboard" in result.output


def test_dashboard_cli_starts_background_service_when_needed(monkeypatch):
    probes = iter([{"running": False}, {"running": True, "version": "test"}])
    monkeypatch.setattr("ai_layer.cli.commands.service_commands.probe_service", lambda host, port: next(probes))
    monkeypatch.setattr("ai_layer.cli.commands.service_commands.start_user_service", lambda: {"ok": True})
    monkeypatch.setattr(
        "ai_layer.cli.commands.service_commands.wait_for_service",
        lambda host, port: {"running": True, "version": "test"},
    )
    result = CliRunner().invoke(cli_app, ["dashboard", "--no-open"])
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8765/dashboard" in result.output


def test_service_run_is_manual_unless_process_manager_sets_background(monkeypatch):
    calls = []
    monkeypatch.delenv("AI_LAYER_SERVICE_MODE", raising=False)
    monkeypatch.setattr(
        "ai_layer.cli.commands.service_commands.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(cli_app, ["service", "run"])

    assert result.exit_code == 0, result.output
    assert calls and calls[0][1]["host"] == "127.0.0.1" and calls[0][1]["port"] == 8765
    assert "AI_LAYER_SERVICE_MODE" not in __import__("os").environ


def test_service_run_rejects_noncanonical_endpoint(monkeypatch):
    monkeypatch.setattr(
        "ai_layer.cli.commands.service_commands.uvicorn.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must reject before uvicorn")),
    )
    custom_port = CliRunner().invoke(cli_app, ["service", "run", "--port", "9877"])
    assert custom_port.exit_code != 0
    assert "fixed at 127.0.0.1:8765" in custom_port.output

    custom_host = CliRunner().invoke(cli_app, ["service", "run", "--host", "localhost"])
    assert custom_host.exit_code != 0
    assert "fixed at 127.0.0.1:8765" in custom_host.output


def test_dashboard_protocol_failure_is_warning_and_recovery_not_project_error(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "protocol-dashboard", "Protocol Dashboard")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot
    snapshot._DB_STATUS_CACHE = None

    emit_event(
        project,
        category="mcp",
        operation="task_stage_complete",
        status="failed",
        client="cursor",
        error_type="ValueError",
    )
    emit_event(
        project,
        category="mcp",
        operation="task_stage_complete",
        status="completed",
        client="cursor",
        metrics={"normalization_count": 2, "effective_verdict": "changes_required"},
    )

    from ai_layer.api.app import create_app
    client = TestClient(create_app())
    data = client.get("/api/v1/dashboard/overview").json()
    card = data["projects"][0]
    assert card["project_state"] == "healthy"
    assert card["runtime_state"] == "idle"
    assert card["protocol_state"]["status"] == "warning"
    assert card["protocol_state"]["failures_5m"] == 1
    assert card["protocol_state"]["recovered"] is True
    assert card["protocol_state"]["normalizations_5m"] == 2
    assert data["summary"]["protocol_warnings"] == 1
    assert data["summary"]["recovered_protocol_warnings"] == 1


def test_dashboard_protocol_recovery_requires_same_operation(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "protocol-unrecovered", "Protocol Unrecovered")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot
    snapshot._DB_STATUS_CACHE = None

    emit_event(
        project,
        category="mcp",
        operation="task_stage_complete",
        status="failed",
        client="cursor",
        error_type="ValueError",
    )
    emit_event(
        project,
        category="mcp",
        operation="memory_search",
        status="completed",
        client="cursor",
    )

    from ai_layer.api.app import create_app
    client = TestClient(create_app())
    card = client.get("/api/v1/dashboard/overview").json()["projects"][0]
    assert card["project_state"] == "healthy"
    assert card["protocol_state"]["status"] == "warning"
    assert card["protocol_state"]["recovered"] is False


def test_dashboard_surfaces_human_attention_separately_from_generic_blocker(monkeypatch, tmp_path: Path):
    _home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "attention-dashboard", "Attention Dashboard")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot
    snapshot._DB_STATUS_CACHE = None

    task_dir = project_state_path(project, "tasks")
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "current.json").write_text(
        json.dumps({
            "key": "T-0007",
            "goal": "Stop bounded remediation safely",
            "status": "blocked",
            "human_attention_required": True,
            "human_attention_reason": "Automatic remediation stopped after 2 attempts.",
            "automatic_fix_round_limit": 2,
            "automatic_remediation_count": 2,
            "finding_summary": {"total": 5, "open": 2, "pending_verification": 1, "verified": 2},
            "active_findings": [],
            "active_stage": None,
            "next_action": {"action": "human_attention_required"},
            "stages": [],
            "findings": [],
        }),
        encoding="utf-8",
    )

    from ai_layer.api.app import create_app
    client = TestClient(create_app())
    data = client.get("/api/v1/dashboard/overview").json()
    assert data["summary"]["attention_tasks"] == 1
    card = data["projects"][0]
    assert card["runtime_state"] == "blocked"
    assert card["project_state"] == "attention"
    assert card["task"]["human_attention_required"] is True
    assert card["task"]["finding_summary"]["pending_verification"] == 1


def test_dashboard_project_payload_exposes_native_catalog_and_observed_fetch(monkeypatch, tmp_path: Path):
    import ai_layer.projections.dashboard as dashboard_service

    root = tmp_path / "project"
    root.mkdir()
    task = {"key": "T-0007", "goal": "Redesign dashboard", "status": "active"}
    events = [
        {
            "operation": "memory_context",
            "status": "completed",
            "ts": "2026-08-10T01:00:00+00:00",
            "metrics": {
                "skill_routing_owner": "host-native",
                "automatic_skill_injection": False,
                "automatic_skill_chars": 0,
            },
        },
        {
            "operation": "skill_get",
            "status": "completed",
            "ts": "2026-08-10T01:01:00+00:00",
            "metrics": {"skill_slug": "design", "section": "Core contract"},
        },
    ]

    monkeypatch.setattr(
        dashboard_service,
        "native_catalog_files",
        lambda root: {"cursor": [Path("a"), Path("b")], "codex": [Path("a"), Path("b")], "antigravity": [Path("c"), Path("d")]},
    )
    state = dashboard_service._task_skill_state(root, task, events)
    assert state["task"] == "T-0007"
    assert state["routing_owner"] == "host-native"
    assert state["ai_layer_planner_active"] is False
    assert state["configured_catalog"]["cursor"] == 2
    assert state["last_context"]["automatic_skill_injection"] is False
    assert state["last_context"]["automatic_skill_chars"] == 0
    assert state["observed_fetches"][0]["slug"] == "design"
    assert state["observed_fetches"][0]["section"] == "Core contract"
    assert state["source"] == "native-catalog-plus-observed-skill-get"
