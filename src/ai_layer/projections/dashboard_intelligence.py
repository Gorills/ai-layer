from __future__ import annotations

from pathlib import Path

from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import EPIC_EXECUTION_STATUSES
from ai_layer.memory.freshness import probe_memory_freshness
from ai_layer.memory.navigation import project_map_status
from ai_layer.memory.project_map_semantics import semantic_map_status


def project_intelligence_summary(
    root: str | Path,
    *,
    task_state: dict | None = None,
    epics: list[dict] | None = None,
) -> dict:
    """Compact Dashboard read model for Project Map freshness and continuation focus."""
    project_root = Path(root).expanduser().resolve()
    current_task = dict((task_state or {}).get("current") or {})
    active_epic = next(
        (
            dict(item)
            for item in list(epics or [])
            if str(item.get("status") or "") in EPIC_EXECUTION_STATUSES
        ),
        None,
    )

    try:
        with session_scope() as db:
            project = get_project(db, project_root)
            map_state = project_map_status(db, project)
            map_state.update(semantic_map_status(db, project))
            freshness = probe_memory_freshness(project)
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "current_focus": (
                {"kind": "task", "key": current_task.get("key")}
                if current_task
                else ({"kind": "epic", "key": active_epic.get("key")} if active_epic else None)
            ),
        }

    if current_task:
        focus = {
            "kind": "task",
            "key": current_task.get("key"),
            "title": current_task.get("goal"),
            "status": current_task.get("status"),
        }
    elif active_epic:
        focus = {
            "kind": "epic",
            "key": active_epic.get("key"),
            "title": active_epic.get("title"),
            "status": active_epic.get("status"),
        }
    else:
        focus = None

    return {
        "available": True,
        "current_focus": focus,
        "project_map": map_state,
        "freshness": {
            "status": freshness.get("status"),
            "snapshot_available": freshness.get("snapshot_available"),
            "changed_paths": list(freshness.get("changed_paths") or [])[:10],
            "read_contract": freshness.get("read_contract"),
        },
        "execution_owner": "host-native",
        "source_of_truth": "current repository source",
    }
