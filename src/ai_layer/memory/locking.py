from __future__ import annotations

import errno
import json
import os
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai_layer.core.paths import project_state_path

LOCK_DIR = "refresh.lock"
RECLAIM_DIR = "refresh.lock.reclaim"
STALE_AFTER_SECONDS = 600
WAIT_TIMEOUT_SECONDS = 45
POLL_SECONDS = 0.05


def _lock_dir(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    memory_dir = project_state_path(root, "memory")
    memory_dir.mkdir(parents=True, exist_ok=True)
    return project_state_path(root, "memory", LOCK_DIR)


def _lock_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def _write_owner(path: Path, token: str) -> None:
    payload = {
        "pid": os.getpid(),
        "token": token,
        "created_at": datetime.now(UTC).isoformat(),
    }
    owner = path / "owner.json"
    with owner.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_owner(path: Path) -> dict | None:
    try:
        data = json.loads((path / "owner.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pid_status(pid: object) -> str:
    """Return alive/dead/unknown without assuming Unix-only process APIs."""
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 0:
        return "unknown"
    if value == os.getpid():
        return "alive"
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "alive"
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return "dead"
        if exc.errno == errno.EPERM:
            return "alive"
        return "unknown"
    return "alive"


def _can_reclaim(path: Path, stale_after_seconds: float) -> bool:
    owner = _read_owner(path)
    if owner is not None:
        status = _pid_status(owner.get("pid"))
        if status == "dead":
            return True
        # Never age-steal a lock from a process known to be alive. This avoids a long-running scan
        # losing its lock and later deleting a replacement lock in its cleanup path.
        if status == "alive":
            return False
        # A syntactically valid owner with an indeterminate PID is safer to leave alone.
        return False
    age = _lock_age_seconds(path)
    return age is not None and age > stale_after_seconds


def _try_reclaim(path: Path, stale_after_seconds: float) -> bool:
    """Serialize dead/malformed-lock cleanup so concurrent waiters cannot delete a replacement."""
    guard = path.with_name(RECLAIM_DIR)
    if guard.is_symlink():
        raise RuntimeError(f"Refusing symlinked refresh reclaim guard: {guard}")
    try:
        guard.mkdir()
    except FileExistsError:
        guard_age = _lock_age_seconds(guard)
        if guard_age is not None and guard_age > stale_after_seconds:
            try:
                shutil.rmtree(guard)
            except OSError:
                pass
        return False

    try:
        if not path.exists() or not _can_reclaim(path, stale_after_seconds):
            return False
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass
        return True
    finally:
        try:
            shutil.rmtree(guard)
        except FileNotFoundError:
            pass


@contextmanager
def project_refresh_lock(
    project_root: str | Path,
    *,
    timeout_seconds: float = WAIT_TIMEOUT_SECONDS,
    stale_after_seconds: float = STALE_AFTER_SECONDS,
) -> Iterator[dict]:
    """Cross-process, cross-platform lock for scan/freshness rebuilds.

    Atomic directory creation serializes refreshes. A lock whose owner process is confirmed dead is
    recovered immediately; malformed ownerless locks are recovered only after the stale timeout.
    Live locks are never removed merely because a scan takes longer than the stale threshold.
    """
    path = _lock_dir(project_root)
    started = time.monotonic()
    waited = False
    token = uuid4().hex
    while True:
        try:
            path.mkdir()
            try:
                _write_owner(path, token)
            except Exception:
                shutil.rmtree(path, ignore_errors=True)
                raise
            break
        except FileExistsError:
            waited = True
            if _try_reclaim(path, stale_after_seconds):
                continue
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(
                    f"AI Layer memory refresh is busy for {Path(project_root).resolve()}; "
                    f"waited {timeout_seconds:.0f}s for {path}."
                ) from None
            time.sleep(POLL_SECONDS)
    try:
        yield {"waited": waited, "lock_path": str(path)}
    finally:
        # Only the process that still owns this exact lock instance may remove it.
        owner = _read_owner(path)
        if owner is not None and owner.get("token") == token:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                pass
