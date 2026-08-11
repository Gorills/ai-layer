from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from ai_layer.core.service import get_project
from ai_layer.db.models import Task, VerificationRun
from ai_layer.db.session import session_scope
from ai_layer.projections.dashboard_common import (
    entry_for_key,
    page_info,
    project_key,
    project_options,
    selected_entries,
)
from ai_layer.tasks.views import task_to_dict

_TASK_STATUSES = {"active", "blocked", "completed", "cancelled"}


def tasks_payload(
    *,
    project_key_value: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    selected = selected_entries(project_key_value)
    if project_key_value and not selected:
        return None
    wanted_status = str(status or "").strip().casefold()
    if wanted_status and wanted_status not in _TASK_STATUSES:
        wanted_status = ""

    with session_scope() as db:
        project_map: dict[object, dict] = {}
        project_ids = []
        for entry in selected:
            project = get_project(db, Path(str(entry["root"])))
            if project is None:
                continue
            project_ids.append(project.id)
            project_map[project.id] = {
                "key": project_key(entry),
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            }
        if not project_ids:
            return {
                "items": [],
                "pagination": page_info(0, page, page_size),
                "projects": project_options(),
                "filters": {"project_key": project_key_value, "status": wanted_status or None},
            }

        conditions = [Task.project_id.in_(project_ids)]
        if wanted_status:
            conditions.append(Task.status == wanted_status)
        total = int(db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0)
        pagination = page_info(total, page, page_size)
        rows = list(
            db.scalars(
                select(Task)
                .where(*conditions)
                .order_by(Task.updated_at.desc(), Task.created_at.desc())
                .offset((pagination["page"] - 1) * pagination["page_size"])
                .limit(pagination["page_size"])
            ).all()
        )
        return {
            "items": [
                {
                    **task_to_dict(db, task, include_history=False),
                    "project": project_map.get(task.project_id, {}),
                }
                for task in rows
            ],
            "pagination": pagination,
            "projects": project_options(),
            "filters": {"project_key": project_key_value, "status": wanted_status or None},
        }


def task_detail_payload(project_key_value: str, task_key: str) -> dict | None:
    entry = entry_for_key(project_key_value)
    if entry is None:
        return None
    raw = str(task_key or "").strip().upper()
    if not raw.startswith("T-"):
        return None
    try:
        sequence = int(raw[2:])
    except ValueError:
        return None

    with session_scope() as db:
        project = get_project(db, Path(str(entry["root"])))
        if project is None:
            return None
        task = db.scalar(
            select(Task).where(Task.project_id == project.id, Task.sequence == sequence).limit(1)
        )
        if task is None:
            return None
        rows = list(
            db.scalars(
                select(VerificationRun)
                .where(VerificationRun.task_id == task.id)
                .order_by(VerificationRun.created_at.desc())
                .limit(50)
            ).all()
        )
        return {
            "project": {
                "key": project_key_value,
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            },
            "task": task_to_dict(db, task, include_history=True),
            "verification": [
                {
                    "id": str(row.id),
                    "stage_id": str(row.stage_id) if row.stage_id else None,
                    "assurance": row.assurance,
                    "command": list(row.command or []),
                    "started_at": row.started_at.isoformat(),
                    "completed_at": row.completed_at.isoformat(),
                    "exit_code": row.exit_code,
                    "timed_out": bool(row.timed_out),
                    "output_summary": row.output_summary,
                    "evidence_ref": row.evidence_ref,
                }
                for row in rows
            ],
        }
