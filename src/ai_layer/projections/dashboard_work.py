from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ai_layer.db.epic_models import Epic
from ai_layer.db.models import Project, RuntimeEvent, Task
from ai_layer.db.session import session_scope
from ai_layer.db.work_models import WORK_STATUSES, AgentRun, RuntimeEventContext, WorkItem
from ai_layer.observability.work_events import safe_event_payload
from ai_layer.projections.dashboard_common import (
    entry_for_key,
    page_info,
    project_key,
    project_options,
    selected_entries,
)
from ai_layer.work.service import work_to_dict

WORK_FILTER_STATUSES = frozenset(WORK_STATUSES)
WORK_TIMELINE_LIMIT = 200


def _project_scope(
    db: Session, project_key_value: str | None
) -> tuple[list[Project], dict[UUID, dict]] | None:
    selected = selected_entries(project_key_value)
    if project_key_value and not selected:
        return None
    entries_by_root = {
        str(Path(str(entry["root"])).expanduser().resolve()): entry for entry in selected
    }
    if not entries_by_root:
        return [], {}
    projects = list(db.scalars(select(Project).where(Project.root_path.in_(entries_by_root))).all())
    metadata = {
        project.id: {
            "key": project_key(entries_by_root[project.root_path]),
            "name": entries_by_root[project.root_path].get("name") or Path(project.root_path).name,
            "root": project.root_path,
        }
        for project in projects
    }
    return projects, metadata


def _normalized_status(status: str | None) -> str:
    value = str(status or "").strip().casefold()
    if value and value not in WORK_FILTER_STATUSES:
        allowed = ", ".join(sorted(WORK_FILTER_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    return value


def _runs_by_work(db: Session, work_ids: list[UUID]) -> dict[UUID, list[AgentRun]]:
    grouped: dict[UUID, list[AgentRun]] = defaultdict(list)
    if not work_ids:
        return grouped
    rows = db.scalars(
        select(AgentRun)
        .where(AgentRun.work_id.in_(work_ids))
        .order_by(AgentRun.work_id, AgentRun.started_at, AgentRun.id)
    ).all()
    for row in rows:
        grouped[row.work_id].append(row)
    return grouped


def _link_keys(db: Session, rows: list[WorkItem]) -> tuple[dict[UUID, str], dict[UUID, str]]:
    task_ids = {row.linked_task_id for row in rows if row.linked_task_id}
    epic_ids = {row.linked_epic_id for row in rows if row.linked_epic_id}
    tasks = db.scalars(select(Task).where(Task.id.in_(task_ids))).all() if task_ids else []
    epics = db.scalars(select(Epic).where(Epic.id.in_(epic_ids))).all() if epic_ids else []
    return (
        {row.id: f"T-{int(row.sequence):04d}" for row in tasks},
        {row.id: f"E-{int(row.sequence):04d}" for row in epics},
    )


def _work_items(
    db: Session,
    rows: list[WorkItem],
    project_metadata: dict[UUID, dict],
) -> list[dict]:
    runs = _runs_by_work(db, [row.id for row in rows])
    task_keys, epic_keys = _link_keys(db, rows)
    result = []
    for row in rows:
        item = work_to_dict(db, row, preloaded_runs=runs.get(row.id, []))
        item["project"] = project_metadata.get(row.project_id, {})
        item["linked_task_key"] = (
            task_keys.get(row.linked_task_id) if row.linked_task_id is not None else None
        )
        item["linked_epic_key"] = (
            epic_keys.get(row.linked_epic_id) if row.linked_epic_id is not None else None
        )
        result.append(item)
    return result


def work_items_payload(
    *,
    project_key_value: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    wanted_status = _normalized_status(status)
    with session_scope() as db:
        scope = _project_scope(db, project_key_value)
        if scope is None:
            return None
        projects, project_metadata = scope
        project_ids = [project.id for project in projects]
        conditions: list[ColumnElement[bool]] = [WorkItem.project_id.in_(project_ids)]
        if wanted_status:
            conditions.append(WorkItem.status == wanted_status)
        total = (
            int(db.scalar(select(func.count()).select_from(WorkItem).where(*conditions)) or 0)
            if project_ids
            else 0
        )
        pagination = page_info(total, page, page_size)
        rows = (
            list(
                db.scalars(
                    select(WorkItem)
                    .where(*conditions)
                    .order_by(WorkItem.updated_at.desc(), WorkItem.id.desc())
                    .offset((pagination["page"] - 1) * pagination["page_size"])
                    .limit(pagination["page_size"])
                ).all()
            )
            if project_ids
            else []
        )
        items = _work_items(db, rows, project_metadata)
    return {
        "contract_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "items": items,
        "pagination": pagination,
        "projects": project_options(),
        "filters": {"project_key": project_key_value, "status": wanted_status or None},
        "ordering": ["updated_at:desc", "id:desc"],
    }


def work_detail_payload(project_key_value: str, work_key: str) -> dict | None:
    entry = entry_for_key(project_key_value)
    if entry is None:
        return None
    rendered = str(work_key or "").strip().upper()
    if not rendered.startswith("W-"):
        return None
    try:
        sequence = int(rendered[2:])
    except ValueError:
        return None

    root = str(Path(str(entry["root"])).expanduser().resolve())
    with session_scope() as db:
        project = db.scalar(select(Project).where(Project.root_path == root))
        if project is None:
            return None
        work = db.scalar(
            select(WorkItem).where(
                WorkItem.project_id == project.id,
                WorkItem.sequence == sequence,
            )
        )
        if work is None:
            return None
        item = _work_items(
            db,
            [work],
            {
                project.id: {
                    "key": project_key_value,
                    "name": entry.get("name") or Path(root).name,
                    "root": root,
                }
            },
        )[0]
        timeline_total = int(
            db.scalar(
                select(func.count())
                .select_from(RuntimeEventContext)
                .where(RuntimeEventContext.work_id == work.id)
            )
            or 0
        )
        event_rows = list(
            db.execute(
                select(RuntimeEvent, RuntimeEventContext)
                .join(RuntimeEventContext, RuntimeEventContext.event_id == RuntimeEvent.id)
                .where(RuntimeEventContext.work_id == work.id)
                .order_by(RuntimeEvent.created_at.desc(), RuntimeEvent.id.desc())
                .limit(WORK_TIMELINE_LIMIT)
            ).all()
        )
        timeline = [safe_event_payload(event, context) for event, context in reversed(event_rows)]
    return {
        "contract_version": 1,
        "project": item.pop("project"),
        "work": item,
        "timeline": timeline,
        "timeline_total": timeline_total,
        "timeline_truncated": timeline_total > len(timeline),
        "timeline_ordering": ["occurred_at:asc", "event_id:asc"],
    }
