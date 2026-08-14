from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_layer.application.commands import execute_idempotent
from ai_layer.application.security import decide
from ai_layer.core.request_context import operation_context
from ai_layer.db.base import Base
from ai_layer.db.models import (
    CommandReceipt,
    Project,
    RepositorySnapshot,
    RuntimeEvent,
    Task,
    TaskStage,
)
from ai_layer.domain.security import Actor, Capability
from ai_layer.domain.workflow import STAGE_DEFINITIONS, validate_workflow_registry
from ai_layer.observability.domain_events import append_event
from ai_layer.tasks import service as tasks
from ai_layer.tasks.state_store import task_work_dir


def _db_project(tmp_path: Path) -> tuple[Session, Project, Path]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="demo", root_path=str(root), languages={}, dependencies={}, architecture_summary=""
    )
    db.add(project)
    db.commit()
    return db, project, root


def test_new_task_recovery_state_is_durable_without_filesystem_snapshot(tmp_path: Path) -> None:
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Change value",
            acceptance_criteria=["VALUE becomes 2"],
            constraints=[],
            workflow="standard",
        )
        task = db.get(Task, UUID(created["id"]))
        assert task is not None and task.baseline_snapshot_id is not None
        stage = db.scalar(
            select(TaskStage).where(TaskStage.task_id == task.id, TaskStage.status == "active")
        )
        assert stage is not None and stage.start_snapshot_id is not None
        assert db.get(RepositorySnapshot, task.baseline_snapshot_id) is not None

        shutil.rmtree(task_work_dir(project, task.id), ignore_errors=True)
        delegated = tasks.delegate_current_stage(db, project, worker_id="implementer-durable")
        assert delegated["active_stage"]["worker_id"] == "implementer-durable"

        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        review = tasks.complete_stage(
            db,
            project,
            stage_id=delegated["active_stage"]["id"],
            worker_id="implementer-durable",
            summary="Changed value.",
            checks=["manual check"],
        )
        assert review["active_stage"]["kind"] == "review"
        assert review["active_stage"]["start_snapshot_id"]

        shutil.rmtree(task_work_dir(project, task.id), ignore_errors=True)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-durable")
        completed = tasks.complete_stage(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-durable",
            summary="Review passed.",
            checks=["manual diff inspection"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        assert completed["final_changes"]["modified"] == ["app.py"]
    finally:
        db.close()


def test_projection_failure_after_commit_does_not_lose_canonical_state(
    tmp_path: Path, monkeypatch
) -> None:
    db, project, _ = _db_project(tmp_path)
    import ai_layer.tasks.lifecycle as lifecycle

    monkeypatch.setattr(
        lifecycle,
        "materialize_baseline",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk gone")),
    )
    monkeypatch.setattr(
        lifecycle,
        "materialize_stage_start",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk gone")),
    )
    try:
        created = tasks.create_task(
            db, project, goal="Durable", acceptance_criteria=[], constraints=[]
        )
        task = db.get(Task, UUID(created["id"]))
        assert task is not None
        assert task.baseline_snapshot_id is not None
        assert db.scalar(select(func.count()).select_from(RepositorySnapshot)) >= 1
    finally:
        db.close()


def test_commit_failure_does_not_publish_required_filesystem_state(
    tmp_path: Path, monkeypatch
) -> None:
    db, project, _ = _db_project(tmp_path)
    import ai_layer.tasks.lifecycle as lifecycle

    published = {"count": 0}
    monkeypatch.setattr(
        lifecycle,
        "materialize_baseline",
        lambda *args, **kwargs: published.__setitem__("count", published["count"] + 1),
    )
    monkeypatch.setattr(
        lifecycle,
        "materialize_stage_start",
        lambda *args, **kwargs: published.__setitem__("count", published["count"] + 1),
    )
    real_commit = db.commit

    def fail_commit() -> None:
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(db, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="injected commit failure"):
            tasks.create_task(
                db, project, goal="Crash before commit", acceptance_criteria=[], constraints=[]
            )
        assert published["count"] == 0
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Task)) == 0
        assert db.scalar(select(func.count()).select_from(RepositorySnapshot)) == 0
        assert db.scalar(select(func.count()).select_from(RuntimeEvent)) == 0
    finally:
        monkeypatch.setattr(db, "commit", real_commit)
        db.close()


