from __future__ import annotations

import errno
import json
import os
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_STALE_AFTER_SECONDS = 600.0
POLL_SECONDS = 0.025


def _age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def _pid_status(pid: object) -> str:
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


def _boot_id() -> str | None:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _process_start(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    parts = raw.split()
    return parts[21] if len(parts) > 21 else None


def _owner_process_matches(owner: dict) -> bool:
    try:
        pid = int(owner.get("pid"))
    except (TypeError, ValueError):
        return False
    stored_boot = owner.get("boot_id")
    current_boot = _boot_id()
    if stored_boot and current_boot and stored_boot != current_boot:
        return False
    stored_start = owner.get("process_start")
    current_start = _process_start(pid)
    if stored_start and current_start and str(stored_start) != str(current_start):
        return False
    return _pid_status(pid) == "alive"


def _write_owner(lock_dir: Path, token: str) -> None:
    owner = lock_dir / "owner.json"
    with owner.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "pid": os.getpid(),
                "token": token,
                "boot_id": _boot_id(),
                "process_start": _process_start(os.getpid()),
            },
            handle,
            separators=(",", ":"),
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_owner(lock_dir: Path) -> dict | None:
    try:
        data = json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _can_reclaim(lock_dir: Path, stale_after_seconds: float) -> bool:
    owner = _read_owner(lock_dir)
    if owner is not None:
        status = _pid_status(owner.get("pid"))
        if status == "dead":
            return True
        # New-format owners bind a lock to the process incarnation, not only a reusable PID.
        if owner.get("boot_id") or owner.get("process_start"):
            return not _owner_process_matches(owner)
        return False
    age = _age_seconds(lock_dir)
    return age is not None and age > stale_after_seconds


def _try_reclaim(lock_dir: Path, stale_after_seconds: float) -> bool:
    guard = lock_dir.with_name(lock_dir.name + ".reclaim")
    if guard.is_symlink():
        raise RuntimeError(f"Refusing symlinked lock reclaim guard: {guard}")
    try:
        guard.mkdir()
    except FileExistsError:
        guard_age = _age_seconds(guard)
        if guard_age is not None and guard_age > stale_after_seconds:
            shutil.rmtree(guard, ignore_errors=True)
        return False
    try:
        if not lock_dir.exists() or not _can_reclaim(lock_dir, stale_after_seconds):
            return False
        shutil.rmtree(lock_dir, ignore_errors=True)
        return not lock_dir.exists()
    finally:
        shutil.rmtree(guard, ignore_errors=True)


@contextmanager
def directory_lock(
    lock_dir: Path,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> Iterator[None]:
    """Serialize cross-process updates with atomic directory creation.

    Locks owned by a process confirmed dead are reclaimed. A malformed ownerless lock is reclaimed
    only after the stale timeout; a known-live owner is never age-stolen.
    """
    lock_dir = lock_dir.expanduser()
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    if lock_dir.is_symlink():
        raise RuntimeError(f"Refusing symlinked lock path: {lock_dir}")

    started = time.monotonic()
    token = uuid4().hex
    while True:
        try:
            lock_dir.mkdir()
            try:
                _write_owner(lock_dir, token)
            except Exception:
                shutil.rmtree(lock_dir, ignore_errors=True)
                raise
            break
        except FileExistsError:
            if _try_reclaim(lock_dir, stale_after_seconds):
                continue
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for lock: {lock_dir}") from None
            time.sleep(POLL_SECONDS)
    try:
        yield
    finally:
        owner = _read_owner(lock_dir)
        if owner is not None and owner.get("token") == token:
            shutil.rmtree(lock_dir, ignore_errors=True)
