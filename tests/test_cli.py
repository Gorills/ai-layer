import json
from pathlib import Path

from typer.testing import CliRunner

from ai_layer.cli.app import app


def test_cursor_mcp_config_merge(tmp_path: Path, monkeypatch):
    import importlib
    from types import SimpleNamespace

    service_commands = importlib.import_module("ai_layer.cli.commands.service_commands")
    monkeypatch.setattr(
        service_commands,
        "get_settings",
        lambda: SimpleNamespace(stable_mcp_executable=tmp_path / "missing-ai-layer-mcp"),
    )
    target = tmp_path / ".cursor" / "mcp.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"mcpServers": {"existing": {"command": "demo"}}}))
    result = CliRunner().invoke(app, ["mcp-config", str(tmp_path), "--write-cursor"])
    assert result.exit_code == 0, result.output
    data = json.loads(target.read_text())
    assert data["mcpServers"]["existing"]["command"] == "demo"
    assert data["mcpServers"]["ai-layer"]["command"] == "ai-layer-mcp"
    assert data["mcpServers"]["ai-layer"]["env"]["AI_LAYER_PROJECT_ROOT"] == str(tmp_path.resolve())
    assert data["mcpServers"]["ai-layer"]["env"]["AI_LAYER_CLIENT"] == "cursor"


def test_cursor_mcp_config_rejects_symlink_escape(tmp_path: Path):
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".cursor").symlink_to(outside, target_is_directory=True)

    result = CliRunner().invoke(app, ["mcp-config", str(project), "--write-cursor"])

    assert result.exit_code != 0
    assert not (outside / "mcp.json").exists()


def test_serve_rejects_non_loopback_host():
    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code != 0
    assert "loopback" in result.output.lower()


