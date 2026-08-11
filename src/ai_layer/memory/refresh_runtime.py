from __future__ import annotations

import queue
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ai_layer.db.models import Project
from ai_layer.db.session import session_scope
from ai_layer.memory.freshness import ensure_memory_fresh, probe_memory_freshness

_LOCK = threading.Lock()
_QUEUE: queue.Queue[str] = queue.Queue()
_JOBS: dict[str, dict[str, Any]] = {}
_IN_FLIGHT: set[str] = set()
_WORKER: threading.Thread | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _update(root: str, **values: Any) -> None:
    with _LOCK:
        state = dict(_JOBS.get(root) or {})
        state.update(values)
        _JOBS[root] = state


def _run(root: str) -> None:
    _update(root, status="running", started_at=_now(), error=None)
    try:
        with session_scope() as db:
            project = db.scalar(select(Project).where(Project.root_path == root))
            if project is None:
                raise RuntimeError(f"Project is not registered: {root}")
            result = ensure_memory_fresh(db, project)
        _update(root, status="completed", completed_at=_now(), result=result, error=None)
    except Exception as exc:
        _update(root, status="failed", completed_at=_now(), error=f"{type(exc).__name__}: {exc}"[:500])


def _worker_loop() -> None:
    while True:
        root = _QUEUE.get()
        try:
            _run(root)
        finally:
            with _LOCK:
                _IN_FLIGHT.discard(root)
            _QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER
    with _LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        # Daemon is intentional: a scan must never keep core-service shutdown/restart alive.
        _WORKER = threading.Thread(target=_worker_loop, name="ai-layer-refresh", daemon=True)
        _WORKER.start()


def schedule_refresh(project: Project) -> dict[str, Any]:
    root = str(Path(project.root_path).expanduser().resolve())
    _ensure_worker()
    with _LOCK:
        if root not in _IN_FLIGHT:
            _IN_FLIGHT.add(root)
            _JOBS[root] = {"status": "queued", "queued_at": _now(), "error": None}
            _QUEUE.put(root)
        return dict(_JOBS[root])


def refresh_status(project_root: str | Path) -> dict[str, Any]:
    root = str(Path(project_root).expanduser().resolve())
    with _LOCK:
        return dict(_JOBS.get(root) or {"status": "idle"})


def interactive_freshness(project: Project) -> dict[str, Any]:
    """Never perform a full scanner rebuild in an interactive MCP request.

    The cheap probe decides whether the durable snapshot can be used. Stale/unknown state is queued
    for the persistent runtime; callers may continue with the last stable snapshot and current source
    remains authoritative for changed paths.
    """
    probe = probe_memory_freshness(project)
    if probe.get("status") == "fresh":
        return probe
    job = schedule_refresh(project)
    result = dict(probe)
    result.update(
        {
            "status": "refreshing" if probe.get("snapshot_available") else "initializing",
            "refreshed": False,
            "background_refresh": True,
            "refresh_job": job.get("status"),
            "read_contract": (
                "Using the last stable memory snapshot while refresh runs. Current repository source is authoritative "
                "for changed paths; do not treat stale memory as proof of current code."
                if probe.get("snapshot_available")
                else "No stable memory snapshot exists yet. Run/await the initial scan before relying on semantic memory."
            ),
        }
    )
    return result
