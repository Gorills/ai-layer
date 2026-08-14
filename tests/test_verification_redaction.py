from __future__ import annotations

import inspect
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.core.redaction import redact_secret_argv
from ai_layer.db.base import Base
from ai_layer.db.models import Project, VerificationRun
from ai_layer.verification import present, runner
from ai_layer.verification.present import (
    DEFAULT_VIEW_EXCERPT_CHARS,
    public_verification_row,
    public_verification_view,
)
from ai_layer.verification.runner import (
    MAX_STORED_OUTPUT_CHARS,
    VerificationRequest,
    persist_verification,
)

TOKEN = "leak-token-value-999"
PASSWORD = "hunter2-password-xyz"
KEEP = "KEEP_SUMMARY 3 passed"


def _project(tmp_path: Path, monkeypatch) -> Project:
    root = tmp_path / "target"
    root.mkdir()
    state = tmp_path / "machine-state"
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(projects_state_dir=state))
    return Project(
        id=uuid.uuid4(),
        name="verify",
        root_path=str(root),
        languages={},
        dependencies={},
        architecture_summary="",
    )


def test_runner_redacts_token_argv_and_password_output_and_bounds_store(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    blob = tmp_path / "blob.txt"
    blob.write_text(("X" * 20_000) + f"\npassword={PASSWORD}\n", encoding="utf-8")
    request = VerificationRequest.from_values(
        [
            sys.executable,
            "-c",
            "import sys; print('KEEP_SUMMARY 3 passed'); print(sys.argv[-1]); print(open(sys.argv[1]).read())",
            str(blob),
            f"--token={TOKEN}",
        ],
        timeout_seconds=10,
    )
    result, payload = runner.execute_verification(project, request)
    stored = json.loads(Path(result.evidence_ref).read_text(encoding="utf-8"))

    assert TOKEN not in json.dumps(stored["command"])
    assert TOKEN not in stored["output_summary"]
    assert TOKEN not in result.output_summary
    assert PASSWORD not in stored["output_summary"]
    assert "--token=<redacted>" in stored["command"]
    assert KEEP in stored["output_summary"]
    assert len(stored["output_summary"]) <= MAX_STORED_OUTPUT_CHARS
    assert len(stored["output_summary"]) < 16_000
    assert payload["command"] == stored["command"]
    assert result.passed is True


def test_runner_redacts_equals_form_credential_and_authorization_argv(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path, monkeypatch)
    request = VerificationRequest.from_values(
        [
            sys.executable,
            "-c",
            "print('KEEP_SUMMARY 3 passed')",
            f"--credential={TOKEN}",
            f"--authorization={PASSWORD}",
        ],
        timeout_seconds=10,
    )
    result, payload = runner.execute_verification(project, request)
    stored = json.loads(Path(result.evidence_ref).read_text(encoding="utf-8"))
    command = json.dumps(stored["command"])
    assert "--credential=<redacted>" in stored["command"]
    assert "--authorization=<redacted>" in stored["command"]
    assert TOKEN not in command
    assert PASSWORD not in command
    assert TOKEN not in json.dumps(payload)
    view = public_verification_view(
        {
            "command": [f"--credential={TOKEN}", f"--authorization={PASSWORD}"],
            "exit_code": 0,
            "timed_out": False,
            "output_summary": KEEP,
        }
    )
    assert view["command"] == ["--credential=<redacted>", "--authorization=<redacted>"]
    assert TOKEN not in json.dumps(view)
    assert PASSWORD not in json.dumps(view)


def test_runner_redacts_space_separated_token_argv(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    request = VerificationRequest.from_values(
        [
            sys.executable,
            "-c",
            "import sys; print('KEEP_SUMMARY 3 passed'); print(sys.argv[-1])",
            "--token",
            TOKEN,
        ],
        timeout_seconds=10,
    )
    result, payload = runner.execute_verification(project, request)
    stored = json.loads(Path(result.evidence_ref).read_text(encoding="utf-8"))
    assert stored["command"][-2:] == ["--token", "<redacted>"]
    assert TOKEN not in stored["output_summary"]
    assert TOKEN not in json.dumps(payload)
    assert KEEP in result.output_summary


def test_default_view_does_not_dump_legacy_16k_or_secrets() -> None:
    command = [sys.executable, "-c", "print('ok')", f"--token={TOKEN}"]
    summary = KEEP + "\n" + ("Y" * 16_000) + f"\npassword={PASSWORD}\n"
    view = public_verification_view(
        {
            "id": "run-1",
            "assurance": "ai_layer_verified",
            "command": command,
            "exit_code": 0,
            "timed_out": False,
            "output_summary": summary,
            "evidence_ref": "evidence.json",
        }
    )
    assert view["name"]
    assert view["status"] == "passed"
    assert view["exit_code"] == 0
    assert view["passed"] is True
    assert TOKEN not in json.dumps(view["command"])
    assert TOKEN not in view["output_summary"]
    assert PASSWORD not in view["output_summary"]
    assert KEEP in view["output_summary"]
    assert len(view["output_summary"]) <= DEFAULT_VIEW_EXCERPT_CHARS
    assert len(view["output_summary"]) < 16_000
    assert "--token=<redacted>" in view["command"]


def test_default_row_presenter_keeps_identity_and_bounds_output() -> None:
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id=uuid.uuid4(),
        assurance="ai_layer_verified",
        command=["pytest", "-q", f"--token={TOKEN}"],
        started_at=now,
        completed_at=now,
        exit_code=1,
        timed_out=False,
        output_summary=("Z" * 16_000) + f"\npassword={PASSWORD}\n",
        evidence_ref="/tmp/evidence.json",
        cwd=".",
        task_id=uuid.uuid4(),
        stage_id=uuid.uuid4(),
    )
    view = public_verification_row(
        row,
        extra={
            "task_id": str(row.task_id),
            "stage_id": str(row.stage_id),
            "cwd": row.cwd,
        },
    )
    assert view["id"] == str(row.id)
    assert view["task_id"] == str(row.task_id)
    assert view["status"] == "failed"
    assert view["exit_code"] == 1
    assert TOKEN not in json.dumps(view)
    assert PASSWORD not in json.dumps(view)
    assert len(view["output_summary"]) <= DEFAULT_VIEW_EXCERPT_CHARS


def test_persist_and_default_projection_are_redacted(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(project)
    db.commit()
    db.refresh(project)
    request = VerificationRequest.from_values(
        [
            sys.executable,
            "-c",
            "print('KEEP_SUMMARY 3 passed'); print('password=" + PASSWORD + "')",
            f"--token={TOKEN}",
        ],
        timeout_seconds=10,
    )
    result, _payload = runner.execute_verification(project, request)
    row = persist_verification(db, project, result)
    db.commit()
    loaded = db.get(VerificationRun, row.id)
    assert loaded is not None
    view = public_verification_row(loaded)
    dumped = json.dumps(view)
    assert TOKEN not in dumped
    assert PASSWORD not in dumped
    assert KEEP in view["output_summary"]
    assert view["status"] == "passed"
    assert len(view["output_summary"]) <= DEFAULT_VIEW_EXCERPT_CHARS
    assert TOKEN not in (loaded.output_summary or "")
    assert PASSWORD not in (loaded.output_summary or "")
    db.close()


def test_verification_helpers_do_not_reuse_runtime_event_allowlist() -> None:
    assert "SAFE_EVENT" not in inspect.getsource(runner)
    assert "SAFE_EVENT" not in inspect.getsource(present)
    assert redact_secret_argv(["--token", TOKEN]) == ["--token", "<redacted>"]
    assert redact_secret_argv([f"--credential={TOKEN}"]) == ["--credential=<redacted>"]
    assert redact_secret_argv([f"--authorization={TOKEN}"]) == ["--authorization=<redacted>"]
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "src/ai_layer/projections/dashboard.py",
        "src/ai_layer/projections/dashboard_tasks.py",
        "src/ai_layer/tasks/stage_views.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "public_verification_row" in text
        assert "SAFE_EVENT_FIELDS" not in text
