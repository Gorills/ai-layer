from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.sessions.service import list_sessions, restore_session, save_session, session_to_dict


def list_project_sessions(project_root: str | Path, limit: int = 10) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, project_root)
        return [session_to_dict(item) for item in list_sessions(db, project, limit=limit)]


def restore_project_session(project_root: str | Path, session_id: str) -> dict | None:
    with session_scope() as db:
        project = get_project(db, project_root)
        item = restore_session(db, project, session_id)
        return session_to_dict(item) if item else None


def save_project_session(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        return session_to_dict(save_session(db, project, **kwargs))
