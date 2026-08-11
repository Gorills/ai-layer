from __future__ import annotations

import hashlib
import math
from pathlib import Path

from ai_layer.core.registry import list_registered_projects


def project_key(entry: dict) -> str:
    project_id = str(entry.get("project_id") or "").strip()
    if project_id:
        return project_id
    root = str(entry.get("root") or "")
    return "root-" + hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def entries() -> list[dict]:
    return [dict(item) for item in list_registered_projects(existing_only=True)]


def entry_for_key(key: str) -> dict | None:
    return next((entry for entry in entries() if project_key(entry) == key), None)


def project_options() -> list[dict]:
    return [
        {
            "key": project_key(entry),
            "name": entry.get("name") or Path(str(entry.get("root") or "")).name,
            "root": str(entry.get("root") or ""),
            "mode": entry.get("mode") or "standard",
            "provenance": entry.get("provenance") or "allow",
        }
        for entry in entries()
    ]


def selected_entries(project_key_value: str | None) -> list[dict]:
    if not project_key_value:
        return entries()
    entry = entry_for_key(project_key_value)
    return [entry] if entry is not None else []


def page_info(total: int, page: int, page_size: int) -> dict:
    size = max(1, min(int(page_size or 10), 50))
    pages = math.ceil(total / size) if total else 0
    current = max(1, int(page or 1))
    if pages:
        current = min(current, pages)
    return {
        "page": current,
        "page_size": size,
        "total": int(total),
        "pages": pages,
        "has_previous": current > 1,
        "has_next": pages > 0 and current < pages,
    }
