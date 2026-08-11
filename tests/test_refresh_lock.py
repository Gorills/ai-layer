import json
import os
import threading
import time
from pathlib import Path

import pytest

from ai_layer.memory import locking
from ai_layer.memory.locking import project_refresh_lock


def test_refresh_lock_serializes_concurrent_agents(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    first_entered = threading.Event()
    release_first = threading.Event()
    result: dict = {}

    def first():
        with project_refresh_lock(project):
            first_entered.set()
            assert release_first.wait(timeout=2)

    def second():
        assert first_entered.wait(timeout=2)
        with project_refresh_lock(project, timeout_seconds=2) as state:
            result.update(state)

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()
    assert first_entered.wait(timeout=2)
    time.sleep(0.1)
    release_first.set()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert not t1.is_alive() and not t2.is_alive()
    assert result["waited"] is True
    assert not (project / ".ai-layer" / "memory" / "refresh.lock").exists()


def test_refresh_lock_recovers_confirmed_dead_owner_without_waiting_stale_timeout(
    tmp_path: Path, monkeypatch
):
    project = tmp_path / "dead-owner"
    lock_dir = project / ".ai-layer" / "memory" / "refresh.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner.json").write_text(
        json.dumps({"pid": 424242, "token": "dead", "created_at": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(locking, "_pid_status", lambda pid: "dead")

    with project_refresh_lock(project, timeout_seconds=0.5, stale_after_seconds=999999) as state:
        assert state["waited"] is True
        owner = json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))
        assert owner["pid"] == os.getpid()
        assert owner["token"] != "dead"

    assert not lock_dir.exists()


def test_refresh_lock_never_age_steals_from_known_live_owner(tmp_path: Path, monkeypatch):
    project = tmp_path / "live-owner"
    lock_dir = project / ".ai-layer" / "memory" / "refresh.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner.json").write_text(
        json.dumps({"pid": 123, "token": "live", "created_at": "2020-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    old = time.time() - 3600
    os.utime(lock_dir, (old, old))
    monkeypatch.setattr(locking, "_pid_status", lambda pid: "alive")

    with pytest.raises(TimeoutError):
        with project_refresh_lock(project, timeout_seconds=0.08, stale_after_seconds=0.01):
            pass

    assert lock_dir.exists()
    assert json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))["token"] == "live"


def test_lock_owner_process_incarnation_prevents_pid_reuse_stall(tmp_path: Path, monkeypatch):
    import json

    from ai_layer.core import filelock

    lock = tmp_path / "refresh.lock"
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps({"pid": 4242, "token": "old", "boot_id": "old-boot", "process_start": "1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(filelock, "_pid_status", lambda pid: "alive")
    monkeypatch.setattr(filelock, "_boot_id", lambda: "new-boot")
    assert filelock._can_reclaim(lock, stale_after_seconds=600) is True


def test_refresh_lock_treats_invalid_utf8_owner_as_malformed(tmp_path: Path):
    project = tmp_path / "invalid-owner"
    lock_dir = project / ".ai-layer" / "memory" / "refresh.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner.json").write_bytes(b"\xff\xfe")
    old = time.time() - 3600
    os.utime(lock_dir, (old, old))

    with project_refresh_lock(project, timeout_seconds=0.5, stale_after_seconds=0.01):
        owner = json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))
        assert owner["pid"] == os.getpid()

    assert not lock_dir.exists()
