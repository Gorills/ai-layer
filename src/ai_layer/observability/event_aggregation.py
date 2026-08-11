from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ai_layer.observability.event_common import event_dir as _event_dir
from ai_layer.observability.event_common import parse_ts, utcnow


@dataclass
class _AggregateState:
    """Process-local incremental projection of terminal events for one exact time window."""

    files: dict[str, tuple[int, int, int]] = field(default_factory=dict)  # inode, offset, mtime_ns
    events: deque[dict] = field(default_factory=deque)
    operations: Counter[str] = field(default_factory=Counter)
    clients: Counter[str] = field(default_factory=Counter)
    terminal: int = 0
    failed: int = 0
    duration_total: float = 0.0
    duration_count: int = 0
    ordered: bool = True


_AGGREGATE_CACHE: dict[tuple[str, int], _AggregateState] = {}


def _aggregate_empty() -> dict:
    return {
        "terminal": 0,
        "failed": 0,
        "avg_duration_ms": None,
        "operations": {},
        "clients": {},
        "last_event_at": None,
        "recent_terminal": [],
    }


def _aggregate_add(state: _AggregateState, item: dict, *, cutoff_epoch: float) -> None:
    if item.get("status") not in {"completed", "failed"}:
        return
    ts = parse_ts(item.get("ts"))
    if ts is None:
        return
    epoch = ts.timestamp()
    if epoch < cutoff_epoch:
        return
    duration = item.get("duration_ms")
    compact = {
        key: item[key]
        for key in (
            "id",
            "correlation_id",
            "ts",
            "project_root",
            "category",
            "operation",
            "status",
            "source",
            "client",
            "session_id",
            "pid",
            "duration_ms",
            "metrics",
            "error_type",
        )
        if key in item
    }
    compact["_ts_epoch"] = epoch
    if state.events and epoch < float(state.events[-1].get("_ts_epoch") or 0.0):
        state.ordered = False
    state.events.append(compact)
    state.terminal += 1
    if item.get("status") == "failed":
        state.failed += 1
    operation = str(item.get("operation") or "unknown")
    client = str(item.get("client") or "unknown")
    state.operations[operation] += 1
    state.clients[client] += 1
    if isinstance(duration, (int, float)):
        state.duration_total += float(duration)
        state.duration_count += 1


def _aggregate_remove(state: _AggregateState, item: dict) -> None:
    state.terminal = max(0, state.terminal - 1)
    if item.get("status") == "failed":
        state.failed = max(0, state.failed - 1)
    operation = str(item.get("operation") or "unknown")
    client = str(item.get("client") or "unknown")
    state.operations[operation] -= 1
    state.clients[client] -= 1
    if state.operations[operation] <= 0:
        del state.operations[operation]
    if state.clients[client] <= 0:
        del state.clients[client]
    duration = item.get("duration_ms")
    if isinstance(duration, (int, float)):
        state.duration_total -= float(duration)
        state.duration_count = max(0, state.duration_count - 1)


def _aggregate_prune(state: _AggregateState, cutoff_epoch: float) -> None:
    # Events normally arrive in wall-clock order. If the system clock moved backwards, normalize
    # once before pruning instead of silently retaining an expired event behind a newer one.
    if not state.ordered:
        items = sorted(state.events, key=lambda item: float(item.get("_ts_epoch") or 0.0))
        state.events = deque(items)
        state.ordered = True
    while state.events and float(state.events[0].get("_ts_epoch") or 0.0) < cutoff_epoch:
        _aggregate_remove(state, state.events.popleft())


def _read_appended_events(
    path: Path,
    *,
    offset: int,
    state: _AggregateState,
    cutoff_epoch: float,
) -> int:
    """Consume only complete JSONL records and return the safe next byte offset."""
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.read()
    except OSError:
        return offset
    if not raw:
        return offset
    last_newline = raw.rfind(b"\n")
    if last_newline < 0:
        return offset
    complete = raw[: last_newline + 1]
    for line in complete.splitlines():
        try:
            item = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            _aggregate_add(state, item, cutoff_epoch=cutoff_epoch)
    return offset + last_newline + 1


