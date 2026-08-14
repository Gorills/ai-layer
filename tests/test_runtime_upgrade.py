from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_layer.core import runtime


class Proc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def test_start_database_accepts_already_ready_db(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runtime, "compose_file", lambda: tmp_path / "docker-compose.yml")
    monkeypatch.setattr(runtime, "database_status", lambda: {"connected": True, "pgvector": True})
    monkeypatch.setattr(
        runtime,
        "docker_compose_available",
        lambda: (_ for _ in ()).throw(AssertionError("Docker should not be touched")),
    )

    result = runtime.start_database(timeout=0)

    assert result["ok"] is True
    assert result["mode"] == "already-ready"


def test_start_database_adopts_stopped_legacy_container(monkeypatch, tmp_path: Path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "compose_file", lambda: compose)
    states = iter(
        [
            {"connected": False, "pgvector": False},
            {"connected": True, "pgvector": True},
        ]
    )
    monkeypatch.setattr(runtime, "database_status", lambda: next(states))
    monkeypatch.setattr(runtime, "docker_compose_available", lambda: (True, "/usr/bin/docker"))

    calls: list[list[str]] = []

    def fake_run(args, capture_output=True, text=True, **kwargs):
        calls.append(list(args))
        if args[1:4] == ["inspect", "-f", "{{.State.Running}}"]:
            return Proc(returncode=0, stdout="false\n", stderr="")
        if args[1:4] == ["inspect", "-f", "{{json .Config.Env}}"]:
            env = json.dumps(["POSTGRES_DB=ai_layer", "POSTGRES_USER=ai_layer"])
            return Proc(returncode=0, stdout=env, stderr="")
        if args[1:] == ["start", "ai-layer-postgres"]:
            return Proc(returncode=0, stdout="ai-layer-postgres\n", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    result = runtime.start_database(timeout=0)

    assert result["ok"] is True
    assert result["mode"] == "legacy-container"
    assert ["/usr/bin/docker", "start", "ai-layer-postgres"] in calls


def test_start_database_refuses_unrelated_name_conflict(monkeypatch, tmp_path: Path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "compose_file", lambda: compose)
    monkeypatch.setattr(runtime, "database_status", lambda: {"connected": False, "pgvector": False})
    monkeypatch.setattr(runtime, "docker_compose_available", lambda: (True, "/usr/bin/docker"))

    def fake_run(args, capture_output=True, text=True, **kwargs):
        if args[1:4] == ["inspect", "-f", "{{.State.Running}}"]:
            return Proc(returncode=0, stdout="true\n", stderr="")
        if args[1:4] == ["inspect", "-f", "{{json .Config.Env}}"]:
            return Proc(returncode=0, stdout=json.dumps(["POSTGRES_DB=other"]), stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    result = runtime.start_database(timeout=0)

    assert result["ok"] is False
    assert result["mode"] == "container-name-conflict"
    assert "left untouched" in result["error"]


def test_legacy_migration_stamps_0001_then_upgrades_head(monkeypatch):
    class Inspector:
        def get_table_names(self):
            return [
                "projects",
                "project_files",
                "knowledge",
                "decisions",
                "sessions",
                "project_skills",
            ]

        def get_columns(self, table):
            if table == "sessions":
                return [{"name": "id"}, {"name": "goal"}]
            if table == "project_files":
                return [{"name": "id"}, {"name": "sha256"}]
            return [{"name": "id"}]

    monkeypatch.setattr(runtime, "get_engine", lambda: object())
    monkeypatch.setattr(runtime, "inspect", lambda engine: Inspector())
    monkeypatch.setattr(runtime, "_alembic_config", lambda: object())
    calls = []
    monkeypatch.setattr(runtime.command, "stamp", lambda cfg, rev: calls.append(("stamp", rev)))
    monkeypatch.setattr(runtime.command, "upgrade", lambda cfg, rev: calls.append(("upgrade", rev)))

    result = runtime.migrate_database()

    assert result["ok"] is True
    assert calls == [("stamp", "0001_initial"), ("upgrade", "head")]


def test_session_evidence_default_migration_is_present_and_backward_compatible():
    migration = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0003_session_evidence_defaults.py"
    )
    text = migration.read_text(encoding="utf-8")
    assert 'down_revision = "0002_session_evidence"' in text
    assert "server_default=sa.text(\"'[]'::json\")" in text
    assert 'op.alter_column(\n        "sessions",\n        "verified_facts"' in text


def test_install_state_write_is_private_and_atomic(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        home=tmp_path,
        install_state_file=tmp_path / "install.json",
        runtime_home=tmp_path / "runtime-home",
        stable_mcp_executable=tmp_path / "runtime-home" / "current" / "bin" / "ai-layer-mcp",
    )
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)

    payload = runtime.write_install_state({"last_upgrade_ok": True})

    written = json.loads(settings.install_state_file.read_text(encoding="utf-8"))
    assert written["version"] == payload["version"]
    assert written["last_upgrade_ok"] is True
    assert settings.install_state_file.stat().st_mode & 0o077 == 0
    assert not list(tmp_path.glob(".install.json.*"))


