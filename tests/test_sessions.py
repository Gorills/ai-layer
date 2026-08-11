from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from ai_layer.db.base import Base
from ai_layer.db.models import Project, WorkSession
from ai_layer.sessions import service as sessions


def test_session_restore_falls_back_to_project_snapshot(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".ai-layer" / "sessions").mkdir(parents=True)

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="demo",
            root_path=str(project_root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()

        class BrokenEmbedder:
            def embed(self, texts):
                raise RuntimeError("embedding offline")

        monkeypatch.setattr(sessions, "get_embedder", lambda: BrokenEmbedder())
        saved = sessions.save_session(
            db,
            project,
            goal="security review",
            completed_actions=["reviewed webhook"],
            current_state="review complete",
            next_steps=["fix signature verification"],
            important_decisions=["Verify webhook signatures using the raw request body."],
            verified_facts=["Webhook endpoint is CSRF exempt."],
            notable_findings=["Signature verification is currently dead code."],
        )
        db.commit()
        saved_id = str(saved.id)

        # Simulate the exact failure mode reported by the external test: DB session history is empty
        # while the handoff snapshot exists on disk.
        db.execute(delete(WorkSession).where(WorkSession.project_id == project.id))
        db.commit()

        restored = sessions.restore_session(db, project, "latest")
        assert restored is not None
        assert restored["id"] == saved_id
        assert restored["goal"] == "security review"
        assert restored["important_decisions"]
        assert restored["verified_facts"] == ["Webhook endpoint is CSRF exempt."]
        assert restored["notable_findings"] == ["Signature verification is currently dead code."]

        listed = sessions.list_sessions(db, project)
        assert listed and listed[0]["id"] == saved_id


def test_session_columns_have_server_defaults_for_stale_mcp_writers(tmp_path: Path):
    """An older long-lived MCP process can omit v0.1.5 evidence columns during upgrade."""
    from sqlalchemy import text

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_root = tmp_path / "legacy-writer"
    project_root.mkdir()

    with Session(engine) as db:
        project = Project(
            name="demo",
            root_path=str(project_root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        # Simulate a pre-evidence MCP writer: INSERT names only the old session columns.
        db.execute(
            text(
                """
                INSERT INTO sessions
                    (id, project_id, goal, completed_actions, current_state, next_steps, important_decisions, created_at)
                VALUES
                    (:id, :project_id, :goal, :done, :state, :next, :decisions, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "project_id": str(project.id),
                "goal": "legacy save",
                "done": "[]",
                "state": "saved by old MCP",
                "next": "[]",
                "decisions": "[]",
            },
        )
        db.commit()
        row = db.execute(text("SELECT verified_facts, notable_findings FROM sessions")).first()
        assert row is not None
        assert row[0] == "[]"
        assert row[1] == "[]"


def test_save_session_omitted_evidence_fields_are_empty_lists(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_root = tmp_path / "project-defaults"
    project_root.mkdir()
    (project_root / ".ai-layer" / "sessions").mkdir(parents=True)

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="demo",
            root_path=str(project_root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        monkeypatch.setattr(
            sessions, "get_embedder", lambda: type("E", (), {"embed": lambda self, texts: []})()
        )
        saved = sessions.save_session(
            db,
            project,
            goal="compat save",
            completed_actions=[],
            current_state="done",
            next_steps=[],
            important_decisions=[],
        )
        db.commit()
        payload = sessions.session_to_dict(saved)
        assert payload["verified_facts"] == []
        assert payload["notable_findings"] == []


def test_latest_restore_prefers_committed_database_over_newer_provisional_snapshot(
    tmp_path: Path, monkeypatch
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_root = tmp_path / "newer-snapshot"
    project_root.mkdir()

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="demo",
            root_path=str(project_root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        monkeypatch.setattr(
            sessions, "get_embedder", lambda: type("E", (), {"embed": lambda self, texts: []})()
        )
        old = sessions.save_session(
            db,
            project,
            goal="old",
            completed_actions=[],
            current_state="old state",
            next_steps=[],
            important_decisions=[],
        )
        db.commit()

        newer_id = str(uuid4())
        newer = {
            "id": newer_id,
            "goal": "new durable handoff",
            "completed_actions": ["snapshot survived"],
            "current_state": "new state",
            "next_steps": ["continue"],
            "important_decisions": [],
            "verified_facts": ["DB commit failed after snapshot"],
            "notable_findings": [],
            "created_at": (
                old.created_at.replace(tzinfo=timezone.utc)
                if old.created_at.tzinfo is None
                else old.created_at
            )
            .astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "storage": "snapshot",
        }
        # Ensure strict ordering even if the original row landed on an exact second boundary.
        newer["created_at"] = (
            datetime.fromisoformat(newer["created_at"]) + timedelta(seconds=1)
        ).isoformat()
        sessions._persist_snapshot(project, newer)

        restored = sessions.restore_session(db, project, "latest")
        assert restored is not None
        assert restored["id"] == str(old.id)
        assert restored["current_state"] == "old state"
        assert restored["storage"] == "database"


def test_latest_restore_uses_latest_pointer_without_scanning_history(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_root = tmp_path / "latest-pointer"
    project_root.mkdir()

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="demo",
            root_path=str(project_root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        monkeypatch.setattr(
            sessions,
            "get_embedder",
            lambda: type("E", (), {"embed": lambda self, texts: []})(),
        )
        saved = sessions.save_session(
            db,
            project,
            goal="latest",
            completed_actions=[],
            current_state="ready",
            next_steps=[],
            important_decisions=[],
        )
        db.commit()

        monkeypatch.setattr(
            sessions,
            "_disk_sessions",
            lambda project: (_ for _ in ()).throw(AssertionError("history scan should not run")),
        )
        restored = sessions.restore_session(db, project, "latest")
        assert restored is not None
        assert restored["id"] == str(saved.id)


def test_rolled_back_session_never_publishes_authoritative_snapshot(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = tmp_path / "rollback-session"
    root.mkdir()
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="demo", root_path=str(root), languages={}, dependencies={}, architecture_summary=""
        )
        db.add(project)
        db.commit()
        monkeypatch.setattr(
            sessions, "get_embedder", lambda: type("E", (), {"embed": lambda self, texts: []})()
        )
        item = sessions.save_session(
            db,
            project,
            goal="must rollback",
            completed_actions=[],
            current_state="not committed",
            next_steps=[],
            important_decisions=[],
        )
        session_id = str(item.id)
        db.rollback()

        snapshot_dir = sessions._snapshot_dir(project)
        assert not (snapshot_dir / f"{session_id}.json").exists()
        assert sessions.restore_session(db, project, "latest") is None


def test_save_session_bounds_and_redacts_durable_handoff(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_root = tmp_path / "bounded-session"
    project_root.mkdir()
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="demo",
            root_path=str(project_root),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.commit()
        monkeypatch.setattr(
            sessions, "get_embedder", lambda: type("E", (), {"embed": lambda self, texts: []})()
        )
        saved = sessions.save_session(
            db,
            project,
            goal="Investigate token=super-secret-value",
            completed_actions=["Authorization: Bearer abcdefghijklmnopqrstuvwxyz"],
            current_state="password=hunter2",
            next_steps=[],
            important_decisions=[],
        )
        db.commit()
        payload = sessions.session_to_dict(saved)
        serialized = str(payload)
        assert "super-secret-value" not in serialized
        assert "abcdefghijklmnopqrstuvwxyz" not in serialized
        assert "hunter2" not in serialized
        assert "<redacted>" in serialized

        try:
            sessions.save_session(
                db,
                project,
                goal="g",
                completed_actions=["x"] * (sessions.MAX_SESSION_LIST_ITEMS + 1),
                current_state="state",
                next_steps=[],
                important_decisions=[],
            )
        except ValueError as exc:
            assert "item limit" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("oversized session list must be rejected")
