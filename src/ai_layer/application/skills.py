from __future__ import annotations

from pathlib import Path

from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope


def ensure_registered_project(project_root: str | Path) -> None:
    """Validate project registration without making skill relevance decisions."""
    with session_scope() as db:
        get_project(db, project_root)