def test_worker_recovery_uses_database_snapshot_after_local_cache_loss(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Recover worker", acceptance_criteria=[], constraints=[]
        )
        delegated = tasks.delegate_current_stage(db, project, worker_id="lost-worker")
        task_id = UUID(created["id"])
        shutil.rmtree(task_work_dir(project, task_id), ignore_errors=True)
        recovered = tasks.recover_disconnected_worker(db, project, reason="worker process exited")
        assert recovered["status"] == "active"
        assert recovered["active_stage"]["id"] != delegated["active_stage"]["id"]
        assert recovered["active_stage"]["worker_id"] is None
        assert recovered["active_stage"]["start_snapshot_id"]
    finally:
        db.close()


def test_database_prevents_two_open_tasks_even_if_service_guard_is_bypassed(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        first = Task(project_id=project.id, sequence=1, goal="one", status="active")
        db.add(first)
        db.commit()
        db.add(Task(project_id=project.id, sequence=2, goal="two", status="blocked"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Task)) == 1
    finally:
        db.close()


def test_database_prevents_two_active_stages_even_if_service_guard_is_bypassed(
    tmp_path: Path,
) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        task = Task(project_id=project.id, sequence=1, goal="one", status="active")
        db.add(task)
        db.flush()
        db.add(TaskStage(task_id=task.id, ordinal=1, kind="implement", status="active"))
        db.commit()
        db.add(TaskStage(task_id=task.id, ordinal=2, kind="review", status="active"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(TaskStage)) == 1
    finally:
        db.close()


def test_stale_expected_task_version_is_rejected(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Versioned mutation", acceptance_criteria=[], constraints=[]
        )
        assert created["version"] == 1
        with pytest.raises(RuntimeError, match="STALE_TASK_VERSION"):
            tasks.delegate_current_stage(
                db,
                project,
                worker_id="versioned-worker",
                expected_version=99,
            )
        delegated = tasks.delegate_current_stage(
            db,
            project,
            worker_id="versioned-worker",
            expected_version=1,
        )
        assert delegated["version"] == 2
    finally:
        db.close()


def test_workflow_registry_is_complete_and_classifies_every_stage() -> None:
    assert validate_workflow_registry() == []
    assert set(STAGE_DEFINITIONS) == {"discovery", "implement", "review", "fix"}
    for definition in STAGE_DEFINITIONS.values():
        assert definition.role
        assert definition.completion_contract
        assert definition.required_capabilities
        assert definition.readonly is not definition.mutating
        assert definition.allowed_outcomes


def test_capability_policy_denies_unauthenticated_and_missing_permissions() -> None:
    anonymous = Actor("anon", "remote", frozenset({Capability.TASK_READ}), authenticated=False)
    assert not decide(anonymous, Capability.TASK_READ).allowed
    reader = Actor("user:1", "user", frozenset({Capability.TASK_READ}), authenticated=True)
    assert decide(reader, Capability.TASK_READ).allowed
    assert not decide(reader, Capability.SHELL_EXECUTE).allowed
    operator = Actor("user:2", "user", frozenset({Capability.SHELL_EXECUTE}), authenticated=True)
    decision = decide(operator, Capability.SHELL_EXECUTE, require_approval=True)
    assert not decision.allowed and decision.approval_required


def test_event_metadata_is_attributed_from_operation_context(tmp_path: Path) -> None:
    db, project, _ = _db_project(tmp_path)
    actor = Actor("user:42", "user", frozenset({Capability.TASK_CREATE}), authenticated=True)
    try:
        with operation_context(
            actor=actor,
            interface="test",
            correlation_id="corr-42",
            command_id="cmd-42",
        ):
            append_event(
                db,
                event_type="TaskCreated",
                project=project,
                aggregate_type="task",
                aggregate_id="fake",
                payload={"ok": True},
            )
            db.commit()
        row = db.scalar(select(RuntimeEvent))
        assert row is not None
        assert row.correlation_id == "corr-42"
        assert row.actor_id == "user:42"
        assert row.actor_kind == "user"
        assert row.interface == "test"
        assert row.command_id == "cmd-42"
        assert row.schema_version == 2
    finally:
        db.close()


def test_idempotent_command_retry_returns_original_result_without_second_mutation(
    tmp_path: Path,
) -> None:
    db, project, _ = _db_project(tmp_path)
    actor = Actor("user:7", "user", frozenset({Capability.TASK_CREATE}), authenticated=True)
    calls = {"count": 0}

    def handler() -> dict:
        calls["count"] += 1
        return {"created": calls["count"]}

    try:
        first = execute_idempotent(
            db,
            command_id="cmd-once",
            command_name="task.create",
            request={"goal": "one"},
            actor=actor,
            correlation_id="corr-once",
            project_id=project.id,
            handler=handler,
        )
        db.commit()
        second = execute_idempotent(
            db,
            command_id="cmd-once",
            command_name="task.create",
            request={"goal": "one"},
            actor=actor,
            correlation_id="corr-retry",
            project_id=project.id,
            handler=handler,
        )
        assert first == second == {"created": 1}
        assert calls["count"] == 1
        assert db.scalar(select(func.count()).select_from(CommandReceipt)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(RuntimeEvent)
                .where(RuntimeEvent.event_type == "CommandExecuted")
            )
            == 1
        )
        with pytest.raises(RuntimeError, match="IDEMPOTENCY_KEY_REUSED"):
            execute_idempotent(
                db,
                command_id="cmd-once",
                command_name="task.create",
                request={"goal": "different"},
                actor=actor,
                correlation_id="corr-bad",
                project_id=project.id,
                handler=handler,
            )
    finally:
        db.close()


def test_idempotent_command_same_key_does_not_replay_another_project(tmp_path: Path) -> None:
    db, project_a, _ = _db_project(tmp_path)
    actor = Actor("user:7", "user", frozenset({Capability.TASK_CREATE}), authenticated=True)
    other_root = tmp_path / "other"
    other_root.mkdir()
    project_b = Project(
        name="other",
        root_path=str(other_root),
        languages={},
        dependencies={},
        architecture_summary="",
    )
    db.add(project_b)
    db.commit()
    calls = {"count": 0}

    def handler() -> dict:
        calls["count"] += 1
        return {"created": calls["count"]}

    try:
        first = execute_idempotent(
            db,
            command_id="shared-key",
            command_name="work_begin",
            request={"goal": "same"},
            actor=actor,
            correlation_id="corr-a",
            project_id=project_a.id,
            handler=handler,
        )
        db.commit()
        second = execute_idempotent(
            db,
            command_id="shared-key",
            command_name="work_begin",
            request={"goal": "same"},
            actor=actor,
            correlation_id="corr-b",
            project_id=project_b.id,
            handler=handler,
        )
        db.commit()
        assert first == {"created": 1}
        assert second == {"created": 2}
        assert calls["count"] == 2
        assert db.scalar(select(func.count()).select_from(CommandReceipt)) == 2
        other_a = execute_idempotent(
            db,
            command_id="alt-key",
            command_name="work_begin",
            request={"goal": "alpha"},
            actor=actor,
            correlation_id="corr-alt-a",
            project_id=project_a.id,
            handler=handler,
        )
        other_b = execute_idempotent(
            db,
            command_id="alt-key",
            command_name="work_begin",
            request={"goal": "beta"},
            actor=actor,
            correlation_id="corr-alt-b",
            project_id=project_b.id,
            handler=handler,
        )
        db.commit()
        assert other_a == {"created": 3}
        assert other_b == {"created": 4}
        with pytest.raises(RuntimeError, match="IDEMPOTENCY_KEY_REUSED"):
            execute_idempotent(
                db,
                command_id="shared-key",
                command_name="work_begin",
                request={"goal": "changed"},
                actor=actor,
                correlation_id="corr-reuse",
                project_id=project_a.id,
                handler=handler,
            )
    finally:
        db.close()


def test_idempotent_command_replays_pre_project_hash_receipts(tmp_path: Path) -> None:
    from ai_layer.application.commands import _legacy_request_hash

    db, project, _ = _db_project(tmp_path)
    actor = Actor("user:7", "user", frozenset({Capability.TASK_CREATE}), authenticated=True)
    request = {"goal": "legacy"}
    db.add(
        CommandReceipt(
            project_id=project.id,
            command_id="legacy-key",
            command_name="work_begin",
            request_hash=_legacy_request_hash("work_begin", request),
            status="completed",
            result={"work": {"id": "kept"}},
        )
    )
    db.commit()
    calls = {"count": 0}

    def handler() -> dict:
        calls["count"] += 1
        return {"work": {"id": "new"}}

    try:
        replayed = execute_idempotent(
            db,
            command_id="legacy-key",
            command_name="work_begin",
            request=request,
            actor=actor,
            correlation_id="corr-legacy",
            project_id=project.id,
            handler=handler,
        )
        assert replayed == {"work": {"id": "kept"}}
        assert calls["count"] == 0
    finally:
        db.close()
