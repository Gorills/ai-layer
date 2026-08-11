from __future__ import annotations
from ai_layer.cli.root import app, mcp_app, memory_app, service_app, session_app, echo
from ai_layer.core.background_service import DEFAULT_HOST
from ai_layer.core.background_service import DEFAULT_PORT
from ai_layer.integrations.service import _merge_mcp_json
from ai_layer.application.context import search_memory as app_memory_search
from ai_layer.application.projects import scan_project as app_scan_project
from ai_layer.application.runtime import database_health
from ai_layer.core.config import get_settings
from ai_layer.core.background_service import install_user_service
import ipaddress
from ai_layer.core.mcp_process import list_mcp_processes
from ai_layer.core.paths import normalize_root
from ai_layer.privacy.service import privacy_check
from ai_layer.core.background_service import probe_service
from ai_layer.core.paths import project_local_path
from ai_layer.core.paths import project_mode
from ai_layer.core.background_service import restart_user_service
from ai_layer.application.sessions import restore_project_session
from ai_layer.application.sessions import save_project_session
from ai_layer.core.background_service import service_status
from ai_layer.core.background_service import service_url
from ai_layer.core.background_service import start_user_service
from ai_layer.core.background_service import stop_user_service
import typer
from ai_layer.core.background_service import uninstall_user_service
import uvicorn
from ai_layer.core.background_service import wait_for_service
import webbrowser


def memory_search_cmd(
    query: str, path: str = typer.Option(".", "--path"), limit: int = typer.Option(8, min=1, max=30)
):
    echo(app_memory_search(path, query, limit))


def memory_rebuild(path: str = typer.Option(".", "--path")):
    echo(app_scan_project(path))


def session_save(
    goal: str = typer.Option(..., help="Current work goal."),
    state: str = typer.Option(..., help="Current state/handoff summary."),
    done: list[str] = typer.Option([], "--done", help="Completed action; repeatable."),
    next_step: list[str] = typer.Option([], "--next", help="Next step; repeatable."),
    decision: list[str] = typer.Option([], "--decision", help="Important decision; repeatable."),
    fact: list[str] = typer.Option([], "--fact", help="Verified project fact; repeatable."),
    finding: list[str] = typer.Option(
        [], "--finding", help="Notable review/investigation finding; repeatable."
    ),
    path: str = typer.Option(".", "--path"),
):
    root = normalize_root(path)
    check = privacy_check(root)
    if not check.get("ok", True):
        echo(check)
        raise typer.Exit(1)
    echo(
        save_project_session(
            root,
            goal=goal,
            completed_actions=done,
            current_state=state,
            next_steps=next_step,
            important_decisions=decision,
            verified_facts=fact,
            notable_findings=finding,
        )
    )


def session_restore_cmd(
    session_id: str = typer.Argument("latest"), path: str = typer.Option(".", "--path")
):
    item = restore_project_session(path, session_id)
    echo(item if item else {"found": False})


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def health_cmd():
    """Fast machine health view for the persistent core, DB and MCP bridges."""
    service = probe_service(timeout=0.5)
    db = database_health()
    core = service.get("runtime") or {}
    payload = {
        "ok": bool(
            service.get("running") and db.get("connected") and core.get("status") == "ready"
        ),
        "service": service,
        "core_runtime": core,
        "database": db,
        "mcp_processes": list_mcp_processes(),
    }
    echo(payload)
    if not payload["ok"]:
        raise typer.Exit(1)


def mcp_status_cmd():
    """Show persistent MCP core transport and connected stdio bridge processes."""
    service = probe_service(timeout=0.5)
    echo(
        {
            "ok": bool(service.get("running")),
            "core": service,
            "stdio_bridges": list_mcp_processes(),
            "streamable_http": (service.get("runtime") or {}).get("mcp_http_url"),
        }
    )
    if not service.get("running"):
        raise typer.Exit(1)


def serve(host: str = "127.0.0.1", port: int = 8765):
    """Run the unauthenticated local FastAPI server on loopback only."""
    if not _is_loopback_host(host):
        raise typer.BadParameter(
            "The FastAPI surface has no remote authentication; --host must be localhost/loopback."
        )
    uvicorn.run("ai_layer.api.app:app", host=host, port=port, reload=False)


