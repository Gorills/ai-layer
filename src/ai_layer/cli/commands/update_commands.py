from __future__ import annotations

from pathlib import Path

import typer

from ai_layer.cli.root import app, echo, echo_error
from ai_layer.installation.updater import install_update


def update(
    check: bool = typer.Option(False, "--check", help="Verify the signed channel and report availability without installing."),
    manifest_url: str | None = typer.Option(None, "--manifest-url", help="Override the configured signed channel manifest URL."),
    public_key: Path | None = typer.Option(None, "--public-key", help="Override the configured publisher public key."),
):
    """Securely install the newest release from the configured signed channel."""
    try:
        result = install_update(manifest_url=manifest_url, public_key=public_key, check_only=check)
    except Exception as exc:
        echo_error(exc)
        raise typer.Exit(1) from exc
    echo(result)


app.command()(update)
