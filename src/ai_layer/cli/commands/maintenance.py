from __future__ import annotations

import os
import tempfile
from pathlib import Path

import typer
import yaml

from ai_layer import __version__
from ai_layer.application.projects import hydrate_registry_from_database
from ai_layer.application.runtime import database_health
from ai_layer.cli.root import app, echo
from ai_layer.core.config import get_settings
from ai_layer.core.paths import project_config_path
from ai_layer.core.registry import list_registered_projects
from ai_layer.core.repair import repair_registered_projects
from ai_layer.core.runtime import migrate_database, start_database, write_install_state
from ai_layer.core.service import sync_project_integrations
from ai_layer.integrations.service import (
    INTEGRATION_TEMPLATE_VERSION,
    install_global_integrations,
    remove_global_integrations,
    remove_project_integrations,
)
from ai_layer.policy.service import ensure_global_policy
from ai_layer.privacy.service import remove_git_privacy_guard
from ai_layer.skills.service import install_builtin_skills


def _atomic_private_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _install_global_files(force: bool = False) -> dict:
    settings = get_settings()
    settings.home.mkdir(parents=True, exist_ok=True)
    installed = install_builtin_skills(force=force)
    policy = ensure_global_policy(force=force)
    # `config.yaml` is diagnostic machine state, not an input source. Never persist the configured
    # database URL because it can contain a real password/token. Rewrite legacy files on upgrade so
    # credentials written by older v0.1.x releases are removed even without --force-templates.
    config_data: dict = {}
    existing_config: str | None = None
    if settings.config_file.exists():
        try:
            existing_config = settings.config_file.read_text(encoding="utf-8")
            loaded = yaml.safe_load(existing_config) or {}
            if isinstance(loaded, dict):
                config_data = loaded
        except (OSError, yaml.YAMLError):
            config_data = {}
            existing_config = None
    config_data.pop("database_url", None)
    config_data.update(
        {
            "version": __version__,
            "database_configuration": "AI_LAYER_DATABASE_URL process environment or built-in local default",
            "database_credentials_persisted": False,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
        }
    )
    config_content = yaml.safe_dump(config_data, sort_keys=False)
    if force or existing_config != config_content:
        _atomic_private_text(settings.config_file, config_content)
    elif settings.config_file.exists():
        os.chmod(settings.config_file, 0o600)
    return {"home": str(settings.home), "skills": installed, "policy": str(policy)}


def _hydrate_registry_from_db() -> dict:
    """Import legacy database rows into the durable machine registry through an application use case."""
    try:
        return hydrate_registry_from_database()
    except Exception as exc:
        return {"ok": False, "imported": 0, "error": str(exc)}


def _sync_registered_projects() -> dict:
    results: list[dict] = []
    for item in list_registered_projects():
        root = Path(str(item.get("root", "")))
        if not root.exists():
            results.append({"root": str(root), "ok": False, "status": "missing"})
            continue
        if not project_config_path(root).exists():
            results.append({"root": str(root), "ok": False, "status": "not-initialized"})
            continue
        try:
            synced = sync_project_integrations(root)
            results.append(
                {"root": str(root), "ok": True, "template_version": synced["template_version"]}
            )
        except Exception as exc:  # doctor/upgrade should continue through other projects
            results.append({"root": str(root), "ok": False, "status": "error", "error": str(exc)})
    return {
        "total": len(results),
        "ok": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "projects": results,
    }


def _machine_upgrade(*, force: bool, skip_db: bool, sync_projects: bool) -> dict:
    result: dict = {
        "version": __version__,
        "global_files": _install_global_files(force=force),
        "global_integrations": install_global_integrations(),
    }
    database_pipeline_ok = bool(skip_db)
    if skip_db:
        result["database"] = {"skipped": True, "state": database_health()}
    else:
        started = start_database()
        result["database_start"] = started
        if started.get("ok"):
            try:
                migration = migrate_database()
            except Exception as exc:  # upgrade must return actionable JSON instead of a traceback
                migration = {"ok": False, "error": str(exc)}
            result["database_migration"] = migration
            if migration.get("ok"):
                result["registry_import"] = _hydrate_registry_from_db()
                database_pipeline_ok = True
            else:
                result["registry_import"] = {"ok": False, "skipped": True}
        else:
            result["database_migration"] = {
                "ok": False,
                "skipped": True,
                "reason": started.get("error"),
            }
            result["registry_import"] = {"ok": False, "skipped": True}
    if sync_projects and database_pipeline_ok:
        repair = repair_registered_projects(sync=True)
        result["project_repair"] = repair
        # Keep the older project_sync summary key for machine-readable compatibility. Since v0.2.5
        # synchronization is performed inside the repair pass so structural conflicts are fixed
        # before adapters are refreshed.
        result["project_sync"] = {
            "total": repair.get("projects_checked", 0),
            "ok": repair.get("projects_healthy", 0),
            "failed": max(0, repair.get("projects_checked", 0) - repair.get("projects_healthy", 0)),
            "managed_by": "project_repair",
        }
    elif sync_projects:
        result["project_repair"] = {
            "skipped": True,
            "reason": "database migration/bootstrap did not complete",
        }
        result["project_sync"] = {
            "skipped": True,
            "reason": "database migration/bootstrap did not complete",
        }
    else:
        result["project_repair"] = {"skipped": True}
        result["project_sync"] = {"skipped": True}
    project_pipeline_ok = True
    if sync_projects:
        project_pipeline_ok = bool((result.get("project_repair") or {}).get("ok"))
    machine_upgrade_ok = bool(database_pipeline_ok and project_pipeline_ok)
    result["database_pipeline_ok"] = bool(database_pipeline_ok)
    result["project_pipeline_ok"] = bool(project_pipeline_ok) if sync_projects else None
    result["machine_upgrade_ok"] = machine_upgrade_ok
    db_state = database_health()
    result["install_state"] = write_install_state(
        {
            "integration_template_version": INTEGRATION_TEMPLATE_VERSION,
            # This is dependency readiness, not whether the compose start command ran.
            "database_ready": bool(db_state.get("connected") and db_state.get("pgvector")),
            "last_upgrade_ok": machine_upgrade_ok,
        }
    )
    return result


def install(force: bool = typer.Option(False, help="Rewrite built-in global files.")):
    """Low-level install of ~/.ai-layer files. Normal users should use ./install.sh."""
    echo(
        {
            "ok": True,
            **_install_global_files(force=force),
            "next": "Use ./install.sh for full machine setup.",
        }
    )


def uninstall_integrations():
    """Remove AI Layer-owned host/project integration residue without touching user-owned files."""
    projects: list[dict] = []
    for item in list_registered_projects():
        raw = str(item.get("root") or "").strip()
        if not raw:
            continue
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            projects.append({"root": str(root), "removed": False, "reason": "missing"})
            continue
        try:
            integration = remove_project_integrations(root)
            privacy_guard = remove_git_privacy_guard(root)
            projects.append(
                {
                    "root": str(root),
                    "removed": True,
                    "integration": integration,
                    "privacy_guard": privacy_guard,
                }
            )
        except Exception as exc:
            projects.append({"root": str(root), "removed": False, "error": str(exc)})
    global_result = remove_global_integrations()
    ok = all(not item.get("error") for item in projects)
    echo({"ok": ok, "global": global_result, "projects": projects})
    if not ok:
        raise typer.Exit(1)


# Focused command registration: importing this module extends the root composition without
# growing one central CLI module.
app.command()(install)
app.command("uninstall-integrations")(uninstall_integrations)
