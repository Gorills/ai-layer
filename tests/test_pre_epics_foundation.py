from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.agents.policy import build_agent_requirement, requested_tier
from ai_layer.db.base import Base
from ai_layer.db.models import Project, RuntimeEvent, TaskStage, utcnow
from ai_layer.installation import updater
from ai_layer.tasks import service as tasks
from ai_layer.tasks.worker_leases import heartbeat_worker, reap_stale_worker_leases
from ai_layer.verification import runner
from ai_layer.verification.runner import VerificationRequest


def _db_project(tmp_path: Path) -> tuple[Session, Project, Path]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="demo",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()
    return db, project, root


@pytest.mark.parametrize(
    ("stage", "workflow", "risk", "complexity", "uncertainty", "preference", "tier", "readonly"),
    [
        ("implement", "micro", "low", "low", "low", "economy", "economy", False),
        ("implement", "standard", "normal", "high", "normal", "economy", "balanced", False),
        ("implement", "standard", "high", "high", "normal", "economy", "strong", False),
        ("discovery", "discovery_first", "low", "low", "normal", "economy", "economy", True),
        ("review", "standard", "high", "normal", "normal", "balanced", "strong", True),
        ("fix", "standard", "high", "low", "normal", "economy", "balanced", False),
        ("implement", "standard", "low", "low", "low", "balanced", "balanced", False),
        ("implement", "standard", "normal", "normal", "normal", "quality", "balanced", False),
        ("review", "standard", "normal", "normal", "normal", "quality", "strong", True),
    ],
)
def test_agent_requirement_and_host_tier_matrix(
    stage: str,
    workflow: str,
    risk: str,
    complexity: str,
    uncertainty: str,
    preference: str,
    tier: str,
    readonly: bool,
) -> None:
    requirement = build_agent_requirement(
        stage_kind=stage,
        workflow_profile=workflow,
        risk_level=risk,
        complexity_level=complexity,
        uncertainty_level=uncertainty,
        cost_policy=preference,
    )
    selected, _ = requested_tier(
        stage_kind=stage,
        workflow_profile=workflow,
        risk_level=risk,
        complexity_level=complexity,
        uncertainty_level=uncertainty,
        cost_policy=preference,
    )
    assert requirement.role in {"implementer", "reviewer", "fixer", "discovery"}
    assert requirement.risk == risk
    assert requirement.complexity == complexity
    assert requirement.uncertainty == uncertainty
    assert requirement.quality_cost_preference == preference
    assert requirement.readonly is readonly
    assert selected == tier


def test_verification_runner_executes_command_and_persists_private_evidence(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "target"
    root.mkdir()
    state = tmp_path / "machine-state"
    project = Project(
        id=uuid.uuid4(),
        name="verify",
        root_path=str(root),
        languages={},
        dependencies={},
        architecture_summary="",
    )
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(projects_state_dir=state))

    request = VerificationRequest.from_values(
        [sys.executable, "-c", "import os; print('verified=' + os.environ['AI_LAYER_VERIFY_CASE'])"],
        environment={"AI_LAYER_VERIFY_CASE": "foundation"},
        timeout_seconds=10,
    )
    result, payload = runner.execute_verification(project, request)

    assert result.assurance.value == "ai_layer_verified"
    assert result.passed is True
    assert result.exit_code == 0
    assert "verified=foundation" in result.output_summary
    evidence = Path(result.evidence_ref or "")
    assert evidence.is_file()
    assert evidence.is_relative_to(state)
    assert (evidence.stat().st_mode & 0o777) == 0o600
    stored = json.loads(evidence.read_text(encoding="utf-8"))
    assert stored["environment"] == {"AI_LAYER_VERIFY_CASE": "foundation"}
    assert stored["exit_code"] == 0
    assert payload["evidence_ref"] == str(evidence)


