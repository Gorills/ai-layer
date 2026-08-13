from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from ai_layer.core.service import get_project
from ai_layer.db.models import RuntimeEvent
from ai_layer.db.session import session_scope
from ai_layer.db.work_models import RuntimeEventContext
from ai_layer.observability.work_events import safe_event_payload
from ai_layer.projections.dashboard_common import (
    page_info,
    project_key,
    project_options,
    selected_entries,
)


def activity_payload(
    *,
    project_key_value: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    entries = selected_entries(project_key_value)
    if project_key_value and not entries:
        return None
    normalized_size = max(1, min(int(page_size or 10), 50))
    requested_page = max(1, int(page or 1))
    offset = (requested_page - 1) * normalized_size

    with session_scope() as db:
        projects = []
        names: dict[str, tuple[str, str]] = {}
        for entry in entries:
            root = Path(str(entry["root"])).expanduser().resolve()
            project = get_project(db, root)
            projects.append(project)
            names[str(project.id)] = (project_key(entry), str(entry.get("name") or root.name))
        project_ids = [item.id for item in projects]
        if not project_ids:
            total = 0
            rows = []
        else:
            total = int(
                db.scalar(
                    select(func.count(RuntimeEvent.id)).where(
                        RuntimeEvent.project_id.in_(project_ids)
                    )
                )
                or 0
            )
            rows = db.execute(
                select(RuntimeEvent, RuntimeEventContext)
                .outerjoin(
                    RuntimeEventContext,
                    RuntimeEventContext.event_id == RuntimeEvent.id,
                )
                .where(RuntimeEvent.project_id.in_(project_ids))
                .order_by(RuntimeEvent.created_at.desc(), RuntimeEvent.id.desc())
                .offset(offset)
                .limit(normalized_size)
            ).all()

    items = []
    for event, context in rows:
        safe = safe_event_payload(event, context)
        key, name = names.get(str(event.project_id), ("", "unknown"))
        details = safe.get("payload") or {}
        items.append(
            {
                **safe,
                "ts": safe.get("occurred_at"),
                "project_key": key,
                "project_name": name,
                "client": safe.get("client") or "unknown",
                "category": "runtime_event",
                "operation": details.get("tool") or safe.get("event_type") or "unknown",
                "status": details.get("status") or "observed",
                "duration_ms": details.get("duration_ms"),
                "error_type": details.get("error_type"),
            }
        )
    return {
        "items": items,
        "pagination": page_info(total, requested_page, normalized_size),
        "projects": project_options(),
        "project_key": project_key_value,
        "retention": "durable RuntimeEvent journal; JSONL telemetry is diagnostic only",
    }
