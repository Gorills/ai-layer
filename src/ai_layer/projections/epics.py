from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select

from ai_layer.application import epics as epic_uc
from ai_layer.core.registry import list_registered_projects
from ai_layer.core.service import get_project
from ai_layer.db.epic_models import Epic
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import epic_key


def _project_key(entry: dict) -> str:
    project_id = str(entry.get("project_id") or "").strip()
    if project_id:
        return project_id
    root = str(entry.get("root") or "")
    return "root-" + hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def _root_for_key(key: str) -> Path | None:
    for entry in list_registered_projects(existing_only=True):
        if _project_key(entry) == key:
            return Path(str(entry["root"])).expanduser().resolve()
    return None


def _epic_summary(row: Epic) -> dict:
    return {
        "id": str(row.id),
        "key": epic_key(row.sequence),
        "project_id": str(row.project_id),
        "title": row.title,
        "status": row.status,
        "current_spec_version": row.current_spec_version,
        "approved_spec_version": row.approved_spec_version,
        "execution_spec_version": row.execution_spec_version,
        "plan_version": row.plan_version,
        "blocked_reason": row.blocked_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }


def _list_epic_summaries(root: Path) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, root)
        rows = db.scalars(
            select(Epic).where(Epic.project_id == project.id).order_by(Epic.sequence.desc())
        ).all()
        return [_epic_summary(row) for row in rows]


def project_epics_payload(project_key: str) -> dict | None:
    root = _root_for_key(project_key)
    if root is None:
        return None
    return {"project_key": project_key, "epics": _list_epic_summaries(root)}


def epic_detail_payload(project_key: str, epic_key: str) -> dict | None:
    root = _root_for_key(project_key)
    if root is None:
        return None
    try:
        epic = epic_uc.get(root, key=epic_key, include_history=True)
    except ValueError:
        return None
    return {"project_key": project_key, "epic": epic}