def test_audit_tail_cli_reads_privacy_minimal_events(tmp_path: Path, monkeypatch):
    from ai_layer.audit.service import mcp_audit
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    register_project(tmp_path, "audit-cli-tail", "audit-cli-tail")
    with mcp_audit(tmp_path, "memory_context", arg_keys=["task"]):
        pass
    result = CliRunner().invoke(app, ["audit", "tail", "--path", str(tmp_path), "--limit", "5"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["events"][0]["tool"] == "memory_context"
    assert payload["events"][0]["arg_keys"] == ["task"]


def test_audit_check_cli_validates_latest_completed_flow(tmp_path: Path, monkeypatch):
    from ai_layer.audit.service import mcp_audit
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    register_project(tmp_path, "audit-cli-check", "audit-cli-check")
    with mcp_audit(tmp_path, "project_status", arg_keys=["task"]):
        pass
    with mcp_audit(tmp_path, "session_save", arg_keys=["goal", "current_state"]):
        pass
    result = CliRunner().invoke(app, ["audit", "check", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["flow_start_tool"] == "project_status"
    assert payload["project_status_calls"] == 1
    assert payload["memory_context_calls"] == 0
    assert payload["session_saved"] is True


def test_machine_upgrade_does_not_sync_projects_after_failed_migration(monkeypatch):
    import importlib

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    monkeypatch.setattr(cli, "_install_global_files", lambda force=False: {})
    monkeypatch.setattr(cli, "install_global_integrations", lambda: {})
    monkeypatch.setattr(cli, "start_database", lambda: {"ok": True})
    monkeypatch.setattr(
        cli, "migrate_database", lambda: (_ for _ in ()).throw(RuntimeError("migration failed"))
    )
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(cli, "write_install_state", lambda payload: payload)
    monkeypatch.setattr(
        cli,
        "_sync_registered_projects",
        lambda: (_ for _ in ()).throw(AssertionError("project sync must not run")),
    )

    result = cli._machine_upgrade(force=False, skip_db=False, sync_projects=True)

    assert result["machine_upgrade_ok"] is False
    assert result["project_sync"]["skipped"] is True
    assert "migration" in result["project_sync"]["reason"]


def test_global_config_does_not_persist_database_credentials(monkeypatch, tmp_path: Path):
    import importlib
    from types import SimpleNamespace

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    home = tmp_path / "home"
    home.mkdir()
    config_file = home / "config.yaml"
    config_file.write_text(
        "database_url: postgresql+psycopg://user:legacy-secret@example.invalid/db\ncustom_note: keep-me\n",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        home=home,
        config_file=config_file,
        embedding_provider="hash",
        embedding_model="test-model",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "install_builtin_skills", lambda force=False: [])
    monkeypatch.setattr(cli, "ensure_global_policy", lambda force=False: home / "policy.md")

    cli._install_global_files(force=False)

    text = config_file.read_text(encoding="utf-8")
    assert "legacy-secret" not in text
    assert "database_url" not in text
    assert "database_credentials_persisted: false" in text
    assert "custom_note: keep-me" in text
    assert config_file.stat().st_mode & 0o077 == 0


def test_doctor_treats_stale_mcp_as_warning_not_upgrade_blocker(monkeypatch, tmp_path: Path):
    import importlib
    from types import SimpleNamespace

    cli = importlib.import_module("ai_layer.cli.commands.operations")
    stable_bin = tmp_path / "current" / "bin"
    stable_bin.mkdir(parents=True)
    (stable_bin / "ai-layer").write_text("", encoding="utf-8")
    (stable_bin / "ai-layer-mcp").write_text("", encoding="utf-8")
    machine_runtime = tmp_path / "machine-runtime"
    (machine_runtime / "alembic").mkdir(parents=True)
    (machine_runtime / "docker-compose.yml").write_text("", encoding="utf-8")
    settings = SimpleNamespace(
        stable_bin_dir=stable_bin,
        stable_mcp_executable=stable_bin / "ai-layer-mcp",
        config_file=tmp_path / "config.yaml",
        machine_runtime_dir=machine_runtime,
        projects_registry_file=tmp_path / "projects.json",
    )
    settings.config_file.write_text("version: test\n", encoding="utf-8")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "docker_compose_available", lambda: (True, "/usr/bin/docker"))
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(
        cli,
        "global_integration_status",
        lambda: {
            "cursor": {"ready": True},
            "antigravity": {"ready": True},
            "codex": {"ready": True},
        },
    )
    monkeypatch.setattr(cli, "list_registered_projects", lambda: [])
    monkeypatch.setattr(
        cli,
        "list_mcp_processes",
        lambda: [{"pid": 1234, "version": "0.1.5.1", "version_match": False}],
    )
    monkeypatch.setattr(cli, "read_install_state", lambda: {"version": "0.1.6"})

    result = CliRunner().invoke(app, ["doctor", "--all-projects"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    stale = [item for item in payload["issues"] if "stale MCP process" in item["problem"]]
    assert stale and stale[0]["severity"] == "warning"


def test_audit_check_cli_treats_duplicate_context_as_tool_economy_warning(
    tmp_path: Path, monkeypatch
):
    from ai_layer.audit.service import mcp_audit
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    register_project(tmp_path, "audit-cli-economy", "audit-cli-economy")
    with mcp_audit(tmp_path, "project_status", arg_keys=[]):
        pass
    with mcp_audit(tmp_path, "memory_context", arg_keys=["task"]):
        pass
    with mcp_audit(tmp_path, "memory_context", arg_keys=["task"]):
        pass
    with mcp_audit(tmp_path, "session_save", arg_keys=["goal", "current_state"]):
        pass

    result = CliRunner().invoke(app, ["audit", "check", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["warnings"][0]["code"] == "tool_economy"


def test_global_config_repairs_permissions_even_when_content_is_unchanged(
    monkeypatch, tmp_path: Path
):
    import importlib
    import os
    from types import SimpleNamespace

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    home = tmp_path / "home"
    home.mkdir()
    config_file = home / "config.yaml"
    settings = SimpleNamespace(
        home=home,
        config_file=config_file,
        embedding_provider="hash",
        embedding_model="test-model",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "install_builtin_skills", lambda force=False: [])
    monkeypatch.setattr(cli, "ensure_global_policy", lambda force=False: home / "policy.md")

    cli._install_global_files(force=False)
    os.chmod(config_file, 0o644)
    cli._install_global_files(force=False)

    assert config_file.stat().st_mode & 0o077 == 0


def test_doctor_machine_only_ignores_registered_project_health(monkeypatch, tmp_path: Path):
    import importlib
    from types import SimpleNamespace

    cli = importlib.import_module("ai_layer.cli.commands.operations")
    stable_bin = tmp_path / "current" / "bin"
    stable_bin.mkdir(parents=True)
    (stable_bin / "ai-layer").write_text("", encoding="utf-8")
    (stable_bin / "ai-layer-mcp").write_text("", encoding="utf-8")
    machine_runtime = tmp_path / "machine-runtime"
    (machine_runtime / "alembic").mkdir(parents=True)
    (machine_runtime / "docker-compose.yml").write_text("", encoding="utf-8")
    settings = SimpleNamespace(
        stable_bin_dir=stable_bin,
        stable_mcp_executable=stable_bin / "ai-layer-mcp",
        config_file=tmp_path / "config.yaml",
        machine_runtime_dir=machine_runtime,
        projects_registry_file=tmp_path / "projects.json",
    )
    settings.config_file.write_text("version: test\n", encoding="utf-8")
    bad_project = tmp_path / "unsafe-project"
    bad_project.mkdir()

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "docker_compose_available", lambda: (True, "/usr/bin/docker"))
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(
        cli,
        "global_integration_status",
        lambda: {
            "cursor": {"ready": True},
            "antigravity": {"ready": True},
            "codex": {"ready": True},
            "claude-code": {"ready": True, "optional": True},
        },
    )
    monkeypatch.setattr(cli, "list_registered_projects", lambda: [{"root": str(bad_project)}])
    monkeypatch.setattr(cli, "list_mcp_processes", lambda: [])
    monkeypatch.setattr(cli, "read_install_state", lambda: {"version": "0.1.6.2"})
    monkeypatch.setattr(
        cli,
        "integration_status",
        lambda root: (_ for _ in ()).throw(
            AssertionError("machine-only doctor must not inspect projects")
        ),
    )

    result = CliRunner().invoke(app, ["doctor", "--machine-only"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["projects"] == []


def test_doctor_machine_only_rejects_project_scope_options():
    result = CliRunner().invoke(app, ["doctor", "--machine-only", "--all-projects"])
    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_projects_unregister_cli_forgets_only_requested_root(tmp_path: Path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    home = tmp_path / "home"
    first = tmp_path / "first"
    second = tmp_path / "second"
    home.mkdir()
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    register_project(first, "p-1", "first")
    register_project(second, "p-2", "second")

    result = CliRunner().invoke(app, ["projects", "unregister", str(first)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["removed"] == 1

    remaining = CliRunner().invoke(app, ["projects", "list"])
    assert remaining.exit_code == 0, remaining.output
    roots = [item["root"] for item in json.loads(remaining.output)["projects"]]
    assert roots == [str(second.resolve())]
    get_settings.cache_clear()


def test_registry_hydration_skips_missing_database_roots(monkeypatch, tmp_path: Path):
    import importlib
    from contextlib import contextmanager
    from types import SimpleNamespace

    cli = importlib.import_module("ai_layer.application.projects")
    existing = tmp_path / "existing"
    existing.mkdir()
    missing = tmp_path / "missing"
    projects = [
        SimpleNamespace(root_path=str(existing), id="p-existing", name="existing"),
        SimpleNamespace(root_path=str(missing), id="p-missing", name="missing"),
    ]

    class FakeScalars:
        def all(self):
            return projects

    class FakeDb:
        def scalars(self, statement):
            return FakeScalars()

    @contextmanager
    def fake_session_scope():
        yield FakeDb()

    registered = []
    monkeypatch.setattr(cli, "session_scope", fake_session_scope)
    monkeypatch.setattr(
        cli, "register_project", lambda root, project_id, name: registered.append(str(root))
    )

    result = cli.hydrate_registry_from_database()

    assert result == {"ok": True, "imported": 1, "skipped_missing": 1, "skipped_forgotten": 0}
    assert registered == [str(existing)]


def test_registry_hydration_skips_forgotten_database_roots(monkeypatch, tmp_path: Path):
    import importlib
    from contextlib import contextmanager
    from types import SimpleNamespace

    cli = importlib.import_module("ai_layer.application.projects")
    project = tmp_path / "forgotten"
    project.mkdir()
    rows = [SimpleNamespace(root_path=str(project), id="p-forgotten", name="forgotten")]

    class FakeScalars:
        def all(self):
            return rows

    class FakeDb:
        def scalars(self, statement):
            return FakeScalars()

    @contextmanager
    def fake_session_scope():
        yield FakeDb()

    registered = []
    monkeypatch.setattr(cli, "session_scope", fake_session_scope)
    monkeypatch.setattr(cli, "is_project_forgotten", lambda root: True)
    monkeypatch.setattr(cli, "register_project", lambda *args, **kwargs: registered.append(args))

    result = cli.hydrate_registry_from_database()
    assert result == {"ok": True, "imported": 0, "skipped_missing": 0, "skipped_forgotten": 1}
    assert registered == []


def test_projects_remove_requires_explicit_yes():
    result = CliRunner().invoke(app, ["projects", "remove", "/tmp/example"])
    assert result.exit_code != 0
    assert "--yes is required" in result.output


def test_doctor_overlap_is_error_and_nonzero_even_when_both_projects_are_otherwise_ready(
    monkeypatch, tmp_path: Path
):
    import importlib
    from types import SimpleNamespace

    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project
    from ai_layer.integrations.service import INTEGRATION_TEMPLATE_VERSION

    cli = importlib.import_module("ai_layer.cli.commands.operations")
    home = tmp_path / "home-overlap-doctor"
    parent = tmp_path / "food"
    child = parent / "main"
    child.mkdir(parents=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    register_project(child, "p-child", "main")
    register_project(parent, "p-parent", "food")
    for root, project_id in ((parent, "p-parent"), (child, "p-child")):
        meta = root / ".ai-layer"
        meta.mkdir(exist_ok=True)
        (meta / "project.yaml").write_text(
            f"version: 2\nproject_id: {project_id}\nname: {root.name}\nroot: {root.resolve()}\nmode: standard\nprovenance: allow\nintegration_template_version: {INTEGRATION_TEMPLATE_VERSION}\n",
            encoding="utf-8",
        )

    stable_bin = tmp_path / "current" / "bin"
    stable_bin.mkdir(parents=True)
    (stable_bin / "ai-layer").write_text("", encoding="utf-8")
    (stable_bin / "ai-layer-mcp").write_text("", encoding="utf-8")
    machine_runtime = tmp_path / "machine-runtime"
    (machine_runtime / "alembic").mkdir(parents=True)
    (machine_runtime / "docker-compose.yml").write_text("", encoding="utf-8")
    settings = SimpleNamespace(
        stable_bin_dir=stable_bin,
        stable_mcp_executable=stable_bin / "ai-layer-mcp",
        config_file=tmp_path / "config.yaml",
        machine_runtime_dir=machine_runtime,
        projects_registry_file=home / ".ai-layer" / "projects.json",
    )
    settings.config_file.write_text("version: test\n", encoding="utf-8")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "docker_compose_available", lambda: (True, "/usr/bin/docker"))
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(cli, "global_integration_status", lambda: {"cursor": {"ready": True}})
    monkeypatch.setattr(cli, "global_bootstrap_status", lambda: {"cursor": {"ready": True}})
    monkeypatch.setattr(cli, "list_mcp_processes", lambda: [])
    monkeypatch.setattr(cli, "read_install_state", lambda: {"version": "0.2.4"})
    monkeypatch.setattr(cli, "integration_status", lambda root: {"ready": True})

    try:
        result = CliRunner().invoke(app, ["doctor", "--all-projects"])
        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["ok"] is False
        overlap = [
            issue
            for issue in payload["issues"]
            if "overlapping project registrations" in issue["problem"]
        ]
        assert len(overlap) == 1
        assert overlap[0]["severity"] == "error"
        assert "ai-layer repair" in overlap[0]["action"]
    finally:
        get_settings.cache_clear()


def test_machine_upgrade_runs_project_repair_after_successful_migration(monkeypatch):
    import importlib

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    calls = []
    monkeypatch.setattr(cli, "_install_global_files", lambda force=False: {})
    monkeypatch.setattr(cli, "install_global_integrations", lambda: {})
    monkeypatch.setattr(cli, "start_database", lambda: {"ok": True})
    monkeypatch.setattr(cli, "migrate_database", lambda: {"ok": True})
    monkeypatch.setattr(cli, "_hydrate_registry_from_db", lambda: {"ok": True, "imported": 0})
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(cli, "write_install_state", lambda payload: payload)
    monkeypatch.setattr(
        cli,
        "repair_registered_projects",
        lambda sync=True: (
            calls.append(sync)
            or {
                "ok": True,
                "projects_checked": 2,
                "projects_healthy": 2,
                "nested_detached": 1,
                "projects": [],
                "unresolved": [],
            }
        ),
    )

    result = cli._machine_upgrade(force=False, skip_db=False, sync_projects=True)

    assert calls == [True]
    assert result["machine_upgrade_ok"] is True
    assert result["project_repair"]["nested_detached"] == 1
    assert result["project_sync"] == {
        "total": 2,
        "ok": 2,
        "failed": 0,
        "managed_by": "project_repair",
    }


def test_machine_upgrade_is_degraded_when_registered_project_repair_fails(monkeypatch):
    import importlib

    cli = importlib.import_module("ai_layer.cli.commands.maintenance")
    monkeypatch.setattr(cli, "_install_global_files", lambda force=False: {})
    monkeypatch.setattr(cli, "install_global_integrations", lambda: {})
    monkeypatch.setattr(cli, "start_database", lambda: {"ok": True})
    monkeypatch.setattr(cli, "migrate_database", lambda: {"ok": True})
    monkeypatch.setattr(cli, "_hydrate_registry_from_db", lambda: {"ok": True, "imported": 0})
    monkeypatch.setattr(cli, "database_health", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(cli, "write_install_state", lambda payload: payload)
    monkeypatch.setattr(
        cli,
        "repair_registered_projects",
        lambda sync=True: {
            "ok": False,
            "projects_checked": 2,
            "projects_healthy": 1,
            "projects": [],
            "unresolved": [{"root": "/broken"}],
        },
    )

    result = cli._machine_upgrade(force=False, skip_db=False, sync_projects=True)
    assert result["database_pipeline_ok"] is True
    assert result["project_pipeline_ok"] is False
    assert result["machine_upgrade_ok"] is False
    assert result["install_state"]["last_upgrade_ok"] is False


def test_task_cli_uses_application_control_contract(monkeypatch):
    import importlib

    cli = importlib.import_module("ai_layer.cli.commands.operations")
    monkeypatch.setattr(
        cli,
        "app_task_current",
        lambda path, include_history=False: {
            "active": True,
            "state": "active",
            "task": {"key": "T-0001", "history": include_history},
        },
    )
    monkeypatch.setattr(
        cli,
        "app_task_cancel",
        lambda path, reason: {"status": "cancelled", "completion_summary": reason},
    )

    current = CliRunner().invoke(app, ["task", "current", "--path", "/repo"])
    assert current.exit_code == 0, current.output
    current_payload = json.loads(current.output)
    assert current_payload["task"]["key"] == "T-0001"
    assert current_payload["task"]["history"] is False

    with_history = CliRunner().invoke(app, ["task", "current", "--path", "/repo", "--history"])
    assert with_history.exit_code == 0, with_history.output
    assert json.loads(with_history.output)["task"]["history"] is True

    cancelled = CliRunner().invoke(
        app, ["task", "cancel", "--path", "/repo", "--reason", "transport closed"]
    )
    assert cancelled.exit_code == 0, cancelled.output
    assert json.loads(cancelled.output)["status"] == "cancelled"


def test_skill_cli_add_project_scope_stays_outside_repository(tmp_path: Path, monkeypatch):
    import uuid

    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project

    home = tmp_path / "home"
    project = tmp_path / "repo"
    project.mkdir()
    source = tmp_path / "custom.md"
    source.write_text(
        "---\nslug: repo-specific-contract\ndescription: Repository-specific implementation conventions, architecture constraints, local workflows and safe change guidance for this project.\n---\n# Custom Project Skill\n\n## Core contract\n\nPreserve project-specific behavior.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    try:
        project_id = str(uuid.uuid4())
        register_project(project, project_id=project_id, name="repo")
        result = CliRunner().invoke(
            app,
            [
                "skill",
                "add",
                str(source),
                "--scope",
                "project",
                "--project",
                str(project),
                "--slug",
                "repo-specific-contract",
                "--task-term",
                "repo-contract",
                "--approve",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "installed"
        assert payload["skills"][0]["scope"] == "project"
        assert (home / "project-skills" / project_id / "repo-specific-contract.md").is_file()
        assert not (project / ".ai-layer" / "skills").exists()
    finally:
        get_settings.cache_clear()
