from __future__ import annotations

import typer

from ai_layer.core.jsonutil import dumps
from ai_layer.domain.errors import normalize_error

app = typer.Typer(help="Local AI Development Layer")
memory_app = typer.Typer(help="Project memory commands")
session_app = typer.Typer(help="Cross-chat session memory")
projects_app = typer.Typer(help="Machine project registry")
audit_app = typer.Typer(help="Privacy-minimal MCP call audit")
service_app = typer.Typer(help="Always-on local dashboard/control service")
mcp_app = typer.Typer(help="MCP runtime/transport status")
task_app = typer.Typer(help="Transport-independent durable task recovery/control")
skill_app = typer.Typer(help="Install/manage global and project-scoped expert skills")
agent_app = typer.Typer(help="Cost-aware delegated-agent routing policy")
app.add_typer(memory_app, name="memory")
app.add_typer(session_app, name="session")
app.add_typer(projects_app, name="projects")
app.add_typer(audit_app, name="audit")
app.add_typer(service_app, name="service")
app.add_typer(mcp_app, name="mcp")
app.add_typer(task_app, name="task")
app.add_typer(skill_app, name="skill")
app.add_typer(agent_app, name="agent")

def echo(data) -> None:
    typer.echo(dumps(data) if not isinstance(data, str) else data)


def error_payload(exc: BaseException) -> dict:
    return {"ok": False, "error": normalize_error(exc).to_dict()}


def echo_error(exc: BaseException) -> None:
    echo(error_payload(exc))
