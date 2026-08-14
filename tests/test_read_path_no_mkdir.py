from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.application import project_intelligence as pi
from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.memory.freshness import (
    load_file_state,
    load_scan_metadata,
    probe_memory_freshness,
    write_scan_metadata,
)


def _isolate_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    return home


def _project_stub(root: Path) -> SimpleNamespace:
    return SimpleNamespace(root_path=str(root.resolve()))


def _scan_stats(file_state: dict | None = None) -> SimpleNamespace:
    current = file_state or {"app.py": {"size": 1, "mtime_ns": 1, "ctime_ns": 1}}
    return SimpleNamespace(
        files=len(current),
        knowledge_items=0,
        languages={"python": 1},
        dependencies={},
        selected_skills=[],
        file_state=current,
    )


@contextmanager
def _bound_status_db(tmp_path: Path, root: Path):
    import ai_layer.db.session as db_session

    engine = create_engine(f"sqlite:///{tmp_path / 'status.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Project(
                name="status-proj",
                root_path=str(root.resolve()),
                languages={},
                dependencies={},
                architecture_summary="",
            )
        )
        db.commit()
    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session


def test_overview_get_on_clean_standard_project_creates_no_ai_layer(
    monkeypatch, tmp_path: Path
) -> None:
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "clean-overview", "Clean Overview")
    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    import ai_layer.observability.snapshot as snapshot

    snapshot._DB_STATUS_CACHE = None
    assert not (project / ".ai-layer").exists()

    from ai_layer.api.app import create_app

    response = TestClient(create_app()).get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["projects"] == 1
    assert data["projects"][0]["last_scan"] is None
    assert data["projects"][0]["scan_files"] is None
    assert not (project / ".ai-layer").exists()
    assert not (project / ".ai-layer" / "memory").exists()


def test_load_scan_metadata_and_probe_succeed_without_creating_dirs(
    monkeypatch, tmp_path: Path
) -> None:
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    stub = _project_stub(project)

    assert load_scan_metadata(stub) == {}
    assert load_file_state(stub) == {}
    probe = probe_memory_freshness(stub)
    assert probe["status"] == "missing"
    assert probe["snapshot_available"] is False
    assert not (project / ".ai-layer").exists()


def test_existing_scan_metadata_still_loads(monkeypatch, tmp_path: Path) -> None:
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    memory = project / ".ai-layer" / "memory"
    memory.mkdir(parents=True)
    (memory / "scan.json").write_text(
        '{"reason": "manual", "files": 4, "scanned_at": "2026-08-14T00:00:00+00:00"}\n',
        encoding="utf-8",
    )
    stub = _project_stub(project)

    metadata = load_scan_metadata(stub)
    assert metadata["reason"] == "manual"
    assert metadata["files"] == 4
    assert memory.is_dir()
    assert (memory / "scan.json").is_file()


def test_write_scan_metadata_still_creates_memory_dir(monkeypatch, tmp_path: Path) -> None:
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    stub = _project_stub(project)

    snapshot = write_scan_metadata(stub, _scan_stats(), reason="explicit_write")
    memory = project / ".ai-layer" / "memory"
    assert snapshot["reason"] == "explicit_write"
    assert memory.is_dir()
    assert (memory / "scan.json").is_file()
    assert (memory / "file_state.json").is_file()
    assert load_scan_metadata(stub)["reason"] == "explicit_write"


def test_project_status_read_does_not_mkdir_ai_layer(monkeypatch, tmp_path: Path) -> None:
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "clean-status", "Clean Status")
    monkeypatch.setattr(
        "ai_layer.memory.refresh_runtime.schedule_refresh",
        lambda _project: {"status": "idle"},
    )
    monkeypatch.setattr(pi, "project_map_status", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(pi, "semantic_map_status", lambda *_args, **_kwargs: {})

    with _bound_status_db(tmp_path, project):
        status = pi.project_status(project)

    assert status["index"]["freshness"]["status"] in {"missing", "initializing"}
    assert status["index"]["freshness"]["snapshot_available"] in {False, None}
    assert not (project / ".ai-layer").exists()


def test_external_and_strict_private_reads_keep_zero_footprint(monkeypatch, tmp_path: Path) -> None:
    home = _isolate_home(monkeypatch, tmp_path)
    import ai_layer.observability.snapshot as snapshot

    monkeypatch.setattr(
        "ai_layer.db.session.database_status",
        lambda: {"connected": True, "pgvector": True},
    )
    snapshot._DB_STATUS_CACHE = None

    from ai_layer.api.app import create_app

    client = TestClient(create_app())

    for mode, project_id in (("external", "ext-clean"), ("strict-private", "priv-clean")):
        project = tmp_path / mode
        project.mkdir()
        register_project(project, project_id, mode, mode=mode, provenance="forbid")
        response = client.get("/api/v1/dashboard/overview")
        assert response.status_code == 200
        assert load_scan_metadata(_project_stub(project)) == {}
        assert not (project / ".ai-layer").exists()
        assert not (home / "projects" / project_id / "memory").exists()
        assert not (home / "projects" / project_id).exists()
