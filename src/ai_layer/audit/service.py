from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai_layer.core.filelock import directory_lock
from ai_layer.core.mcp_process import begin_mcp_activity, current_mcp_session_id, end_mcp_activity
from ai_layer.core.paths import project_state_path
from ai_layer.core.registry import get_registered_project
from ai_layer.observability.service import emit_event

AUDIT_RELATIVE_PATH = Path("audit") / "mcp.jsonl"
MAX_AUDIT_BYTES = 4 * 1024 * 1024
AUDIT_TAIL_BYTES = 512 * 1024
AUDIT_SAFE_METRIC_KEYS = {
    "task",
    "status",
    "stage",
    "next_stage",
    "open_findings",
    "handoff_written",
    "normalization_count",
    "effective_verdict",
}


def _server_version() -> str:
    try:
        from ai_layer import __version__

        return __version__
    except Exception:
        return "unknown"


def audit_path(project_root: str | Path) -> Path:
    return project_state_path(project_root, *AUDIT_RELATIVE_PATH.parts)


def _safe_audit_metrics(metrics: dict | None) -> dict | None:
    if not isinstance(metrics, dict):
        return None
    safe = {}
    for key, value in metrics.items():
        if str(key) not in AUDIT_SAFE_METRIC_KEYS:
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            safe[str(key)] = value
        elif isinstance(value, str):
            safe[str(key)] = value[:120]
    return safe or None


def _append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    lock = path.parent / ".mcp-audit-write.lock"
    with directory_lock(lock, timeout_seconds=2, stale_after_seconds=60):
        try:
            oversized = path.exists() and path.stat().st_size >= MAX_AUDIT_BYTES
        except OSError:
            oversized = False
        if oversized:
            previous = path.with_name("mcp.previous.jsonl")
            older = path.with_name("mcp.previous.2.jsonl")
            if previous.is_symlink():
                raise RuntimeError(f"Refusing symlinked audit rotation target: {previous}")
            if older.is_symlink():
                raise RuntimeError(f"Refusing symlinked audit rotation target: {older}")
            if previous.exists():
                os.replace(previous, older)
            os.replace(path, previous)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)


def _tail_lines(path: Path, max_bytes: int = AUDIT_TAIL_BYTES) -> list[str]:
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


@contextmanager
def mcp_audit(
    project_root: str | Path, tool: str, *, arg_keys: list[str] | None = None
) -> Iterator[dict]:
    """Append a privacy-minimal MCP audit event.

    Argument values and tool results are deliberately not logged: QA needs call observability, not a
    second copy of project prompts, secrets, or retrieved source.
    """
    root = str(Path(project_root).expanduser().resolve())
    started = time.perf_counter()
    correlation_id = uuid4().hex
    session_id = current_mcp_session_id()
    error_type: str | None = None
    ok = False
    registered = False
    state: dict = {"metrics": {}}
    try:
        registered = get_registered_project(root) is not None
    except RuntimeError:
        registered = False
    if registered:
        begin_mcp_activity(root, tool, correlation_id)
        emit_event(
            root,
            category="mcp",
            operation=tool,
            status="started",
            correlation_id=correlation_id,
            session_id=session_id,
            metrics={"arg_keys": sorted(set(arg_keys or []))},
            source="mcp",
        )
    try:
        yield state
        ok = True
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            if registered:
                _append_event(
                    audit_path(root),
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "tool": tool,
                        "project_root": root,
                        "server_version": _server_version(),
                        "pid": os.getpid(),
                        "ok": ok,
                        "duration_ms": duration_ms,
                        "arg_keys": sorted(set(arg_keys or [])),
                        "error_type": error_type,
                        "session_id": session_id,
                        "correlation_id": correlation_id,
                        "client": os.getenv("AI_LAYER_CLIENT") or "unknown",
                        "metrics": _safe_audit_metrics(state.get("metrics")),
                    },
                )
                emit_event(
                    root,
                    category="mcp",
                    operation=tool,
                    status="completed" if ok else "failed",
                    correlation_id=correlation_id,
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metrics={
                        "arg_keys": sorted(set(arg_keys or [])),
                        **(state.get("metrics") or {}),
                    },
                    error_type=error_type,
                    source="mcp",
                )
                end_mcp_activity(root, correlation_id)
        except (OSError, RuntimeError):
            # Observability must never make a project tool unusable. Unsafe state paths are ignored
            # here; the DB-backed tool path performs its own hard checks.
            pass


