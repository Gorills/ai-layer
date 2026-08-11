from __future__ import annotations

import time
from pathlib import Path

import typer

from ai_layer import __version__
from ai_layer.application.projects import get_project_info as app_project_info
from ai_layer.application.projects import initialize_project
from ai_layer.application.projects import remove_project as app_remove_project
from ai_layer.application.projects import scan_project as app_scan_project
from ai_layer.application.runtime import database_health
from ai_layer.application.tasks import cancel as app_task_cancel
from ai_layer.application.tasks import current as app_task_current
from ai_layer.application.tasks import next_action as app_task_next
from ai_layer.application.tasks import resume as app_task_resume
from ai_layer.application.tasks import worker_disconnected as app_worker_disconnected
from ai_layer.application.tasks import worker_heartbeat as app_worker_heartbeat
from ai_layer.audit.service import audit_path, check_latest_flow, read_audit
from ai_layer.cli.commands.maintenance import _machine_upgrade
from ai_layer.cli.doctor import DoctorDependencies, doctor_report
from ai_layer.cli.root import app, audit_app, echo, projects_app, task_app
from ai_layer.core.background_service import service_status
from ai_layer.core.config import get_settings
from ai_layer.core.mcp_process import list_mcp_processes, stop_user_mcp_processes
from ai_layer.core.paths import (
    normalize_root,
    project_config_path,
    project_meta_dir,
    project_mode,
    project_provenance,
)
from ai_layer.core.registry import (
    get_registered_project,
    list_registered_projects,
    overlapping_registered_projects,
    prune_registry,
    unregister_project,
)
from ai_layer.core.repair import repair_project, repair_registered_projects
from ai_layer.core.runtime import docker_compose_available, migrate_database, read_install_state
from ai_layer.core.service import sync_project_integrations
from ai_layer.domain.errors import normalize_error
from ai_layer.integrations.service import (
    INTEGRATION_TEMPLATE_VERSION,
    global_bootstrap_status,
    global_integration_status,
    integration_status,
)
from ai_layer.observability.render import render_monitor, render_status
from ai_layer.observability.service import observability_snapshot
from ai_layer.privacy.service import git_privacy_guard_status, privacy_check, repository_footprint


def db_init():
    """Initialize/repair the database exclusively through Alembic migrations."""
    result = migrate_database()
    echo({"ok": bool(result.get("ok")), "database": "initialized", "migration": result})