def service_run(
    host: str = typer.Option(DEFAULT_HOST, "--host"),
    port: int = typer.Option(DEFAULT_PORT, "--port"),
):
    """Run the persistent MCP/dashboard core in the foreground on its canonical endpoint."""
    if host != DEFAULT_HOST or port != DEFAULT_PORT:
        raise typer.BadParameter(
            f"The persistent MCP core endpoint is fixed at {DEFAULT_HOST}:{DEFAULT_PORT}; "
            "use `ai-layer serve` for an ad-hoc HTTP-only development port."
        )
    uvicorn.run("ai_layer.api.app:app", host=host, port=port, reload=False)


def service_install(no_start: bool = typer.Option(False, "--no-start")):
    """Install/refresh Linux systemd --user autostart for the persistent core/dashboard service."""
    result = install_user_service(start=not no_start)
    echo(result)
    if not result.get("ok"):
        raise typer.Exit(1)


def service_start():
    """Start the always-on AI Layer core/dashboard service."""
    result = start_user_service()
    echo(result)
    if not result.get("ok"):
        raise typer.Exit(1)


def service_restart():
    """Restart the always-on AI Layer core/dashboard service."""
    result = restart_user_service()
    echo(result)
    if not result.get("ok"):
        raise typer.Exit(1)


def service_stop():
    """Stop the persistent core/dashboard service without removing AI Layer."""
    result = stop_user_service()
    echo(result)
    if not result.get("ok"):
        raise typer.Exit(1)


def service_status_cmd():
    """Show persistent core/dashboard service and autostart state."""
    echo(service_status())


def service_uninstall():
    """Remove the user-level dashboard autostart unit."""
    result = uninstall_user_service()
    echo(result)
    if not result.get("ok"):
        raise typer.Exit(1)


def dashboard(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the browser automatically."),
):
    """Open the always-on local dashboard; start its user service when possible."""
    if not _is_loopback_host(host):
        raise typer.BadParameter(
            "The dashboard is local-only and unauthenticated; --host must be localhost/loopback."
        )
    url = service_url(host, port) + "/dashboard"
    health = probe_service(host, port)
    if not health.get("running") and host == DEFAULT_HOST and port == DEFAULT_PORT:
        started = start_user_service()
        if started.get("ok"):
            health = wait_for_service(host, port)
    typer.echo(f"AI Layer dashboard: {url}")
    if not health.get("running"):
        typer.echo(
            "Background service is not running. Run `ai-layer service install` (Linux) "
            "or `ai-layer service run` for a foreground fallback.",
            err=True,
        )
        raise typer.Exit(1)
    if not no_open:
        webbrowser.open(url)


def mcp():
    """Run the MCP stdio server (normally started by the IDE)."""
    from ai_layer.mcp.server import main

    main()


def mcp_config(
    path: str = typer.Argument("."), write_cursor: bool = typer.Option(False, "--write-cursor")
):
    """Print MCP stdio config, or refresh project integrations for Cursor."""
    root = normalize_root(path)
    settings = get_settings()
    server = {
        "command": str(settings.stable_mcp_executable)
        if settings.stable_mcp_executable.exists()
        else "ai-layer-mcp",
        "args": [],
        "env": {"AI_LAYER_PROJECT_ROOT": str(root), "AI_LAYER_CLIENT": "cursor"},
    }
    payload = {"mcpServers": {"ai-layer": server}}
    if not write_cursor:
        echo(payload)
        return
    if project_mode(root) in {"external", "strict-private"}:
        raise typer.BadParameter(
            "--write-cursor is forbidden for external-state projects; use the global MCP integration."
        )
    target = project_local_path(root, ".cursor", "mcp.json")
    _merge_mcp_json(target, server)
    echo({"ok": True, "written": str(target), "server": server})


# Public CLI contract registrations.
memory_app.command("search")(memory_search_cmd)
memory_app.command("rebuild")(memory_rebuild)
session_app.command("save")(session_save)
session_app.command("restore")(session_restore_cmd)
app.command("health")(health_cmd)
mcp_app.command("status")(mcp_status_cmd)
app.command()(serve)
service_app.command("run")(service_run)
service_app.command("install")(service_install)
service_app.command("start")(service_start)
service_app.command("restart")(service_restart)
service_app.command("stop")(service_stop)
service_app.command("status")(service_status_cmd)
service_app.command("uninstall")(service_uninstall)
app.command()(dashboard)
app.command()(mcp)
app.command("mcp-config")(mcp_config)