def read_audit(project_root: str | Path, limit: int = 50) -> list[dict]:
    try:
        path = audit_path(project_root)
    except RuntimeError:
        return []
    wanted = max(1, limit)
    lines: list[str] = []
    older = path.with_name("mcp.previous.2.jsonl")
    previous = path.with_name("mcp.previous.jsonl")
    if older.exists() and not older.is_symlink():
        lines.extend(_tail_lines(older))
    if previous.exists() and not previous.is_symlink():
        lines.extend(_tail_lines(previous))
    if path.exists() and not path.is_symlink():
        lines.extend(_tail_lines(path))
    events: list[dict] = []
    for line in lines[-wanted:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def check_latest_flow(project_root: str | Path, limit: int = 200) -> dict:
    """Verify the latest task-sized MCP flow without logging prompt/source/result payloads."""
    events = read_audit(project_root, limit=max(10, limit))
    latest_context = None
    for index in range(len(events) - 1, -1, -1):
        if events[index].get("tool") == "memory_context":
            latest_context = index
            break
    if latest_context is None:
        return {"ok": False, "reason": "no memory_context event found", "events": 0}

    def terminal_kind(event: dict) -> str | None:
        if not event.get("ok", False):
            return None
        if event.get("tool") == "session_save":
            return "session_save"
        metrics = event.get("metrics") or {}
        if (
            event.get("tool")
            in {
                "task_stage_complete",
                "task_implementation_complete",
                "task_review_complete",
                "task_fix_complete",
            }
            and metrics.get("status") == "completed"
        ):
            return "managed_task"
        if event.get("tool") == "task_cancel":
            return "cancelled_task"
        return None

    previous_terminal = -1
    for index in range(latest_context - 1, -1, -1):
        if terminal_kind(events[index]) is not None:
            previous_terminal = index
            break

    completion_index = None
    completion_kind = None
    for index in range(latest_context + 1, len(events)):
        kind = terminal_kind(events[index])
        if kind is not None:
            completion_index = index
            completion_kind = kind
            break

    end = completion_index if completion_index is not None else len(events) - 1
    flow = events[previous_terminal + 1 : end + 1]
    tools = [str(item.get("tool")) for item in flow]
    failures = [
        {"tool": item.get("tool"), "error_type": item.get("error_type")}
        for item in flow
        if not item.get("ok", False)
    ]
    context_calls = sum(1 for tool in tools if tool == "memory_context")
    duplicate_context = context_calls > 1
    warnings: list[dict] = []
    if duplicate_context:
        warnings.append(
            {
                "code": "tool_economy",
                "message": (
                    f"server-side memory_context was called {context_calls} times in one "
                    "completed flow; reuse returned context unless state changed materially."
                ),
            }
        )

    handoff_written = False
    if completion_index is not None:
        completion_metrics = events[completion_index].get("metrics") or {}
        handoff_written = completion_kind == "session_save" or bool(
            completion_metrics.get("handoff_written")
        )
    successful_terminal = completion_kind in {"session_save", "managed_task"}
    versions = sorted(
        {str(item.get("server_version")) for item in flow if item.get("server_version")}
    )
    return {
        "ok": successful_terminal and handoff_written and context_calls >= 1 and not failures,
        "tools": tools,
        "session_saved": handoff_written,
        "terminal_checkpoint": completion_kind,
        "managed_task": completion_kind == "managed_task",
        "memory_context_calls": context_calls,
        "memory_context_count_scope": "ai_layer_server_audit_events_only",
        "host_tool_schema_discovery_counted": False,
        "duplicate_memory_context": duplicate_context,
        "warnings": warnings,
        "failures": failures,
        "server_versions": versions,
        "event_count": len(flow),
    }
