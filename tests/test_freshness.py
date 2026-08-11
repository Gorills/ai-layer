from pathlib import Path
from types import SimpleNamespace

from ai_layer.memory import freshness
from ai_layer.memory.freshness import file_state_changes


def _state(size: int, mtime_ns: int, marker: str = "a") -> dict:
    return {
        "size": size,
        "mtime_ns": mtime_ns,
        "ctime_ns": mtime_ns,
        "content_sha256": marker * 64,
        "indexed": True,
    }


def test_freshness_refreshes_legacy_state_then_stays_fresh(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "project"
    (project_root / ".ai-layer" / "memory").mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    current = {"app.py": _state(10, 100)}
    monkeypatch.setattr(freshness, "build_file_state", lambda root: current)

    calls = []
    stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
        file_state=current,
    )
    monkeypatch.setattr(
        freshness, "scan_project", lambda db, p, root, **kwargs: calls.append(root) or stats
    )

    first = freshness.ensure_memory_fresh(
        SimpleNamespace(commit=lambda: None, rollback=lambda: None), project
    )
    second = freshness.ensure_memory_fresh(
        SimpleNamespace(commit=lambda: None, rollback=lambda: None), project
    )
    assert first["refreshed"] is True
    assert second["refreshed"] is False
    assert len(calls) == 1


def test_file_state_changes_reports_new_modified_and_deleted_immediately():
    previous = {"old.py": _state(1, 1), "edit.py": _state(1, 1)}
    current = {"new_test.py": _state(2, 2, "b"), "edit.py": _state(3, 3, "c")}
    changes = file_state_changes(previous, current)
    assert changes["added"] == ["new_test.py"]
    assert changes["modified"] == ["edit.py"]
    assert changes["deleted"] == ["old.py"]
    assert changes["total"] == 3


def test_concurrent_freshness_runs_only_one_scan(tmp_path: Path, monkeypatch):
    import threading
    import time

    project_root = tmp_path / "project"
    (project_root / ".ai-layer" / "memory").mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    current = {"app.py": _state(10, 100)}
    monkeypatch.setattr(freshness, "build_file_state", lambda root: current)

    calls = []
    entered = threading.Event()
    stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
        file_state=current,
    )

    def fake_scan(db, p, root, **kwargs):
        calls.append(root)
        entered.set()
        time.sleep(0.15)
        return stats

    monkeypatch.setattr(freshness, "scan_project", fake_scan)
    results = []

    def worker():
        results.append(
            freshness.ensure_memory_fresh(
                SimpleNamespace(commit=lambda: None, rollback=lambda: None), project
            )
        )

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    assert entered.wait(timeout=2)
    t2.start()
    t1.join(timeout=3)
    t2.join(timeout=3)

    assert len(calls) == 1
    assert sorted(item["refreshed"] for item in results) == [False, True]


def test_freshness_does_not_advance_state_when_database_commit_fails(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "commit-failure"
    (project_root / ".ai-layer" / "memory").mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    current = {"app.py": _state(10, 100)}
    monkeypatch.setattr(freshness, "build_file_state", lambda root: current)
    stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
        file_state=current,
    )
    monkeypatch.setattr(freshness, "scan_project", lambda db, p, root, **kwargs: stats)

    class FailingDB:
        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            pass

    try:
        freshness.ensure_memory_fresh(FailingDB(), project)
    except RuntimeError as exc:
        assert "commit failed" in str(exc)
    else:
        raise AssertionError("commit failure must propagate")

    memory_dir = project_root / ".ai-layer" / "memory"
    assert not (memory_dir / "file_state.json").exists()
    assert not (memory_dir / "scan.json").exists()
    assert not (memory_dir / "refresh.lock").exists()


def test_freshness_retries_when_repository_changes_during_committed_scan(
    tmp_path: Path, monkeypatch
):
    project_root = tmp_path / "moving-project"
    (project_root / ".ai-layer" / "memory").mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    old = {"app.py": _state(10, 100)}
    new = {"app.py": _state(11, 200, "b")}
    states = iter([old, old, new, new])
    monkeypatch.setattr(freshness, "build_file_state", lambda root: next(states))

    old_stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
        file_state=old,
    )
    new_stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
        file_state=new,
    )
    scans = iter([old_stats, new_stats])
    scan_calls = []
    monkeypatch.setattr(
        freshness,
        "scan_project",
        lambda db, p, root, **kwargs: scan_calls.append(str(root)) or next(scans),
    )
    commits = []
    rollbacks = []
    db = SimpleNamespace(
        commit=lambda: commits.append(True),
        rollback=lambda: rollbacks.append(True),
    )

    result = freshness.ensure_memory_fresh(db, project)

    assert result["refreshed"] is True
    assert result["refresh_attempts"] == 2
    assert len(scan_calls) == 2
    assert len(commits) == 1
    assert len(rollbacks) == 1
    assert freshness.load_file_state(project) == new