def test_installer_restarts_mcp_only_after_success_gate():
    script = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    fail_gate = script.index("if [[ $UPGRADE_STATUS -ne 0 ]]")
    restart = script.index("mcp-stop")
    cleanup = script.index('rm -rf "$STATE_HOME/runtime.previous"', restart)
    assert restart > fail_gate
    assert cleanup > restart


def test_installer_success_gate_checks_machine_only_not_all_registered_projects():
    script = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    gate_section = script[
        script.index("if [[ $UPGRADE_STATUS -eq 0 && $SKIP_DB -eq 0 ]]") : script.index(
            "if [[ $UPGRADE_STATUS -ne 0 ]]"
        )
    ]
    assert "doctor --machine-only" in gate_section
    assert "doctor --all-projects" not in gate_section


def test_alembic_revision_ids_fit_default_version_table_column():
    versions_dir = Path(__file__).parents[1] / "alembic" / "versions"
    for migration in sorted(versions_dir.glob("*.py")):
        tree = ast.parse(migration.read_text(encoding="utf-8"), filename=str(migration))
        revision = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "revision" for target in node.targets
            ):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    revision = node.value.value
                    break
        assert revision is not None, f"missing Alembic revision id in {migration.name}"
        assert len(revision) <= 32, (
            f"Alembic revision id {revision!r} in {migration.name} exceeds the default "
            "alembic_version.version_num VARCHAR(32) contract"
        )


def test_incremental_content_identity_migration_extends_existing_project_files_in_place():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "0004_incremental_identity.py"
    text = migration.read_text(encoding="utf-8")
    assert 'down_revision = "0003_session_evidence_defaults"' in text
    assert 'sa.Column("content_sha256", sa.String(length=64), nullable=True)' in text
    assert 'sa.Column("mtime_ns", sa.BigInteger()' in text
    assert 'sa.Column("ctime_ns", sa.BigInteger()' in text
    assert 'sa.Column("indexed", sa.Boolean()' in text
    assert 'sa.Column("scanner_schema", sa.Integer()' in text
    assert "UPDATE project_files SET content_sha256 = sha256" in text
    assert 'op.drop_column("project_files", "content_sha256")' in text


def test_unversioned_current_head_schema_is_stamped_at_0005_not_0001(monkeypatch):
    class Inspector:
        def get_table_names(self):
            return [
                "projects",
                "project_files",
                "knowledge",
                "decisions",
                "sessions",
                "project_skills",
                "tasks",
                "task_stages",
                "review_findings",
            ]

        def get_columns(self, table):
            if table == "sessions":
                return [
                    {"name": "id", "default": None},
                    {"name": "verified_facts", "default": "'[]'::json"},
                    {"name": "notable_findings", "default": "'[]'::json"},
                ]
            if table == "project_files":
                return [
                    {"name": "id"},
                    {"name": "content_sha256"},
                    {"name": "mtime_ns"},
                    {"name": "ctime_ns"},
                    {"name": "indexed"},
                    {"name": "scanner_schema"},
                ]
            return [{"name": "id"}]

    monkeypatch.setattr(runtime, "get_engine", lambda: object())
    monkeypatch.setattr(runtime, "inspect", lambda engine: Inspector())
    monkeypatch.setattr(runtime, "_alembic_config", lambda: object())
    calls = []
    monkeypatch.setattr(runtime.command, "stamp", lambda cfg, rev: calls.append(("stamp", rev)))
    monkeypatch.setattr(runtime.command, "upgrade", lambda cfg, rev: calls.append(("upgrade", rev)))

    result = runtime.migrate_database()
    assert result["ok"] is True
    assert calls == [("stamp", "0005_task_execution"), ("upgrade", "head")]


def test_unversioned_partial_schema_fails_closed():
    class Inspector:
        def get_columns(self, table):
            if table == "sessions":
                return [{"name": "id"}, {"name": "verified_facts"}]
            if table == "project_files":
                return [{"name": "id"}, {"name": "sha256"}]
            return [{"name": "id"}]

    tables = {"projects", "project_files", "knowledge", "decisions", "sessions", "project_skills"}
    try:
        runtime._detect_unversioned_revision(Inspector(), tables)
    except RuntimeError as exc:
        assert "partially migrated" in str(exc)
    else:
        raise AssertionError("partial unversioned schema must never be guessed/stamped")