def _rebuild_aggregate_state(
    files: list[Path],
    *,
    cutoff_epoch: float,
) -> _AggregateState:
    state = _AggregateState()
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        offset = _read_appended_events(path, offset=0, state=state, cutoff_epoch=cutoff_epoch)
        try:
            after = path.stat()
        except OSError:
            continue
        state.files[str(path)] = (int(after.st_ino), offset, int(after.st_mtime_ns))
    _aggregate_prune(state, cutoff_epoch)
    return state


def _advance_aggregate_state(
    state: _AggregateState,
    files: list[Path],
    *,
    cutoff_epoch: float,
) -> _AggregateState:
    current_paths = {str(path) for path in files}
    if any(path not in current_paths for path in state.files):
        return _rebuild_aggregate_state(files, cutoff_epoch=cutoff_epoch)

    for path in files:
        key = str(path)
        try:
            stat = path.stat()
        except OSError:
            return _rebuild_aggregate_state(files, cutoff_epoch=cutoff_epoch)
        previous = state.files.get(key)
        if previous is None:
            offset = _read_appended_events(path, offset=0, state=state, cutoff_epoch=cutoff_epoch)
        else:
            inode, offset, previous_mtime = previous
            if int(stat.st_ino) != inode or int(stat.st_size) < offset:
                return _rebuild_aggregate_state(files, cutoff_epoch=cutoff_epoch)
            if int(stat.st_size) == offset and int(stat.st_mtime_ns) != previous_mtime:
                # Same-size rewrite is not an append-only event stream; rebuild rather than trust it.
                return _rebuild_aggregate_state(files, cutoff_epoch=cutoff_epoch)
            offset = _read_appended_events(
                path, offset=offset, state=state, cutoff_epoch=cutoff_epoch
            )
        try:
            after = path.stat()
        except OSError:
            return _rebuild_aggregate_state(files, cutoff_epoch=cutoff_epoch)
        state.files[key] = (int(after.st_ino), offset, int(after.st_mtime_ns))
    _aggregate_prune(state, cutoff_epoch)
    return state


def aggregate_events(
    project_root: str | Path | None = None,
    *,
    since_seconds: float,
    recent_limit: int = 80,
) -> dict:
    """Aggregate an exact retained time window using an incremental append-only projection.

    The first call streams the relevant daily JSONL files. Later dashboard polls only consume bytes
    appended since the previous call and prune terminal events that left the requested window, so
    exact 5-minute/24-hour totals do not require rescanning a day's history every two seconds.
    """
    try:
        directory = _event_dir(project_root)
    except RuntimeError:
        return _aggregate_empty()
    window_seconds = max(0, int(round(float(since_seconds))))
    now = utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    cutoff_epoch = cutoff.timestamp()
    if not directory.exists():
        files: list[Path] = []
    else:
        try:
            files = []
            for path in sorted(directory.glob("*.jsonl")):
                try:
                    file_day = datetime.strptime(path.stem, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if file_day >= cutoff.date() - timedelta(days=1):
                    files.append(path)
        except OSError:
            files = []

    cache_key = (str(directory), window_seconds)
    state = _AGGREGATE_CACHE.get(cache_key)
    if state is None:
        state = _rebuild_aggregate_state(files, cutoff_epoch=cutoff_epoch)
    else:
        state = _advance_aggregate_state(state, files, cutoff_epoch=cutoff_epoch)
    _AGGREGATE_CACHE[cache_key] = state

    wanted_recent = max(1, int(recent_limit))
    recent: list[dict] = []
    for item in list(state.events)[-wanted_recent:]:
        recent.append({key: value for key, value in item.items() if key != "_ts_epoch"})
    last_event_at = recent[-1].get("ts") if recent else None
    return {
        "terminal": state.terminal,
        "failed": state.failed,
        "avg_duration_ms": (
            round(state.duration_total / state.duration_count, 1) if state.duration_count else None
        ),
        "operations": dict(state.operations.most_common()),
        "clients": dict(state.clients.most_common()),
        "last_event_at": last_event_at,
        "recent_terminal": recent,
    }
