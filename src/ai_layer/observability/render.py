from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def _parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age(value: object) -> str:
    ts = _parse_ts(value)
    if ts is None:
        return "never"
    seconds = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _time(value: object) -> str:
    ts = _parse_ts(value)
    return ts.astimezone().strftime("%H:%M:%S") if ts else "--:--:--"


def _metric_summary(metrics: dict) -> str:
    preferred = (
        "memory_hits",
        "skills",
        "skill_slugs",
        "hits",
        "files",
        "knowledge_items",
        "skill_slug",
        "memory_refreshed",
        "decisions",
        "findings",
        "refresh_attempts",
        "template_version",
    )
    items = []
    for key in preferred:
        value = metrics.get(key)
        if value is None or key == "arg_keys":
            continue
        label = key.replace("_", " ")
        if isinstance(value, list):
            value = ",".join(str(item) for item in value[:8])
        items.append(f"{label}={value}")
    return " · ".join(items[:4])


def _event_line(event: dict) -> str:
    status = str(event.get("status") or "?").upper()
    operation = str(event.get("operation") or "unknown")
    category = str(event.get("category") or "kernel")
    duration = event.get("duration_ms")
    suffix = f" · {duration:.0f} ms" if isinstance(duration, (int, float)) else ""
    metrics = _metric_summary(event.get("metrics") or {})
    if metrics:
        suffix += " · " + metrics
    if event.get("error_type"):
        suffix += f" · {event['error_type']}"
    return f"{_time(event.get('ts'))}  {status:<9} {category}.{operation}{suffix}"


def render_monitor(snapshot: dict, *, recent_limit: int = 12) -> str:
    db = snapshot.get("database") or {}
    db_state = "READY" if db.get("connected") and db.get("pgvector") else "NOT READY"
    projects = snapshot.get("projects") or []
    processes = snapshot.get("mcp_processes") or []
    lines = [
        f"AI Layer {snapshot.get('version', '?')}  LIVE",
        "=" * 72,
        f"Database: {db_state}    MCP processes: {len(processes)}    Projects: {len(projects)}",
        "",
    ]

    if processes:
        lines.append("AGENTS / MCP")
        for proc in processes:
            client = str(proc.get("client") or "unknown")
            state = str(proc.get("activity_state") or "IDLE")
            tool = proc.get("current_tool")
            root = proc.get("last_project_root") or proc.get("project_root_env")
            root_label = Path(str(root)).name if root else "no project yet"
            detail = f" · {tool}" if tool else ""
            idle = proc.get("idle_seconds")
            idle_text = f" · AI activity {int(idle)}s ago" if isinstance(idle, (int, float)) else ""
            lines.append(
                f"  {client:<14} {state:<6} pid={proc.get('pid')} session={str(proc.get('session_id') or '-')[:8]}"
                f" · {root_label}{detail}{idle_text}"
            )
    else:
        lines.extend(["AGENTS / MCP", "  No running AI Layer MCP processes detected."])

    for project in projects:
        lines.extend(
            [
                "",
                f"PROJECT  {project.get('name')}  [{project.get('mode')}]",
                f"  {project.get('root')}",
            ]
        )
        lines.append(
            f"  Memory: last scan {_age(project.get('last_scan'))}"
            + (
                f" · {project.get('scan_files')} files"
                if project.get("scan_files") is not None
                else ""
            )
            + (f" · {project.get('scan_reason')}" if project.get("scan_reason") else "")
        )
        task = project.get("task") or {}
        if task:
            stage = task.get("active_stage") or {}
            stage_label = stage.get("label") or stage.get("kind") or "-"
            lines.append(
                f"  Task: {task.get('key') or '-'} · {task.get('status') or '-'}"
                f" · stage={stage_label} · findings={task.get('open_findings', 0)}"
            )
            if task.get("blocked_reason"):
                lines.append(f"    Blocked: {str(task.get('blocked_reason'))[:180]}")
        active = project.get("active_operations") or []
        if active:
            lines.append("  Active operations:")
            for event in active[-5:]:
                lines.append(f"    {_event_line(event)}")
        handoff = project.get("last_handoff") or {}
        if handoff.get("goal"):
            goal = str(handoff.get("goal")).replace("\n", " ")[:110]
            lines.append(f"  Last handoff: {goal} · {_age(handoff.get('created_at'))}")
        stats = project.get("last_5m") or {}
        lines.append(
            f"  Last 5m: completed={stats.get('completed', 0)} · failed={stats.get('failed', 0)}"
        )
        recent = [
            item
            for item in (project.get("recent_events") or [])
            if item.get("status") in {"completed", "failed"}
        ][-recent_limit:]
        if recent:
            lines.append("  Recent activity:")
            for event in recent:
                lines.append(f"    {_event_line(event)}")
        else:
            lines.append("  Recent activity: none")

    lines.extend(
        [
            "",
            "Event stream: metadata only; prompts, source text and tool results are not stored.",
            "Last handoff, when shown, is read from the existing session handoff and is not copied into events.",
            "Ctrl+C to exit.",
        ]
    )
    return "\n".join(lines)


def render_status(snapshot: dict) -> str:
    projects = snapshot.get("projects") or []
    processes = snapshot.get("mcp_processes") or []
    db = snapshot.get("database") or {}
    lines = [
        f"AI Layer {snapshot.get('version', '?')}",
        f"Database: {'READY' if db.get('connected') and db.get('pgvector') else 'NOT READY'}",
        f"MCP processes: {len(processes)}",
    ]
    for project in projects:
        active = project.get("active_operations") or []
        lines.append(
            f"Project {project.get('name')}: {project.get('mode')} · memory {_age(project.get('last_scan'))}"
            f" · active {len(active)} · failures(5m) {(project.get('last_5m') or {}).get('failed', 0)}"
        )
    if not projects:
        lines.append("Projects: none selected/registered")
    return "\n".join(lines)
