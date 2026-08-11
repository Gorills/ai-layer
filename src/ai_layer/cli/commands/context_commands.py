from __future__ import annotations

import shutil
from pathlib import Path

import typer

from ai_layer.application import knowledge as knowledge_uc
from ai_layer.cli.root import app, echo, memory_app
from ai_layer.core.paths import normalize_root
from ai_layer.observability.context_common import report_path
from ai_layer.observability.context_report import build_report, write_latest_report


def context_report(
    path: str = typer.Option(".", "--path", help="Registered project path."),
    output: str | None = typer.Option(
        None, "--output", help="Optional copy destination for the portable JSON report."
    ),
    limit: int = typer.Option(
        500, "--limit", min=10, max=2000, help="Maximum recent trace events included."
    ),
):
    """Build/export the automatic AI Layer context and skill telemetry report."""
    root = normalize_root(path)
    internal = write_latest_report(root, limit=limit)
    destination = internal
    if output:
        destination = Path(output).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination != internal:
            shutil.copyfile(internal, destination)
    report = build_report(root, limit=limit)
    echo(
        {
            "ok": True,
            "project_root": str(root),
            "report": str(destination),
            "internal_report": str(report_path(root)),
            "events": report["summary"]["events"],
            "sessions": report["summary"]["sessions"],
            "dynamic_tool_result_estimated_tokens_total": report["summary"][
                "dynamic_tool_result_estimated_tokens_total"
            ],
            "findings": len(report.get("findings") or []),
            "note": "Token counts are estimates; the host/model tokenizer and hidden Cursor context are not observable through MCP.",
        }
    )


app.command("context-report")(context_report)


def knowledge_status_cmd(path: str = typer.Option(".", "--path", help="Registered project path.")):
    """Show reviewed Project Knowledge baseline/lifecycle counts."""
    root = normalize_root(path)
    echo({"ok": True, "project_root": str(root), **knowledge_uc.status(root)})


def knowledge_list_cmd(
    path: str = typer.Option(".", "--path", help="Registered project path."),
    status: str = typer.Option("VERIFIED", "--status", help="VERIFIED|DRAFT|STALE|SUPERSEDED"),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
):
    """List curated Project Knowledge cards; never returns raw source chunks."""
    root = normalize_root(path)
    echo(
        {
            "project_root": str(root),
            "items": knowledge_uc.list_cards(root, status=status.upper(), limit=limit),
        }
    )


memory_app.command("status")(knowledge_status_cmd)
memory_app.command("knowledge")(knowledge_list_cmd)
