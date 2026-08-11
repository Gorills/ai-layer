import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.db.base import Base
from ai_layer.db.models import Decision, Knowledge, Project, ProjectFile, ProjectSkill
from ai_layer.memory import freshness, identity, indexer, project_state, scanner


class CountingEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        items = list(texts)
        self.calls.append(items)
        return [[0.1] + [0.0] * 383 for _ in items]


def _project_db(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    project = Project(
        name="demo",
        root_path=str(tmp_path),
        languages={},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()
    return db, project


def _configure(monkeypatch):
    embedder = CountingEmbedder()
    monkeypatch.setattr(indexer, "get_embedder", lambda: embedder)
    monkeypatch.setattr(identity, "_git_changed_paths", lambda root: set())
    return embedder


def test_incremental_scan_hashes_and_refreshes_only_affected_source_evidence(tmp_path: Path, monkeypatch):
    for number in range(50):
        (tmp_path / f"file_{number:02d}.py").write_text(f"VALUE = {number}\n", encoding="utf-8")
    embedder = _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        first = scanner.scan_project(db, project, tmp_path)
        db.commit()
        assert first.hashes_calculated == 50
        assert first.embeddings_regenerated == 0
        assert embedder.calls == []

        (tmp_path / "file_03.py").write_text("VALUE = 300\n", encoding="utf-8")
        (tmp_path / "file_17.py").write_text("VALUE = 1700\n", encoding="utf-8")
        (tmp_path / "new_file.py").write_text("NEW = True\n", encoding="utf-8")
        (tmp_path / "file_40.py").unlink()

        second = scanner.scan_project(db, project, tmp_path)
        db.commit()

        assert second.hashes_calculated == 3
        assert second.changes["added"] == ["new_file.py"]
        assert second.changes["modified"] == ["file_03.py", "file_17.py"]
        assert second.changes["deleted"] == ["file_40.py"]
        assert second.changes["unchanged"] == 47
        assert second.embeddings_regenerated == 0
        assert embedder.calls == []

        sources = set(
            db.scalars(
                select(ProjectFile.path).where(ProjectFile.project_id == project.id)
            ).all()
        )
        assert "file_40.py" not in sources
        assert "new_file.py" in sources
        assert db.scalar(select(Knowledge).where(Knowledge.project_id == project.id)) is None
    finally:
        db.close()


def test_unchanged_scan_reuses_deterministic_file_identity_without_embeddings(tmp_path: Path, monkeypatch):
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    embedder = _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        first = scanner.scan_project(db, project, tmp_path)
        db.commit()
        calls_after_first = len(embedder.calls)

        second = scanner.scan_project(db, project, tmp_path)
        db.commit()

        assert second.hashes_calculated == 0
        assert second.changes["total"] == 0
        assert second.embeddings_regenerated == 0
        assert second.embeddings_reused == 0
        assert len(embedder.calls) == calls_after_first == 0
    finally:
        db.close()


def test_same_size_and_mtime_change_is_hash_verified_via_metadata_candidate(tmp_path: Path, monkeypatch):
    path = tmp_path / "app.py"
    path.write_text("alpha\n", encoding="utf-8")
    _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        scanner.scan_project(db, project, tmp_path)
        db.commit()
        before = path.stat()

        path.write_text("bravo\n", encoding="utf-8")  # same byte length
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

        second = scanner.scan_project(db, project, tmp_path)
        db.commit()

        assert second.hashes_calculated == 1
        assert second.changes["modified"] == ["app.py"]
        row = db.scalar(select(ProjectFile).where(ProjectFile.project_id == project.id, ProjectFile.path == "app.py"))
        assert row is not None
        assert row.content_sha256
        assert db.scalar(select(Knowledge).where(Knowledge.project_id == project.id)) is None
    finally:
        db.close()


def test_equal_content_rename_is_reported_and_file_evidence_moves(tmp_path: Path, monkeypatch):
    old = tmp_path / "old_name.py"
    old.write_text("VALUE = 1\n", encoding="utf-8")
    _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        scanner.scan_project(db, project, tmp_path)
        db.commit()
        old.rename(tmp_path / "new_name.py")

        second = scanner.scan_project(db, project, tmp_path)
        db.commit()

        assert second.changes["renamed"] == [{"from": "old_name.py", "to": "new_name.py"}]
        paths = set(
            db.scalars(
                select(ProjectFile.path).where(ProjectFile.project_id == project.id)
            ).all()
        )
        assert "old_name.py" not in paths
        assert "new_name.py" in paths
    finally:
        db.close()


def test_deleted_source_removes_file_evidence_but_keeps_decisions(tmp_path: Path, monkeypatch):
    source = tmp_path / "obsolete.py"
    source.write_text("OBSOLETE = True\n", encoding="utf-8")
    _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        scanner.scan_project(db, project, tmp_path)
        db.add(
            Decision(
                project_id=project.id,
                title="Keep DB",
                context="architecture",
                decision="Keep PostgreSQL",
                rationale="durability",
                embedding=[0.0] * 384,
            )
        )
        db.commit()
        source.unlink()

        scanner.scan_project(db, project, tmp_path)
        db.commit()

        assert db.scalar(
            select(ProjectFile).where(
                ProjectFile.project_id == project.id,
                ProjectFile.path == "obsolete.py",
            )
        ) is None
        assert db.scalar(select(Decision).where(Decision.project_id == project.id)) is not None
    finally:
        db.close()


def test_unstable_attempt_is_rolled_back_before_stable_commit(tmp_path: Path, monkeypatch):
    (tmp_path / ".ai-layer" / "memory").mkdir(parents=True)
    db, project = _project_db(tmp_path)
    old_state = {
        "app.py": {
            "size": 10,
            "mtime_ns": 100,
            "ctime_ns": 100,
            "content_sha256": "a" * 64,
            "indexed": True,
        }
    }
    new_state = {
        "app.py": {
            "size": 11,
            "mtime_ns": 200,
            "ctime_ns": 200,
            "content_sha256": "b" * 64,
            "indexed": True,
        }
    }
    observed = iter([
        {"app.py": {"size": 11, "mtime_ns": 200, "ctime_ns": 200}},
        {"app.py": {"size": 11, "mtime_ns": 200, "ctime_ns": 200}},
    ])
    monkeypatch.setattr(freshness, "build_file_state", lambda root: next(observed))
    monkeypatch.setattr(
        freshness,
        "embedding_signature",
        lambda: {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    )
    attempts = 0

    def fake_scan(db_session, current_project, root, **kwargs):
        nonlocal attempts
        attempts += 1
        slug = "transient" if attempts == 1 else "stable"
        db_session.add(ProjectSkill(project_id=current_project.id, skill_slug=slug, reason="test"))
        db_session.flush()
        state = old_state if attempts == 1 else new_state
        return SimpleNamespace(
            files=1,
            source_files=1,
            knowledge_items=0,
            languages={},
            dependencies={},
            selected_skills=[],
            file_state=state,
            changes={},
            hashes_calculated=0,
            embeddings_reused=0,
            embeddings_regenerated=0,
            decisions_reembedded=0,
        )

    monkeypatch.setattr(freshness, "scan_project", fake_scan)
    try:
        _, _, attempt_count = freshness.scan_until_stable(
            db,
            project,
            tmp_path,
            reason="test",
            max_attempts=2,
        )
        assert attempt_count == 2
        slugs = set(
            db.scalars(select(ProjectSkill.skill_slug).where(ProjectSkill.project_id == project.id)).all()
        )
        assert slugs == {"stable"}
    finally:
        db.close()


def test_change_detection_scales_to_10000_known_files_without_rehashing_unchanged(tmp_path: Path, monkeypatch):
    import hashlib

    digest = hashlib.sha256(b"x\n").hexdigest()
    previous = []
    for number in range(10_000):
        path = tmp_path / f"file_{number:05d}.py"
        path.write_text("x\n", encoding="utf-8")
        stat = path.stat()
        previous.append(
            SimpleNamespace(
                path=path.name,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                ctime_ns=stat.st_ctime_ns,
                content_sha256=digest,
                sha256=digest,
            )
        )

    (tmp_path / "file_00003.py").write_text("changed-three\n", encoding="utf-8")
    (tmp_path / "file_00017.py").write_text("changed-seventeen\n", encoding="utf-8")
    (tmp_path / "file_00040.py").unlink()
    (tmp_path / "new_file.py").write_text("new\n", encoding="utf-8")
    monkeypatch.setattr(identity, "_git_changed_paths", lambda root: set())

    changes = identity.classify_changes(tmp_path, previous)

    assert changes.hashes_calculated == 3
    assert changes.modified == ["file_00003.py", "file_00017.py"]
    assert changes.added == ["new_file.py"]
    assert changes.deleted == ["file_00040.py"]
    assert len(changes.unchanged) == 9_997


def test_source_scan_does_not_depend_on_embedding_provider(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source = project_root / "app.py"
    source.write_text("VALUE = 'old'\n", encoding="utf-8")
    db, project = _project_db(project_root)

    class FailingEmbedder:
        def embed(self, texts):
            raise RuntimeError("embedding provider failed")

    monkeypatch.setattr(indexer, "get_embedder", lambda: FailingEmbedder())
    monkeypatch.setattr(identity, "_git_changed_paths", lambda root: set())
    try:
        result = scanner.scan_project(db, project, project_root)
        db.commit()
        assert result.embeddings_regenerated == 0
        row = db.scalar(select(ProjectFile).where(ProjectFile.project_id == project.id, ProjectFile.path == "app.py"))
        assert row is not None and row.content_sha256
    finally:
        db.close()

def test_scanner_schema_drift_forces_reparse_of_unchanged_source(tmp_path: Path, monkeypatch):
    import json

    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    embedder = _configure(monkeypatch)
    monkeypatch.setattr(
        freshness,
        "embedding_signature",
        lambda: {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    )
    db, project = _project_db(tmp_path)
    try:
        first = scanner.scan_project(db, project, tmp_path)
        db.commit()
        freshness.write_scan_metadata(project, first, reason="initial")
        calls_after_first = len(embedder.calls)

        scan_file = tmp_path / ".ai-layer" / "memory" / freshness.SCAN_FILE
        metadata = json.loads(scan_file.read_text(encoding="utf-8"))
        metadata["scanner_schema"] = 3
        scan_file.write_text(json.dumps(metadata), encoding="utf-8")
        db.add(Knowledge(
            project_id=project.id, kind="file", title="legacy source chunk", content="VALUE = 1",
            source_path="app.py", meta={"scanner_schema": 3}, embedding=[0.0] * 384,
        ))
        db.add(Knowledge(
            project_id=project.id, kind="architecture", title="legacy architecture", content="old summary",
            source_path=None, meta={"scanner_schema": 3}, embedding=[0.0] * 384,
        ))
        db.commit()

        result = freshness.ensure_memory_fresh(db, project)

        assert result["reason"] == "scanner_schema_changed"
        assert result["hashes_calculated"] == 1
        assert result["embeddings_regenerated"] == 0
        assert result["raw_source_embeddings_regenerated"] == 0
        assert result["legacy_source_knowledge_removed"] == 2
        assert len(embedder.calls) == calls_after_first
        evidence = db.scalar(
            select(ProjectFile).where(
                ProjectFile.project_id == project.id,
                ProjectFile.path == "app.py",
            )
        )
        assert evidence is not None
        assert evidence.scanner_schema == 4
        assert evidence.content_sha256
        assert db.scalar(select(Knowledge).where(Knowledge.project_id == project.id)) is None
    finally:
        db.close()


def test_git_is_optional_evidence_for_dirty_and_untracked_sources(tmp_path: Path, monkeypatch):
    import shutil
    import subprocess

    git = shutil.which("git")
    if not git:
        return
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True)
    subprocess.run([git, "-C", str(tmp_path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run([git, "-C", str(tmp_path), "config", "user.name", "AI Layer Test"], check=True)
    tracked = tmp_path / "tracked.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run([git, "-C", str(tmp_path), "add", "tracked.py"], check=True)
    subprocess.run([git, "-C", str(tmp_path), "commit", "-qm", "baseline"], check=True)

    stat = tracked.stat()
    digest = __import__("hashlib").sha256(b"VALUE = 1\n").hexdigest()
    previous = [
        SimpleNamespace(
            path="tracked.py",
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            ctime_ns=stat.st_ctime_ns,
            content_sha256=digest,
            sha256=digest,
        )
    ]
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("NEW = True\n", encoding="utf-8")

    changes = identity.classify_changes(tmp_path, previous)

    assert {"tracked.py", "untracked.py"} <= set(changes.git_candidates)
    assert changes.modified == ["tracked.py"]
    assert changes.added == ["untracked.py"]

    monkeypatch.setattr(identity.shutil, "which", lambda name: None)
    fallback = identity.classify_changes(tmp_path, previous)
    assert fallback.modified == ["tracked.py"]
    assert fallback.added == ["untracked.py"]




def test_scan_limit_exceeded_fails_closed_without_deleting_committed_knowledge(tmp_path: Path, monkeypatch):
    from ai_layer.memory import source as source_module

    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    real_settings = source_module.get_settings()
    monkeypatch.setattr(
        source_module,
        "get_settings",
        lambda: SimpleNamespace(
            scan_max_files=2,
            scan_max_file_bytes=real_settings.scan_max_file_bytes,
        ),
    )
    _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        scanner.scan_project(db, project, tmp_path)
        db.commit()
        before = set(
            db.scalars(select(ProjectFile.path).where(ProjectFile.project_id == project.id)).all()
        )
        assert before == {"a.py", "b.py"}

        (tmp_path / "c.py").write_text("C = 1\n", encoding="utf-8")
        with pytest.raises(source_module.ScanLimitExceeded, match="scan_max_files=2"):
            scanner.scan_project(db, project, tmp_path)
        db.rollback()

        after = set(
            db.scalars(select(ProjectFile.path).where(ProjectFile.project_id == project.id)).all()
        )
        assert after == before
        assert "c.py" not in after
    finally:
        db.close()

def test_embedding_provider_vector_count_mismatch_aborts_explicit_decision_reembed(tmp_path: Path, monkeypatch):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(identity, "_git_changed_paths", lambda root: set())

    class ShortEmbedder:
        def embed(self, texts):
            return []

    monkeypatch.setattr(indexer, "get_embedder", lambda: ShortEmbedder())
    db, project = _project_db(tmp_path)
    try:
        db.add(Decision(
            project_id=project.id,
            title="Existing decision",
            context="test",
            decision="Keep current design",
            rationale="test",
            embedding=[0.0] * 384,
        ))
        db.commit()
        with pytest.raises(RuntimeError, match="Embedding provider returned"):
            scanner.scan_project(db, project, tmp_path, reembed_decisions=True)
        db.rollback()
    finally:
        db.close()

def test_unknown_binary_extension_is_identity_tracked_but_not_semantically_indexed(tmp_path: Path, monkeypatch):
    binary = tmp_path / "artifact.custom"
    binary.write_bytes(b"header\x00payload")
    embedder = _configure(monkeypatch)
    db, project = _project_db(tmp_path)
    try:
        first = scanner.scan_project(db, project, tmp_path)
        db.commit()
        assert first.source_files == 1
        assert first.files == 0
        assert first.hashes_calculated == 1
        assert first.embeddings_regenerated == 0
        assert db.scalar(
            select(Knowledge).where(
                Knowledge.project_id == project.id,
                Knowledge.source_path == "artifact.custom",
            )
        ) is None

        calls = len(embedder.calls)
        second = scanner.scan_project(db, project, tmp_path)
        db.commit()
        assert second.hashes_calculated == 0
        assert second.embeddings_regenerated == 0
        assert len(embedder.calls) == calls
    finally:
        db.close()


