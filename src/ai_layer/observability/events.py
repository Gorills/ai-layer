from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ai_layer.core.registry import get_registered_project
from ai_layer.observability.event_aggregation import aggregate_events as aggregate_events
from ai_layer.observability.event_common import event_dir as _event_dir
from ai_layer.observability.event_common import parse_ts, utcnow

EVENT_RETENTION_DAYS = 7
TAIL_READ_BYTES = 512 * 1024
_PRUNED_DIR_DAYS: set[tuple[str, str]] = set()
SAFE_METRIC_KEYS = {
    "arg_keys",
    "memory_hits",
    "skills",
    "skill_slugs",
    "memory_refreshed",
    "files",
    "hits",
    "limit",
    "skill_slug",
    "found",
    "completed_actions",
    "next_steps",
    "decisions",
    "verified_facts",
    "findings",
    "task",
    "status",
    "stage",
    "next_stage",
    "open_findings",
    "handoff_written",
    "reason",
    "candidate_files",
    "waited_for_lock",
    "knowledge_items",
    "hashes_calculated",
    "embeddings_reused",
    "embeddings_regenerated",
    "refresh_attempts",
    "template_version",
    "normalizations",
    "normalization_count",
    "effective_verdict",
}


def event_path(project_root: str | Path | None = None, *, day: str | None = None) -> Path:
    day = day or utcnow().date().isoformat()
    return _event_dir(project_root) / f"{day}.jsonl"


def _prune_old_files(directory: Path) -> None:
    today = utcnow().date().isoformat()
    key = (str(directory), today)
    if key in _PRUNED_DIR_DAYS:
        return
    _PRUNED_DIR_DAYS.add(key)
    cutoff = utcnow().date() - timedelta(days=EVENT_RETENTION_DAYS)
    try:
        files = list(directory.glob("*.jsonl"))
    except OSError:
        return
    for path in files:
        try:
            file_day = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_day < cutoff:
            try:
                path.unlink()
            except OSError:
                pass


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _prune_old_files(path.parent)
    raw = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)


def _safe_metrics(metrics: dict | None) -> dict | None:
    if not isinstance(metrics, dict):
        return None
    safe: dict = {}
    for raw_key, value in metrics.items():
        key = str(raw_key)
        if key not in SAFE_METRIC_KEYS:
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:120]
        elif isinstance(value, list):
            safe[key] = [str(item)[:80] for item in value[:12]]
    return safe or None


def emit_event(
    project_root: str | Path | None,
    *,
    category: str,
    operation: str,
    status: str,
    correlation_id: str | None = None,
    client: str | None = None,
    session_id: str | None = None,
    duration_ms: float | None = None,
    metrics: dict | None = None,
    error_type: str | None = None,
    source: str = "kernel",
) -> dict | None:
    """Append one privacy-minimal event without prompt/source/result payloads."""
    root: str | None = None
    if project_root is not None:
        root = str(Path(project_root).expanduser().resolve())
        try:
            if get_registered_project(root) is None:
                return None
        except RuntimeError:
            return None
    event: dict[str, object] = {
        "id": uuid4().hex,
        "correlation_id": correlation_id,
        "ts": utcnow().isoformat(),
        "project_root": root,
        "category": str(category),
        "operation": str(operation),
        "status": str(status),
        "source": str(source),
        "client": client or os.getenv("AI_LAYER_CLIENT") or "unknown",
        "session_id": session_id,
        "pid": os.getpid(),
    }
    if duration_ms is not None:
        event["duration_ms"] = round(float(duration_ms), 2)
    safe_metrics = _safe_metrics(metrics)
    if safe_metrics:
        event["metrics"] = safe_metrics
    if error_type:
        event["error_type"] = str(error_type)
    try:
        _append_jsonl(event_path(root), event)
    except (OSError, RuntimeError):
        return None
    return event


@contextmanager
def observed_operation(
    project_root: str | Path | None,
    *,
    category: str,
    operation: str,
    client: str | None = None,
    session_id: str | None = None,
    start_metrics: dict | None = None,
) -> Iterator[dict]:
    correlation_id = uuid4().hex
    started = time.perf_counter()
    state: dict = {"correlation_id": correlation_id, "metrics": dict(start_metrics or {})}
    emit_event(
        project_root,
        category=category,
        operation=operation,
        status="started",
        correlation_id=correlation_id,
        client=client,
        session_id=session_id,
        metrics=start_metrics,
    )
    try:
        yield state
    except Exception as exc:
        emit_event(
            project_root,
            category=category,
            operation=operation,
            status="failed",
            correlation_id=correlation_id,
            client=client,
            session_id=session_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            metrics=state.get("metrics") or None,
            error_type=type(exc).__name__,
        )
        raise
    else:
        emit_event(
            project_root,
            category=category,
            operation=operation,
            status="completed",
            correlation_id=correlation_id,
            client=client,
            session_id=session_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            metrics=state.get("metrics") or None,
        )


def _tail_lines(path: Path, max_bytes: int = TAIL_READ_BYTES) -> list[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
                handle.readline()
            raw = handle.read()
    except OSError:
        return []
    return raw.decode("utf-8", errors="replace").splitlines()


def read_events(
    project_root: str | Path | None = None,
    *,
    limit: int = 100,
    since_seconds: float | None = None,
) -> list[dict]:
    """Read newest bounded events from current/recent daily files."""
    try:
        directory = _event_dir(project_root)
    except RuntimeError:
        return []
    if not directory.exists():
        return []
    try:
        files = sorted(directory.glob("*.jsonl"), reverse=True)[: min(EVENT_RETENTION_DAYS + 1, 8)]
    except OSError:
        return []
    cutoff = (
        utcnow() - timedelta(seconds=max(0.0, since_seconds)) if since_seconds is not None else None
    )
    events: list[dict] = []
    for path in files:
        lines = _tail_lines(path)
        if not lines:
            continue
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(item, dict):
                continue
            if cutoff is not None:
                ts = parse_ts(item.get("ts"))
                if ts is None or ts < cutoff:
                    continue
            events.append(item)
            if len(events) >= max(1, limit):
                return list(reversed(events))
    return list(reversed(events))