def bootstrap(
    skip_db: bool = typer.Option(False, "--skip-db", help="Do not start/migrate PostgreSQL."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Do not re-sync registered projects."),
):
    """Initialize machine state after the package is installed. Idempotent."""
    result = _machine_upgrade(force=True, skip_db=skip_db, sync_projects=not no_sync)
    echo({"ok": bool(result.get("machine_upgrade_ok")), **result})


def upgrade(
    skip_db: bool = typer.Option(False, "--skip-db", help="Do not start/migrate PostgreSQL."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Do not re-sync registered projects."),
    force_templates: bool = typer.Option(
        False,
        "--force-templates",
        help="Rewrite built-in skills/policy even when files already exist.",
    ),
):
    """Repair/update machine state for the currently installed release.

    This command repairs machine state for the active runtime. Use `ai-layer update` to securely
    obtain and switch to a newer signed release.
    """
    result = _machine_upgrade(force=force_templates, skip_db=skip_db, sync_projects=not no_sync)
    ok = bool(result.get("machine_upgrade_ok"))
    echo({"ok": ok, **result})
    if not ok:
        raise typer.Exit(1)


def sync(
    path: str = typer.Argument("."),
    scan: bool = typer.Option(
        False, "--scan", help="Also rebuild project memory after syncing adapters."
    ),
):
    """Idempotently refresh host rules/skills/MCP adapters for one initialized project."""
    result = sync_project_integrations(path)
    payload: dict = {"ok": True, "sync": result}
    if scan:
        payload["scan"] = app_scan_project(path)
    echo(payload)


def repair(
    path: str | None = typer.Option(
        None, "--path", help="Repair one registered project instead of all registered projects."
    ),
    no_sync: bool = typer.Option(
        False,
        "--no-sync",
        help="Repair structural/privacy residue without refreshing current integration templates.",
    ),
):
    """Safely repair registered projects; defaults to the whole machine registry.

    Automatic repair never rewrites arbitrary user source files. Accidental nested registrations
    are detached with their AI-owned state archived under ~/.ai-layer/recovery. Remaining
    user-owned privacy/provenance conflicts are reported with exact paths for manual review.
    """
    result = (
        repair_project(path, sync=not no_sync)
        if path
        else repair_registered_projects(sync=not no_sync)
    )
    echo({"ok": bool(result.get("ok")), "repair": result})
    if not result.get("ok", False):
        raise typer.Exit(1)


def doctor(
    path: str | None = typer.Option(
        None, "--path", help="Check one project in addition to machine state."
    ),
    all_projects: bool = typer.Option(
        False, "--all-projects", help="Check every project in the machine registry."
    ),
    machine_only: bool = typer.Option(
        False,
        "--machine-only",
        help="Check only machine/runtime dependencies; ignore project health.",
    ),
):
    """Diagnose the installed release, DB, global MCP and project integration drift."""
    deps = DoctorDependencies(
        version=__version__,
        integration_template_version=INTEGRATION_TEMPLATE_VERSION,
        get_settings=get_settings,
        docker_compose_available=docker_compose_available,
        database_status=database_health,
        global_integration_status=global_integration_status,
        global_bootstrap_status=global_bootstrap_status,
        list_registered_projects=list_registered_projects,
        list_mcp_processes=list_mcp_processes,
        read_install_state=read_install_state,
        service_status=service_status,
        get_registered_project=get_registered_project,
        normalize_root=normalize_root,
        project_config_path=project_config_path,
        project_mode=project_mode,
        project_provenance=project_provenance,
        project_meta_dir=project_meta_dir,
        integration_status=integration_status,
        repository_footprint=repository_footprint,
        privacy_check=privacy_check,
        git_privacy_guard_status=git_privacy_guard_status,
        overlapping_registered_projects=overlapping_registered_projects,
    )
    try:
        result = doctor_report(
            deps, path=path, all_projects=all_projects, machine_only=machine_only
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    echo(result)
    if not result["ok"]:
        raise typer.Exit(1)


def mcp_stop():
    """Internal installer hook: terminate long-lived MCP processes after a successful upgrade."""
    echo(stop_user_mcp_processes())


def status(
    human: bool = typer.Option(
        False, "--human", help="Show a compact human-readable runtime snapshot."
    ),
):
    """Compact current status. Use `ai-layer monitor` for live activity and `doctor` for diagnostics."""
    if human:
        typer.echo(render_status(observability_snapshot(include_handoff_text=True)))
        return
    settings = get_settings()
    registered = (
        get_registered_project(Path.cwd()) is not None and project_config_path(Path.cwd()).exists()
    )
    task_recovery = None
    if registered:
        try:
            task_recovery = app_task_current(Path.cwd(), include_history=False)
        except Exception as exc:
            task_recovery = {
                "available": False,
                "error": normalize_error(exc).to_dict(),
                "recovery": "Use `ai-layer task current --path <project>` after database availability is restored.",
            }
    echo(
        {
            "version": __version__,
            "home": str(settings.home),
            "global_install": settings.config_file.exists(),
            "database": database_health(),
            "service": service_status(),
            "project_initialized": registered,
            "integrations": integration_status(Path.cwd()),
            "task_recovery": task_recovery,
            "transport_independent_task_commands": [
                "ai-layer task next --path <project>",
                "ai-layer task current --path <project>",
                "ai-layer task cancel --reason <reason> --path <project>",
                "ai-layer task resume --path <project>",
            ],
        }
    )


def task_current_cmd(
    path: str = typer.Option(".", "--path", help="Registered project path."),
    history: bool = typer.Option(
        False,
        "--history",
        help="Include completed stage/finding history; compact recovery is the default.",
    ),
):
    """Read durable task state directly from PostgreSQL; does not require a live MCP transport."""
    echo(app_task_current(path, include_history=history))


def task_next_cmd(path: str = typer.Option(".", "--path", help="Registered project path.")):
    """Return the one next allowed workflow action directly from durable state."""
    echo(app_task_next(path))


def task_cancel_cmd(
    reason: str = typer.Option(..., "--reason", help="Why the current task is being abandoned."),
    path: str = typer.Option(".", "--path", help="Registered project path."),
):
    """Cancel the current task directly through the durable DB path when MCP is unavailable."""
    echo(app_task_cancel(path, reason=reason))


def task_worker_disconnected_cmd(
    reason: str = typer.Option(
        ..., "--reason", help="Why the bound worker is known to be disconnected."
    ),
    path: str = typer.Option(".", "--path", help="Registered project path."),
):
    """Recover a host-reported lost worker without retroactively rebinding its changes."""
    echo(app_worker_disconnected(path, reason=reason))


def task_worker_heartbeat_cmd(
    worker_id: str = typer.Option(..., "--worker-id", help="Currently delegated worker identity."),
    path: str = typer.Option(".", "--path", help="Registered project path."),
):
    """Renew the durable lease for the currently delegated worker."""
    echo(app_worker_heartbeat(path, worker_id=worker_id))


def task_resume_cmd(path: str = typer.Option(".", "--path", help="Registered project path.")):
    """Explicitly resume a blocked task directly through PostgreSQL, including human-attention stops."""
    echo(app_task_resume(path))


def monitor(
    path: str | None = typer.Option(
        None, "--path", help="Monitor the registered project containing this path."
    ),
    all_projects: bool = typer.Option(False, "--all", help="Monitor every registered project."),
    once: bool = typer.Option(False, "--once", help="Render one snapshot and exit."),
    interval: float = typer.Option(
        1.0, "--interval", min=0.2, max=30.0, help="Live refresh interval in seconds."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Return one machine-readable snapshot and exit."
    ),
):
    """Live privacy-minimal view of agents, MCP calls, memory refreshes and recent activity."""
    if path and all_projects:
        raise typer.BadParameter("--path cannot be combined with --all")

    def snapshot(*, include_handoff_text: bool = False) -> dict:
        return observability_snapshot(
            path,
            all_projects=all_projects,
            include_handoff_text=include_handoff_text,
        )

    if json_output:
        echo(snapshot(include_handoff_text=False))
        return
    if once:
        typer.echo(render_monitor(snapshot(include_handoff_text=True)))
        return

    try:
        while True:
            current = snapshot(include_handoff_text=True)
            typer.echo("\033[2J\033[H", nl=False)
            typer.echo(render_monitor(current))
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo()


def init(
    path: str = typer.Argument("."),
    name: str | None = typer.Option(None),
    private: bool = typer.Option(
        False,
        "--private",
        help="Use zero-footprint external state and forbid AI-development provenance.",
    ),
    external: bool = typer.Option(
        False,
        "--external",
        help="Use zero-footprint external state without enabling provenance restrictions.",
    ),
):
    """Register a project using standard adapters or zero-footprint external attachment."""
    if private and external:
        raise typer.BadParameter("--private and --external are mutually exclusive")
    project = initialize_project(path, name, private=private, external=external)
    root = Path(project["root_path"])
    echo(
        {
            "ok": True,
            "project_id": project["id"],
            "root": project["root_path"],
            "mode": project_mode(root),
            "provenance": project_provenance(root),
            "integration_template_version": INTEGRATION_TEMPLATE_VERSION,
            "workflow": "AI Layer MCP is mandatory for registered-project engineering tasks.",
            "repository_footprint": repository_footprint(root)
            if project_mode(root) in {"external", "strict-private"}
            else None,
            "next": "ai-layer scan",
        }
    )


def privacy_enable(path: str = typer.Argument(".")):
    """Convert an initialized/registered project to strict-private external-state mode."""
    project = initialize_project(path, private=True)
    root = Path(project["root_path"])
    echo(
        {
            "ok": True,
            "root": project["root_path"],
            "mode": project_mode(root),
            "provenance": project_provenance(root),
            "footprint": repository_footprint(root),
            "git_guard": git_privacy_guard_status(root),
        }
    )


def privacy_check_cmd(
    path: str = typer.Option(".", "--path", help="Project path."),
    staged: bool = typer.Option(
        False, "--staged", help="Check staged Git content instead of working-tree changes."
    ),
    commit_message: str | None = typer.Option(
        None, "--commit-message", help="Commit message file path for commit-msg hook."
    ),
):
    """Fail when strict-private changed/staged content contains prohibited AI provenance."""
    result = privacy_check(path, staged=staged, commit_message=commit_message)
    echo(result)
    if not result.get("ok", False):
        raise typer.Exit(1)


def scan(path: str = typer.Argument(".")):
    """Refresh deterministic repository evidence/freshness; does not build a parallel source-code memory index."""
    echo({"ok": True, **app_scan_project(path)})


def info(path: str = typer.Argument(".")):
    echo(app_project_info(path))


def projects_list():
    echo({"projects": list_registered_projects()})


def projects_unregister(path: str = typer.Argument(".")):
    """Durably forget exactly one project without deleting its AI Layer data."""
    echo({"ok": True, **unregister_project(path)})


def projects_remove(
    path: str = typer.Argument("."),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm deletion of AI Layer-owned state for this exact root."
    ),
):
    """Remove an accidental project registration, its AI-owned bridges/state, and its DB project row."""
    if not yes:
        raise typer.BadParameter(
            "--yes is required because this deletes AI Layer memory/session/decision state for the selected root"
        )
    echo({"ok": True, **app_remove_project(path)})


def projects_prune():
    echo({"ok": True, **prune_registry()})


def audit_tail(
    path: str = typer.Option(".", "--path", help="Initialized project path."),
    limit: int = typer.Option(30, "--limit", min=1, max=500),
):
    """Show recent MCP tool calls without prompt/result contents."""
    root = normalize_root(path)
    echo({"path": str(audit_path(root)), "events": read_audit(root, limit)})


def audit_check(
    path: str = typer.Option(".", "--path", help="Initialized project path."),
    limit: int = typer.Option(200, "--limit", min=10, max=1000),
):
    """Verify the latest memory_context -> ... -> session_save MCP flow for QA."""
    root = normalize_root(path)
    result = check_latest_flow(root, limit)
    echo({"path": str(audit_path(root)), **result})
    if not result.get("ok"):
        raise typer.Exit(1)


# Public CLI contract registrations.
app.command("db-init")(db_init)
app.command()(bootstrap)
app.command()(upgrade)
app.command()(sync)
app.command()(repair)
app.command()(doctor)
app.command("mcp-stop", hidden=True)(mcp_stop)
app.command()(status)
task_app.command("current")(task_current_cmd)
task_app.command("next")(task_next_cmd)
task_app.command("cancel")(task_cancel_cmd)
task_app.command("worker-disconnected")(task_worker_disconnected_cmd)
task_app.command("worker-heartbeat")(task_worker_heartbeat_cmd)
task_app.command("resume")(task_resume_cmd)
app.command()(monitor)
app.command()(init)
app.command("privacy-enable")(privacy_enable)
app.command("privacy-check")(privacy_check_cmd)
app.command()(scan)
app.command()(info)
projects_app.command("list")(projects_list)
projects_app.command("unregister")(projects_unregister)
projects_app.command("remove")(projects_remove)
projects_app.command("prune")(projects_prune)
audit_app.command("tail")(audit_tail)
audit_app.command("check")(audit_check)