def test_embedding_configuration_drift_forces_refresh_and_decision_reindex(
    tmp_path: Path, monkeypatch
):
    import json

    project_root = tmp_path / "embedding-drift"
    memory_dir = project_root / ".ai-layer" / "memory"
    memory_dir.mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    current = {"app.py": _state(10, 100)}
    (memory_dir / "file_state.json").write_text(json.dumps(current), encoding="utf-8")
    (memory_dir / "scan.json").write_text(
        json.dumps({"embedding": {"provider": "fastembed", "model": "old", "dimensions": 384}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        freshness,
        "embedding_signature",
        lambda: {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    )
    monkeypatch.setattr(freshness, "build_file_state", lambda root: current)
    calls = []
    stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
        file_state=current,
    )

    def fake_scan(db, p, root, *, reembed_decisions=False, force_reparse=False):
        calls.append((reembed_decisions, force_reparse))
        return stats

    monkeypatch.setattr(freshness, "scan_project", fake_scan)
    result = freshness.ensure_memory_fresh(
        SimpleNamespace(commit=lambda: None, rollback=lambda: None), project
    )

    assert result["refreshed"] is True
    assert result["reason"] == "embedding_configuration_changed"
    assert calls == [(True, True)]
    assert freshness.load_scan_metadata(project)["embedding"]["provider"] == "hash"


def test_freshness_refuses_symlinked_memory_state_directory(tmp_path: Path):
    project_root = tmp_path / "project-symlink-state"
    meta = project_root / ".ai-layer"
    meta.mkdir(parents=True)
    outside = tmp_path / "outside-memory-state"
    outside.mkdir()
    (meta / "memory").symlink_to(outside, target_is_directory=True)
    project = SimpleNamespace(root_path=str(project_root))

    try:
        freshness.load_file_state(project)
    except RuntimeError as exc:
        assert "symlink" in str(exc).lower()
    else:
        raise AssertionError("symlinked freshness state directory must be rejected")


def test_file_state_marker_is_not_published_when_disk_write_fails_after_commit(
    tmp_path: Path, monkeypatch
):
    project_root = tmp_path / "disk-failure"
    (project_root / ".ai-layer" / "memory").mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    current = {"app.py": _state(10, 100)}
    monkeypatch.setattr(freshness, "build_file_state", lambda root: current)
    stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=[],
        file_state=current,
    )
    monkeypatch.setattr(freshness, "scan_project", lambda db, p, root, **kwargs: stats)
    real_atomic_write = freshness._atomic_write_json

    def fail_commit_marker(path, payload, *, sort_keys=False):
        if path.name == freshness.STATE_FILE:
            raise OSError("disk full")
        return real_atomic_write(path, payload, sort_keys=sort_keys)

    monkeypatch.setattr(freshness, "_atomic_write_json", fail_commit_marker)
    commits = []
    db = SimpleNamespace(commit=lambda: commits.append(True), rollback=lambda: None)

    try:
        freshness.scan_until_stable(db, project, project_root, reason="test")
    except OSError as exc:
        assert "disk full" in str(exc)
    else:
        raise AssertionError("state publication failure must propagate")

    memory_dir = project_root / ".ai-layer" / "memory"
    assert commits == [True]
    assert (memory_dir / freshness.SCAN_FILE).exists()
    assert not (memory_dir / freshness.STATE_FILE).exists()


def test_scan_limit_failure_rolls_back_before_publication(tmp_path: Path, monkeypatch):
    from ai_layer.memory.source import ScanLimitExceeded

    project_root = tmp_path / "limit-failure"
    (project_root / ".ai-layer" / "memory").mkdir(parents=True)
    project = SimpleNamespace(root_path=str(project_root))
    current = {"app.py": _state(10, 100)}
    stats = SimpleNamespace(
        files=1,
        knowledge_items=1,
        languages={"python": 1},
        dependencies={},
        selected_skills=[],
        file_state=current,
    )
    monkeypatch.setattr(freshness, "scan_project", lambda db, p, root, **kwargs: stats)

    def over_limit(root):
        raise ScanLimitExceeded("scan_max_files=1")

    monkeypatch.setattr(freshness, "build_file_state", over_limit)
    commits = []
    rollbacks = []
    db = SimpleNamespace(
        commit=lambda: commits.append(True), rollback=lambda: rollbacks.append(True)
    )

    try:
        freshness.scan_until_stable(db, project, project_root, reason="test")
    except ScanLimitExceeded:
        pass
    else:
        raise AssertionError("scan limit failure must propagate")

    assert commits == []
    assert rollbacks == [True]
    memory_dir = project_root / ".ai-layer" / "memory"
    assert not (memory_dir / freshness.STATE_FILE).exists()
    assert not (memory_dir / freshness.SCAN_FILE).exists()


def test_git_generation_probe_skips_full_file_walk_on_unchanged_repository(
    tmp_path: Path, monkeypatch
):
    import json
    from ai_layer.memory.embeddings import embedding_signature
    from ai_layer.memory.versioning import CONTENT_IDENTITY_VERSION, SCANNER_SCHEMA_VERSION

    root = tmp_path / "probe-project"
    memory_dir = root / ".ai-layer" / "memory"
    memory_dir.mkdir(parents=True)
    project = SimpleNamespace(root_path=str(root))
    state = {"app.py": _state(12, 34)}
    probe = {"kind": "git-v1", "head": "abc", "status_sha256": "def", "dirty": {}}
    (memory_dir / "file_state.json").write_text(json.dumps(state), encoding="utf-8")
    (memory_dir / "scan.json").write_text(
        json.dumps(
            {
                "files": 1,
                "embedding": embedding_signature(),
                "content_identity_version": CONTENT_IDENTITY_VERSION,
                "scanner_schema": SCANNER_SCHEMA_VERSION,
                "repository_probe": probe,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(freshness, "repository_probe", lambda root: probe)
    monkeypatch.setattr(
        freshness,
        "build_file_state",
        lambda root: (_ for _ in ()).throw(AssertionError("full file walk must be skipped")),
    )

    result = freshness.ensure_memory_fresh(
        SimpleNamespace(commit=lambda: None, rollback=lambda: None), project
    )
    assert result["refreshed"] is False
    assert result["freshness_probe"] == "git"
    assert result["files"] == 1
