"""CLI composition root. Commands register themselves on focused Typer sub-apps."""
from ai_layer.cli.root import app, echo_error
from ai_layer.cli.commands import maintenance as _maintenance  # noqa: F401
from ai_layer.cli.commands import operations as _operations  # noqa: F401
from ai_layer.cli.commands import context_commands as _context_commands  # noqa: F401
from ai_layer.cli.commands import service_commands as _service_commands  # noqa: F401
from ai_layer.cli.commands import skills_commands as _skills_commands  # noqa: F401
from ai_layer.cli.commands import update_commands as _update_commands  # noqa: F401

def main() -> None:
    try:
        app()
    except Exception as exc:
        echo_error(exc)
        raise SystemExit(1) from exc


__all__ = ["app", "main"]