def _write_signed_update_channel(tmp_path: Path, *, artifact_digest_override: str | None = None) -> tuple[Path, Path, Path]:
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is required for signed updater test")
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    subprocess.run(
        [openssl, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [openssl, "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
    )

    artifact = tmp_path / "release.zip"
    root = "local-ai-development-layer-99.0.0"
    with zipfile.ZipFile(artifact, "w") as bundle:
        bundle.writestr(root + "/scripts/release_gate.py", "print('preflight ok')\n")
        bundle.writestr(root + "/install.sh", "#!/bin/sh\nset -eu\nprintf 'install ok\\n'\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    signature = tmp_path / "manifest.sig"
    payload = {
        "schema": 1,
        "version": "99.0.0",
        "artifact_url": artifact.as_uri(),
        "artifact_sha256": artifact_digest_override or digest,
        "signature_url": signature.as_uri(),
    }
    manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    subprocess.run(
        [openssl, "dgst", "-sha256", "-sign", str(private_key), "-out", str(signature), str(manifest)],
        check=True,
        capture_output=True,
    )
    return manifest, public_key, artifact


def test_signed_one_command_updater_checks_and_installs_local_release(tmp_path: Path, monkeypatch) -> None:
    manifest, public_key, _ = _write_signed_update_channel(tmp_path)
    machine_home = tmp_path / "machine-home"
    machine_home.mkdir()
    monkeypatch.setattr(updater, "get_settings", lambda: SimpleNamespace(home=machine_home))

    checked = updater.check_update(manifest_url=manifest.as_uri(), public_key=public_key)
    assert checked["ok"] is True
    assert checked["signature"] == "verified"
    assert checked["available_version"] == "99.0.0"
    assert checked["update_available"] is True

    installed = updater.install_update(manifest_url=manifest.as_uri(), public_key=public_key)
    assert installed["ok"] is True
    assert installed["updated"] is True
    assert installed["installed_version"] == "99.0.0"
    assert installed["installer"] == "completed"


def test_signed_updater_rejects_checksum_mismatch(tmp_path: Path, monkeypatch) -> None:
    manifest, public_key, _ = _write_signed_update_channel(tmp_path, artifact_digest_override="0" * 64)
    machine_home = tmp_path / "machine-home"
    machine_home.mkdir()
    monkeypatch.setattr(updater, "get_settings", lambda: SimpleNamespace(home=machine_home))

    with pytest.raises(RuntimeError, match="UPDATE_CHECKSUM_MISMATCH"):
        updater.install_update(manifest_url=manifest.as_uri(), public_key=public_key)


def test_release_archive_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("release/install.sh", "#!/bin/sh\n")
        bundle.writestr("release/scripts/release_gate.py", "print('ok')\n")
        bundle.writestr("release/../../escape.txt", "nope")
    with pytest.raises(RuntimeError, match="unsafe release archive member"):
        updater._safe_extract(archive, tmp_path / "out")


def test_worker_disconnect_without_changes_redelegates_same_stage(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(db, project, goal="Change value", acceptance_criteria=[], constraints=[])
        delegated = tasks.delegate_current_stage(db, project, worker_id="lost-worker")
        previous_stage_id = delegated["active_stage"]["id"]

        recovered = tasks.recover_disconnected_worker(db, project, reason="host session disappeared")

        assert recovered["status"] == "active"
        assert recovered["active_stage"]["kind"] == created["active_stage"]["kind"]
        assert recovered["active_stage"]["id"] != previous_stage_id
        assert recovered["active_stage"]["worker_id"] in {None, ""}
        invalid = db.scalar(select(TaskStage).where(TaskStage.id == uuid.UUID(previous_stage_id)))
        assert invalid is not None
        assert invalid.status == "invalid"
        assert invalid.outcome == "worker_disconnected"
    finally:
        db.close()


def test_worker_disconnect_with_changes_blocks_without_rebinding_provenance(tmp_path: Path) -> None:
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="Change value", acceptance_criteria=[], constraints=[])
        delegated = tasks.delegate_current_stage(db, project, worker_id="lost-worker")
        stage_id = delegated["active_stage"]["id"]
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

        blocked = tasks.recover_disconnected_worker(db, project, reason="worker disconnected after mutation")

        assert blocked["status"] == "blocked"
        assert blocked["active_stage"] is None
        assert blocked["blocked_reason"].startswith("WORKER_DISCONNECTED_WITH_CHANGES")
        invalid = db.scalar(select(TaskStage).where(TaskStage.id == uuid.UUID(stage_id)))
        assert invalid is not None
        assert invalid.status == "invalid"
        assert invalid.worker_id == "lost-worker"
        assert invalid.outcome == "worker_disconnected_with_changes"
    finally:
        db.close()


def test_delegation_creates_durable_worker_lease_and_heartbeat_renews_it(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="Change value", acceptance_criteria=[], constraints=[])
        delegated = tasks.delegate_current_stage(db, project, worker_id="worker-lease")
        stage_id = uuid.UUID(delegated["active_stage"]["id"])
        stage = db.get(TaskStage, stage_id)
        assert stage is not None
        assert stage.worker_heartbeat_at is not None
        assert stage.worker_lease_expires_at is not None
        first_expiry = stage.worker_lease_expires_at

        heartbeat_worker(db, project, worker_id="worker-lease", lease_seconds=5 * 60)
        db.refresh(stage)
        assert stage.worker_heartbeat_at is not None
        assert stage.worker_lease_expires_at is not None
        assert stage.worker_lease_expires_at != first_expiry
        heartbeat_event = db.scalar(
            select(RuntimeEvent)
            .where(RuntimeEvent.event_type == "AgentHeartbeat")
            .order_by(RuntimeEvent.created_at.desc())
            .limit(1)
        )
        assert heartbeat_event is not None
        assert heartbeat_event.aggregate_id == str(stage_id)
    finally:
        db.close()


def test_expired_worker_lease_without_changes_is_reaped_to_fresh_stage(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="Change value", acceptance_criteria=[], constraints=[])
        delegated = tasks.delegate_current_stage(db, project, worker_id="expired-worker")
        expired_stage_id = uuid.UUID(delegated["active_stage"]["id"])
        stage = db.get(TaskStage, expired_stage_id)
        assert stage is not None
        stage.worker_lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

        result = reap_stale_worker_leases(db, now=utcnow())

        assert result["expired"] == 1
        assert result["recovered"] == 1
        assert result["blocked"] == 0
        db.refresh(stage)
        assert stage.status == "invalid"
        assert stage.outcome == "worker_lease_expired"
        current = tasks.current_task(db, project, include_history=False)["task"]
        assert current["status"] == "active"
        assert current["active_stage"]["id"] != str(expired_stage_id)
        assert current["active_stage"]["worker_id"] is None
    finally:
        db.close()


def test_expired_worker_lease_with_changes_blocks_fail_closed(tmp_path: Path) -> None:
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="Change value", acceptance_criteria=[], constraints=[])
        delegated = tasks.delegate_current_stage(db, project, worker_id="expired-mutator")
        expired_stage_id = uuid.UUID(delegated["active_stage"]["id"])
        stage = db.get(TaskStage, expired_stage_id)
        assert stage is not None
        stage.worker_lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        (root / "app.py").write_text("VALUE = 3\n", encoding="utf-8")

        result = reap_stale_worker_leases(db, now=utcnow())

        assert result["expired"] == 1
        assert result["recovered"] == 0
        assert result["blocked"] == 1
        db.refresh(stage)
        assert stage.status == "invalid"
        assert stage.outcome == "worker_lease_expired_with_changes"
        current = tasks.current_task(db, project, include_history=False)["task"]
        assert current["status"] == "blocked"
        assert current["blocked_reason"].startswith("WORKER_DISCONNECTED_WITH_CHANGES")
    finally:
        db.close()


def _command_names(typer_app) -> set[str]:
    return {str(item.name or item.callback.__name__).replace("_", "-") for item in typer_app.registered_commands}


def test_cli_and_mcp_composition_register_foundation_contracts() -> None:
    from ai_layer.cli.app import app
    from ai_layer.cli.root import agent_app, service_app, skill_app, task_app
    from ai_layer.mcp.server import TOOL_HANDLERS

    assert {"update", "dashboard", "doctor", "init"} <= _command_names(app)
    assert {"current", "next", "resume", "cancel", "worker-disconnected", "worker-heartbeat"} <= _command_names(task_app)
    assert {"list", "add", "update", "remove"} <= _command_names(skill_app)
    assert {"run", "restart", "status"} <= _command_names(service_app)
    assert {"policy", "configure"} <= _command_names(agent_app)
    assert {
        "task_next",
        "task_stage_delegate",
        "task_implementation_complete",
        "task_review_complete",
        "task_fix_complete",
        "task_worker_disconnected",
        "task_worker_heartbeat",
        "verification_run",
        "skill_get",
        "memory_context",
    } <= set(TOOL_HANDLERS)
