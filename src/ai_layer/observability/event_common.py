from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.paths import project_state_path
from ai_layer.core.registry import get_registered_project

EVENTS_RELATIVE_DIR = Path("observability") / "events"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def event_dir(project_root: str | Path | None = None) -> Path:
    if project_root is None:
        return get_settings().home / EVENTS_RELATIVE_DIR
    registered = get_registered_project(project_root)
    if not registered:
        raise RuntimeError(f"Project is not registered: {project_root}")
    return project_state_path(registered["root"]) / EVENTS_RELATIVE_DIR
