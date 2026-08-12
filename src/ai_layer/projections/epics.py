from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from ai_layer.application import epics as epic_uc
from ai_layer.core.registry import list_registered_projects
from ai_layer.core.service import get_project
from ai_layer.db.epic_models import Epic, EpicPlanItem
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import EPIC_OPEN_STATUSES, epic_key
from ai_layer.projections.dashboard_common import page_info


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


def _epic_summary(row: Epic, progress: dict | None = None) -> dict:
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
        "progress": progress or {"total": 0, "completed": 0, "active": 0},
        "blocked_reason": row.blocked_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }


def _summaries_with_progress(db, rows: list[Epic]) -> list[dict]:
    if not rows:
        return []
    ids = [row.id for row in rows]
    plan_rows = db.scalars(select(EpicPlanItem).where(EpicPlanItem.epic_id.in_(ids))).all()
    progress_by_epic: dict[str, dict[str, int]] = {
        str(row.id): {"total": 0, "completed": 0, "active": 0} for row in rows
    }
    for item in plan_rows:
        progress = progress_by_epic.setdefault(
            str(item.epic_id), {"total": 0, "completed": 0, "active": 0}
        )
        progress["total"] += 1
        if item.status == "completed":
            progress["completed"] += 1
        elif item.status == "active":
            progress["active"] += 1
    return [_epic_summary(row, progress_by_epic.get(str(row.id))) for row in rows]


def _list_epic_summaries(root: Path) -> list[dict]:
    with session_scope() as db:
        project = get_project(db, root)
        rows = db.scalars(
            select(Epic).where(Epic.project_id == project.id).order_by(Epic.sequence.desc())
        ).all()
        return _summaries_with_progress(db, list(rows))


def _registered_project_map(db, project_key_value: str | None = None) -> tuple[dict, list[dict]]:
    project_map: dict[str, dict] = {}
    projects: list[dict] = []
    for entry in list_registered_projects(existing_only=True):
        key = _project_key(entry)
        if project_key_value and key != project_key_value:
            continue
        root = Path(str(entry["root"])).expanduser().resolve()
        project = get_project(db, root, required=False)
        if project is None:
            continue
        project_id = str(project.id)
        metadata = {
            "key": key,
            "name": str(entry.get("name") or root.name),
        }
        project_map[project_id] = metadata
        projects.append(metadata)
    projects.sort(key=lambda item: item["name"].casefold())
    return project_map, projects


def epics_payload(
    *,
    project_key_value: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    with session_scope() as db:
        project_map, projects = _registered_project_map(db, project_key_value)
        if project_key_value and not project_map:
            return None
        rows = list(
            db.scalars(select(Epic).order_by(Epic.updated_at.desc(), Epic.sequence.desc())).all()
        )
        rows = [row for row in rows if str(row.project_id) in project_map]
        normalized_status = str(status or "").strip().casefold()
        if normalized_status == "open":
            rows = [row for row in rows if row.status in EPIC_OPEN_STATUSES]
        elif normalized_status:
            rows = [row for row in rows if row.status.casefold() == normalized_status]

        pagination = page_info(len(rows), page=page, page_size=page_size)
        start = (pagination["page"] - 1) * pagination["page_size"]
        visible_rows = rows[start : start + pagination["page_size"]]
        items = _summaries_with_progress(db, visible_rows)
        for item in items:
            item["project"] = project_map.get(item["project_id"], {})
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "items": items,
            "projects": projects,
            "filters": {"project_key": project_key_value, "status": status},
            "pagination": pagination,
        }


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