def test_unversioned_hardened_task_schema_is_stamped_at_0006(monkeypatch):
    class Inspector:
        def get_table_names(self):
            return [
                "projects",
                "project_files",
                "knowledge",
                "decisions",
                "sessions",
                "project_skills",
                "tasks",
                "task_stages",
                "review_findings",
            ]

        def get_columns(self, table):
            if table == "sessions":
                return [
                    {"name": "id", "default": None},
                    {"name": "verified_facts", "default": "'[]'::json"},
                    {"name": "notable_findings", "default": "'[]'::json"},
                ]
            if table == "project_files":
                return [
                    {"name": "id"},
                    {"name": "content_sha256"},
                    {"name": "mtime_ns"},
                    {"name": "ctime_ns"},
                    {"name": "indexed"},
                    {"name": "scanner_schema"},
                ]
            if table == "review_findings":
                return [
                    {"name": "id"},
                    {"name": "verification_evidence"},
                    {"name": "verification_history"},
                    {"name": "verified_by_stage_id"},
                ]
            if table == "tasks":
                # A current create_all schema may already contain 0007 ORM columns. Stamping 0006
                # lets the idempotent 0007 migration reconcile them and auxiliary indexes safely.
                return [{"name": "id"}, {"name": "execution_origin"}, {"name": "adopted_changes"}]
            return [{"name": "id"}]

    monkeypatch.setattr(runtime, "get_engine", lambda: object())
    monkeypatch.setattr(runtime, "inspect", lambda engine: Inspector())
    monkeypatch.setattr(runtime, "_alembic_config", lambda: object())
    calls = []
    monkeypatch.setattr(runtime.command, "stamp", lambda cfg, rev: calls.append(("stamp", rev)))
    monkeypatch.setattr(runtime.command, "upgrade", lambda cfg, rev: calls.append(("upgrade", rev)))

    result = runtime.migrate_database()
    assert result["ok"] is True
    assert calls == [("stamp", "0006_hardening"), ("upgrade", "head")]


def test_unversioned_partial_hardening_fails_closed():
    class Inspector:
        def get_columns(self, table):
            if table == "sessions":
                return [
                    {"name": "id", "default": None},
                    {"name": "verified_facts", "default": "'[]'::json"},
                    {"name": "notable_findings", "default": "'[]'::json"},
                ]
            if table == "project_files":
                return [
                    {"name": "id"},
                    {"name": "content_sha256"},
                    {"name": "mtime_ns"},
                    {"name": "ctime_ns"},
                    {"name": "indexed"},
                    {"name": "scanner_schema"},
                ]
            if table == "review_findings":
                return [{"name": "id"}, {"name": "verification_evidence"}]
            return [{"name": "id"}]

    tables = {
        "projects",
        "project_files",
        "knowledge",
        "decisions",
        "sessions",
        "project_skills",
        "tasks",
        "task_stages",
        "review_findings",
    }
    with pytest.raises(RuntimeError, match="partially hardened"):
        runtime._detect_unversioned_revision(Inspector(), tables)


def test_workflow_navigation_migration_preserves_legacy_active_stage_compatibility():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "0008_workflow_navigation.py"
    text = migration.read_text(encoding="utf-8")
    assert 'down_revision = "0007_task_adoption"' in text
    assert '"delegation_required"' in text
    assert "sa.Boolean()" in text
    assert "server_default=sa.false()" in text
    assert 'sa.Column("delegated_at", sa.DateTime(timezone=True), nullable=True)' in text
    assert '"external_actions"' in text
    assert "sa.JSON()" in text
    assert "server_default=sa.text" in text
    assert "'[]'::json" in text
    assert 'op.alter_column("task_stages", "delegation_required", server_default=None)' in text


def test_project_intelligence_migration_adds_durable_json_without_rewriting_task_state():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "0009_project_intelligence.py"
    text = migration.read_text(encoding="utf-8")
    assert 'down_revision = "0008_workflow_navigation"' in text
    assert '"project_intelligence"' in text
    assert "sa.JSON()" in text
    assert "nullable=False" in text
    assert "server_default=sa.text(\"'{}'\")" in text
    assert '"task_stages"' not in text
    assert '"tasks"' not in text


def test_adaptive_workflow_migration_keeps_existing_tasks_on_legacy_v1():
    migration = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0010_adaptive_task_workflow.py"
    )
    text = migration.read_text(encoding="utf-8")
    assert 'server_default="1"' in text
    assert 'server_default="legacy_standard"' in text
    assert '"workflow_version"' in text
    assert '"workflow_profile"' in text
    assert '"agent_tier"' in text
    assert '"agent_model"' in text
    assert '"readonly_required"' in text
    assert "Existing in-flight/completed tasks retain workflow v1 semantics" in text


def test_read_install_state_treats_invalid_utf8_as_missing(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(install_state_file=tmp_path / "install.json")
    settings.install_state_file.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    assert runtime.read_install_state() == {}


def test_dirty_task_baseline_migration_adds_preexisting_provenance_without_content_storage():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "0013_dirty_task_baselines.py"
    text = migration.read_text(encoding="utf-8")
    assert 'down_revision = "0012_architecture_hardening"' in text
    assert '"preexisting_changes"' in text
    assert "sa.JSON()" in text
    assert "repository_snapshots" not in text
    assert "LargeBinary" not in text


def test_command_receipt_scope_migration_replaces_global_command_id_uniqueness():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "0018_command_project_scope.py"
    text = migration.read_text(encoding="utf-8")
    assert 'revision = "0018_command_project_scope"' in text
    assert 'down_revision = "0017_work_spine"' in text
    assert 'op.drop_constraint("uq_command_receipts_command_id"' in text
    assert '"uq_command_receipts_project_command"' in text
    assert '["project_id", "command_id"]' in text
