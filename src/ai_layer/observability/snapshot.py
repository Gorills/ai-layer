from __future__ import annotations

import json
import time
from pathlib import Path

from ai_layer.core.paths import project_state_path
from ai_layer.core.registry import get_registered_project, list_registered_projects
from ai_layer.observability.events import EVENT_RETENTION_DAYS, aggregate_events, parse_ts, read_events, utcnow
from ai_layer.sessions.service import SNAPSHOT_SCHEMA

_DB_STATUS_CACHE: tuple[float, dict] | None = None


def resolve_registered_root(path: str | Path) -> Path | None:
    candidate = Path(path).expanduser().resolve()
    matches: list[Path] = []
    for item in list_registered_projects(existing_only=True):
        raw = str(item.get("root") or "").strip()
        if not raw:
            continue
        root = Path(raw).expanduser().resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        matches.append(root)
    return max(matches, key=lambda item: len(item.parts)) if matches else None


def _active_operations(events: list[dict]) -> list[dict]:
    started: dict[str, dict] = {}
    terminal: set[str] = set()
    for event in events:
        correlation = str(event.get("correlation_id") or "")
        if not correlation:
            continue
        if event.get("status") == "started":
            started[correlation] = event
        elif event.get("status") in {"completed", "failed"}:
            terminal.add(correlation)
    return [event for key, event in started.items() if key not in terminal]


def _latest_session_snapshot(root: Path) -> dict | None:
    try:
        path = project_state_path(root, "sessions", "latest.json")
        if path.is_symlink() or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("snapshot_schema") != SNAPSHOT_SCHEMA or data.get("commit_state") != "committed":
        return None
    return {
        "goal": str(data.get("goal") or "")[:240],
        "current_state": str(data.get("current_state") or "")[:240],
        "created_at": data.get("created_at"),
    }


def _open_task_flows(events: list[dict]) -> list[dict]:
    sessions: dict[str, list[dict]] = {}
    for event in events:
        session_id = str(event.get("session_id") or "").strip()
        if session_id and event.get("status") in {"completed", "failed"}:
            sessions.setdefault(session_id, []).append(event)
    result: list[dict] = []
    for session_id, items in sessions.items():
        latest_context = None
        latest_save = None
        for item in items:
            if item.get("operation") == "memory_context" and item.get("status") == "completed":
                latest_context = item
            elif item.get("operation") == "session_save" and item.get("status") == "completed":
                latest_save = item
        context_ts = parse_ts((latest_context or {}).get("ts"))
        save_ts = parse_ts((latest_save or {}).get("ts"))
        if latest_context is None or (save_ts is not None and context_ts is not None and save_ts >= context_ts):
            continue
        after_context = []
        for item in items:
            ts = parse_ts(item.get("ts"))
            if context_ts is not None and ts is not None and ts >= context_ts:
                after_context.append(item)
        result.append(
            {
                "session_id": session_id,
                "client": latest_context.get("client") or "unknown",
                "started_at": latest_context.get("ts"),
                "last_event_at": after_context[-1].get("ts") if after_context else latest_context.get("ts"),
                "last_operation": after_context[-1].get("operation") if after_context else "memory_context",
                "operations": len(after_context),
            }
        )
    return sorted(result, key=lambda item: str(item.get("started_at") or ""), reverse=True)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile))))
    return round(float(ordered[index]), 1)


def _latency_summary(events: list[dict]) -> dict:
    by_operation: dict[str, list[float]] = {}
    all_values: list[float] = []
    for event in events:
        if event.get("category") != "mcp" or event.get("status") not in {"completed", "failed"}:
            continue
        value = event.get("duration_ms")
        if not isinstance(value, (int, float)):
            continue
        operation = str(event.get("operation") or "unknown")
        by_operation.setdefault(operation, []).append(float(value))
        all_values.append(float(value))
    operations = {}
    for operation, values in by_operation.items():
        operations[operation] = {
            "count": len(values),
            "p50_ms": _percentile(values, 0.50),
            "p95_ms": _percentile(values, 0.95),
            "p99_ms": _percentile(values, 0.99),
            "max_ms": round(max(values), 1),
        }
    return {
        "count": len(all_values),
        "p50_ms": _percentile(all_values, 0.50),
        "p95_ms": _percentile(all_values, 0.95),
        "p99_ms": _percentile(all_values, 0.99),
        "operations": operations,
    }


