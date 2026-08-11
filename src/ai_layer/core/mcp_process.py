from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai_layer import __version__
from ai_layer.core.config import get_settings


def _process_dir() -> Path:
    return get_settings().home / "mcp-processes"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _process_marker(pid: int | None = None) -> Path:
    return _process_dir() / f"{pid or os.getpid()}.json"


def _read_process_marker(pid: int | None = None) -> dict | None:
    path = _process_marker(pid)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def current_mcp_session_id() -> str | None:
    item = _read_process_marker()
    value = str((item or {}).get("session_id") or "").strip()
    return value or None


def begin_mcp_activity(project_root: str, tool: str, correlation_id: str) -> dict | None:
    item = _read_process_marker()
    if item is None:
        return None
    item.update(
        {
            "last_seen_at": datetime.now(UTC).isoformat(),
            "last_project_root": str(Path(project_root).expanduser().resolve()),
            "current_tool": tool,
            "current_correlation_id": correlation_id,
        }
    )
    try:
        _atomic_json(_process_marker(), item)
    except OSError:
        return None
    return item


def end_mcp_activity(project_root: str, correlation_id: str) -> dict | None:
    item = _read_process_marker()
    if item is None:
        return None
    item["last_seen_at"] = datetime.now(UTC).isoformat()
    item["last_project_root"] = str(Path(project_root).expanduser().resolve())
    if item.get("current_correlation_id") == correlation_id:
        item["current_tool"] = None
        item["current_correlation_id"] = None
    try:
        _atomic_json(_process_marker(), item)
    except OSError:
        return None
    return item


def begin_bridge_activity(tool: str, correlation_id: str, deadline_seconds: float) -> dict | None:
    item = _read_process_marker()
    if item is None:
        return None
    now = datetime.now(UTC).isoformat()
    item.update(
        {
            "last_seen_at": now,
            "current_tool": tool,
            "current_correlation_id": correlation_id,
            "current_started_at": now,
            "current_deadline_seconds": float(deadline_seconds),
            "runtime_role": "stdio-bridge",
        }
    )
    try:
        _atomic_json(_process_marker(), item)
    except OSError:
        return None
    return item


def end_bridge_activity(correlation_id: str) -> dict | None:
    item = _read_process_marker()
    if item is None:
        return None
    item["last_seen_at"] = datetime.now(UTC).isoformat()
    if item.get("current_correlation_id") == correlation_id:
        item["current_tool"] = None
        item["current_correlation_id"] = None
        item["current_started_at"] = None
        item["current_deadline_seconds"] = None
    try:
        _atomic_json(_process_marker(), item)
    except OSError:
        return None
    return item


@contextmanager
def registered_mcp_process() -> Iterator[dict]:
    """Register a running MCP process so doctor/QA can detect runtime version skew."""
    pid = os.getpid()
    path = _process_dir() / f"{pid}.json"
    started_at = datetime.now(UTC).isoformat()
    payload = {
        "pid": pid,
        "version": __version__,
        "session_id": uuid4().hex,
        "client": os.getenv("AI_LAYER_CLIENT") or "unknown",
        "model": os.getenv("AI_LAYER_MODEL"),
        "started_at": started_at,
        "last_seen_at": started_at,
        "project_root_env": os.getenv("AI_LAYER_PROJECT_ROOT"),
        "last_project_root": os.getenv("AI_LAYER_PROJECT_ROOT"),
        "current_tool": None,
        "current_correlation_id": None,
        "current_started_at": None,
        "current_deadline_seconds": None,
        "runtime_role": "stdio-bridge" if os.getenv("AI_LAYER_MCP_BRIDGE") == "1" else "direct-mcp",
    }
    _atomic_json(path, payload)
    try:
        yield payload
    finally:
        path.unlink(missing_ok=True)


def list_mcp_processes() -> list[dict]:
    directory = _process_dir()
    if not directory.exists():
        return []
    items: list[dict] = []
    for path in directory.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            pid = int(item.get("pid", 0))
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            continue
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)
            continue
        item["current_version"] = __version__
        item["version_match"] = item.get("version") == __version__
        items.append(item)
    return sorted(items, key=lambda item: int(item.get("pid", 0)))


def _is_our_mcp_process(entry: Path, uid: int, exclude_pid: int) -> bool:
    if not entry.name.isdigit():
        return False
    pid = int(entry.name)
    if pid == exclude_pid:
        return False
    try:
        if entry.stat().st_uid != uid:
            return False
        raw = (entry / "cmdline").read_bytes()
    except (OSError, PermissionError):
        return False
    # Match an argv token basename exactly. The old substring check could terminate an unrelated
    # same-user process whose argument merely mentioned "ai-layer-mcp".
    tokens = [
        Path(part.decode("utf-8", errors="replace")).name for part in raw.split(b"\x00") if part
    ]
    return "ai-layer-mcp" in tokens


def stop_user_mcp_processes(timeout_seconds: float = 2.0) -> dict:
    """Terminate this user's running ai-layer-mcp processes after a successful upgrade.

    MCP stdio servers are long-lived child processes of IDEs. They can survive an on-disk release
    switch and keep an old tool schema loaded. Linux /proc is used when available; unsupported
    platforms return a no-op result rather than guessing.
    """
    import signal
    import time

    proc_root = Path("/proc")
    if not proc_root.exists() or not hasattr(os, "getuid"):
        return {"ok": True, "supported": False, "stopped": [], "forced": []}
    uid = os.getuid()
    me = os.getpid()
    targets: list[int] = []
    # Only PIDs that registered themselves as AI Layer MCP processes are eligible. Older/untracked
    # hosts are left alone; a manual IDE reconnect is an accepted operational fallback.
    process_dir = _process_dir()
    markers = list(process_dir.glob("*.json")) if process_dir.exists() else []
    for marker in markers:
        try:
            item = json.loads(marker.read_text(encoding="utf-8"))
            pid = int(item.get("pid", 0))
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if marker.stem != str(pid):
            continue
        entry = proc_root / str(pid)
        if not _is_our_mcp_process(entry, uid, me):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            targets.append(pid)
        except (ProcessLookupError, PermissionError):
            continue

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    remaining = set(targets)
    while remaining and time.monotonic() < deadline:
        for pid in list(remaining):
            entry = proc_root / str(pid)
            if not entry.exists() or not _is_our_mcp_process(entry, uid, me):
                remaining.discard(pid)
        if remaining:
            time.sleep(0.05)

    forced: list[int] = []
    for pid in sorted(remaining):
        entry = proc_root / str(pid)
        if not entry.exists() or not _is_our_mcp_process(entry, uid, me):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            forced.append(pid)
        except (ProcessLookupError, PermissionError):
            continue
    return {"ok": True, "supported": True, "stopped": targets, "forced": forced}
