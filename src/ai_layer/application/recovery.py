from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from ai_layer.application.tasks import reap_stale_workers

_REAPER_INTERVAL_SECONDS = 60.0
_STATUS_LOCK = threading.Lock()
_STATUS: dict = {
    "status": "not_started",
    "last_run_at": None,
    "last_error": None,
    "last_result": None,
}


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def recovery_status() -> dict:
    with _STATUS_LOCK:
        return dict(_STATUS)


def reconcile_stale_workers() -> dict:
    try:
        result = reap_stale_workers()
    except Exception as exc:
        error_payload: dict[str, object] = {
            "status": "degraded",
            "last_run_at": _utc_iso(),
            "last_error": f"{type(exc).__name__}: {exc}"[:1000],
            "last_result": None,
        }
        with _STATUS_LOCK:
            _STATUS.update(error_payload)
        return {"ok": False, "error": error_payload["last_error"]}
    healthy_payload: dict[str, object] = {
        "status": "healthy",
        "last_run_at": _utc_iso(),
        "last_error": None,
        "last_result": result,
    }
    with _STATUS_LOCK:
        _STATUS.update(healthy_payload)
    return result


async def _run_reaper(stop: asyncio.Event, interval_seconds: float) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            await asyncio.to_thread(reconcile_stale_workers)


@asynccontextmanager
async def worker_recovery_lifespan(
    *,
    interval_seconds: float = _REAPER_INTERVAL_SECONDS,
) -> AsyncIterator[None]:
    await asyncio.to_thread(reconcile_stale_workers)
    stop = asyncio.Event()
    task = asyncio.create_task(
        _run_reaper(stop, interval_seconds), name="ai-layer-worker-lease-reaper"
    )
    try:
        yield
    finally:
        stop.set()
        await task