def _project_snapshot(
    root: Path,
    *,
    include_handoff_text: bool = False,
    registered: dict | None = None,
) -> dict:
    registered = dict(registered) if registered is not None else (get_registered_project(root) or {})
    events = read_events(root, limit=500, since_seconds=12 * 3600)
    metrics_5m = aggregate_events(root, since_seconds=300, recent_limit=20)
    scan: dict = {}
    try:
        from ai_layer.memory.freshness import load_scan_metadata

        project_stub = type("ProjectStub", (), {"root_path": str(root)})()
        scan = load_scan_metadata(project_stub)
    except (OSError, RuntimeError):
        pass
    from ai_layer.application.tasks import read_state as read_task_state
    from ai_layer.memory.refresh_runtime import refresh_status

    task_state = read_task_state(root)
    memory_refresh = refresh_status(root)
    return {
        "root": str(root),
        "project_id": registered.get("project_id"),
        "name": registered.get("name") or root.name,
        "mode": registered.get("mode", "standard"),
        "provenance": registered.get("provenance", "allow"),
        "last_scan": scan.get("scanned_at"),
        "scan_reason": scan.get("reason"),
        "scan_files": scan.get("files"),
        "active_operations": _active_operations(events),
        "task": task_state.get("current") or task_state.get("latest"),
        "task_active": bool(task_state.get("current")),
        # Kept as low-level compatibility telemetry only; real Task state lives above.
        "open_task_flows": _open_task_flows(events),
        "last_handoff": _latest_session_snapshot(root) if include_handoff_text else None,
        "recent_events": events[-20:],
        "mcp_latency": _latency_summary(events),
        "memory_refresh": memory_refresh,
        "last_5m": {
            "completed": metrics_5m["terminal"],
            "failed": metrics_5m["failed"],
            "operations": metrics_5m["operations"],
        },
    }


def _cached_database_status(ttl_seconds: float = 5.0) -> dict:
    global _DB_STATUS_CACHE
    now = time.monotonic()
    if _DB_STATUS_CACHE is not None and now - _DB_STATUS_CACHE[0] < ttl_seconds:
        return dict(_DB_STATUS_CACHE[1])
    from ai_layer.db.session import database_status

    state = database_status()
    _DB_STATUS_CACHE = (now, dict(state))
    return state


def observability_snapshot(
    project_root: str | Path | None = None,
    *,
    all_projects: bool = False,
    include_handoff_text: bool = False,
) -> dict:
    """Build a cheap live snapshot without rescanning repositories or querying embeddings."""
    from ai_layer import __version__
    from ai_layer.core.mcp_process import list_mcp_processes

    registered_for_root: dict[str, dict] = {}
    if all_projects:
        entries = list_registered_projects(existing_only=True)
        roots = [Path(str(item["root"])) for item in entries if item.get("root")]
        registered_for_root = {
            str(Path(str(item["root"])).resolve()): item
            for item in entries
            if item.get("root")
        }
    elif project_root is not None:
        resolved = resolve_registered_root(project_root)
        roots = [resolved] if resolved is not None else []
    else:
        cwd_root = resolve_registered_root(Path.cwd())
        if cwd_root is not None:
            roots = [cwd_root]
        else:
            entries = list_registered_projects(existing_only=True)
            roots = [Path(str(item["root"])) for item in entries if item.get("root")]
            registered_for_root = {
            str(Path(str(item["root"])).resolve()): item
            for item in entries
            if item.get("root")
        }

    projects = [
        _project_snapshot(
            root,
            include_handoff_text=include_handoff_text,
            registered=registered_for_root.get(str(root.resolve())),
        )
        for root in roots
    ]
    processes = list_mcp_processes()
    active_session_ids = {str(item.get("session_id")) for item in processes if item.get("session_id")}
    for project in projects:
        project["open_task_flows"] = [
            item
            for item in (project.get("open_task_flows") or [])
            if str(item.get("session_id")) in active_session_ids
        ]

    now = utcnow()
    for process in processes:
        last_seen = parse_ts(process.get("last_seen_at") or process.get("started_at"))
        idle_seconds = (now - last_seen).total_seconds() if last_seen else None
        process["idle_seconds"] = round(idle_seconds, 1) if idle_seconds is not None else None
        # stdio bridge calls carry a declared absolute deadline. If the bridge remains inside a
        # call past that deadline, surface STUCK instead of an ambiguous spinner.
        if process.get("current_tool"):
            deadline = float(process.get("current_deadline_seconds") or 0.0)
            process["activity_state"] = (
                "STUCK" if idle_seconds is not None and deadline > 0 and idle_seconds > deadline + 2.0 else "ACTIVE"
            )
        else:
            process["activity_state"] = "IDLE"
    return {
        "version": __version__,
        "generated_at": now.isoformat(),
        "database": _cached_database_status(),
        "mcp_processes": processes,
        "projects": projects,
        "event_retention_days": EVENT_RETENTION_DAYS,
        "privacy": "metadata-only; prompts, source text and tool results are not recorded",
    }
