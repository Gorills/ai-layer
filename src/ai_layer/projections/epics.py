from __future__ import annotations

import hashlib
from pathlib import Path

from ai_layer.application import epics as epic_uc
from ai_layer.core.registry import list_registered_projects


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


def project_epics_payload(project_key: str) -> dict | None:
    root = _root_for_key(project_key)
    if root is None:
        return None
    return {
        "project_key": project_key,
        "epics": epic_uc.list_for_project(root, include_archived=True),
    }


def epic_detail_payload(project_key: str, epic_key: str) -> dict | None:
    root = _root_for_key(project_key)
    if root is None:
        return None
    try:
        epic = epic_uc.get(root, key=epic_key, include_history=True)
    except ValueError:
        return None
    return {"project_key": project_key, "epic": epic}
