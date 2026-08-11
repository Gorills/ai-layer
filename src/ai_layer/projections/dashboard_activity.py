from __future__ import annotations

from pathlib import Path

from ai_layer.observability.events import aggregate_events
from ai_layer.projections.dashboard_common import (
    page_info,
    project_key,
    project_options,
    selected_entries,
)


def activity_payload(
    *, project_key_value: str | None = None, page: int = 1, page_size: int = 10
) -> dict | None:
    entries = selected_entries(project_key_value)
    if project_key_value and not entries:
        return None
    items = []
    for entry in entries:
        root = Path(str(entry["root"])).expanduser().resolve()
        metrics = aggregate_events(root, since_seconds=7 * 24 * 3600, recent_limit=250)
        for event in metrics.get("recent_terminal") or []:
            items.append(
                {
                    "ts": event.get("ts"),
                    "project_key": project_key(entry),
                    "project_name": entry.get("name") or root.name,
                    "client": event.get("client") or "unknown",
                    "category": event.get("category") or "unknown",
                    "operation": event.get("operation") or "unknown",
                    "status": event.get("status") or "unknown",
                    "duration_ms": event.get("duration_ms"),
                    "error_type": event.get("error_type"),
                }
            )
    items.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    pagination = page_info(len(items), page, page_size)
    start = (pagination["page"] - 1) * pagination["page_size"]
    end = start + pagination["page_size"]
    return {
        "items": items[start:end],
        "pagination": pagination,
        "projects": project_options(),
        "project_key": project_key_value,
        "retention": "7-day dashboard window; underlying event retention is configured separately",
    }
