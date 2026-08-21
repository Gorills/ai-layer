from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.application.action_engine import (
    ActionProtocolError,
    action_debug_snapshot,
    action_token_shape_valid,
    attach_reviewed_assurance,
    continue_action,
    current_action,
    finish_action,
)
from ai_layer.db.action_models import WorkActionState, WorkActionSubmission
from ai_layer.db.base import Base
from ai_layer.db.models import Project, ReviewFinding, Task, TaskStage
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import TaskWorkRelation
from ai_layer.tasks.service import create_task
from ai_layer.work.service import begin_work


def _engine_project(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="phase3",
            root_path=str(root),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
            project_intelligence={"legacy": {"level": "low", "score": 0, "signals": []}},
        )
        db.add(project)
        db.commit()
        project_id = project.id
    return engine, project_id, root


def _rows(engine, project_id):
    db = Session(engine, expire_on_commit=False)
    project = db.get(Project, project_id)
    assert project is not None
    return db, project


def _native_work(db: Session, project: Project, *, goal: str = "Change application behavior"):
    work, run = begin_work(db, project, goal=goal, observability_coverage="control_plane_only")
    db.commit()
    return work, run


def _init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "AI Layer Tests"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)


def _promote(db: Session, project: Project, work: WorkItem) -> tuple[str, dict]:
    native = current_action(db, project, work)
    token = native["next_action"]["action_token"]
    assert token is not None
    reviewed = continue_action(
        db,
        action_token=token,
        report={
            "kind": "assurance_request",
            "summary": "Use reviewed STANDARD assurance",
            "outcome": "escalate",
        },
    )
    return token, reviewed


def test_standard_facade_actions_implement_review_finish_without_fsm_navigation(
    tmp_path: Path,
) -> None:
    engine, project_id, root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    try:
        work, run = _native_work(db, project)
        native_token, implement = _promote(db, project, work)
        action = implement["next_action"]
        assert action["kind"] == "run_worker"
        assert action["worker_kind"] == "change"
        assert action_token_shape_valid(action["action_token"])
        assert str(project.id) not in action["action_token"]
        assert str(work.id) not in action["action_token"]
        assert "stage_id" not in action["worker"]
        assert "task" not in action["worker"]
        assert action["worker"]["worker_id"].startswith("facade-")

        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        implement_report = {
            "kind": "worker_result",
            "summary": "Implemented the requested change",
            "checks": ["focused implementation check"],
            "outcome": "done",
        }
        review = continue_action(db, action_token=action["action_token"], report=implement_report)
        review_action = review["next_action"]
        assert review_action["kind"] == "run_worker"
        assert review_action["worker_kind"] == "independent_check"
        assert review_action["worker"]["repository_mode"] == "read-only"

        duplicate = continue_action(
            db, action_token=action["action_token"], report=implement_report
        )
        assert duplicate == review
        with pytest.raises(ActionProtocolError, match="IDEMPOTENCY_CONFLICT"):
            continue_action(
                db,
                action_token=action["action_token"],
                report={**implement_report, "summary": "different delivery"},
            )

        done = continue_action(
            db,
            action_token=review_action["action_token"],
            report={
                "kind": "worker_result",
                "summary": "Independent review passed",
                "checks": ["review inspection"],
                "verdict": "pass",
            },
        )
        done_action = done["next_action"]
        assert done_action["kind"] == "done"
        task = db.scalar(
            select(Task)
            .join(TaskWorkRelation, TaskWorkRelation.task_id == Task.id)
            .where(TaskWorkRelation.work_id == work.id, TaskWorkRelation.role == "outcome")
        )
        assert task is not None and task.status == "completed"
        assert (
            db.scalar(
                select(func.count()).select_from(TaskStage).where(TaskStage.task_id == task.id)
            )
            == 2
        )

        with pytest.raises(ActionProtocolError, match="ACTION_REQUIRES_FINISH"):
            continue_action(
                db,
                action_token=done_action["action_token"],
                report={"kind": "native_result", "summary": "try to bypass finish"},
            )

        finished = finish_action(
            db,
            action_token=done_action["action_token"],
            summary="Completed and independently reviewed",
            verification=["focused implementation check", "review inspection"],
            map_disposition={"status": "not_applicable", "reason": "No navigation change"},
        )
        assert finished["next_action"]["kind"] == "done"
        assert finished["next_action"]["action_token"] is None
        db.refresh(work)
        db.refresh(run)
        assert work.status == "completed"
        assert run.status == "completed"
        assert db.get(WorkActionState, work.id) is None
        assert db.scalar(select(func.count()).select_from(WorkActionSubmission)) == 4

        finish_replay = finish_action(
            db,
            action_token=done_action["action_token"],
            summary="Completed and independently reviewed",
            verification=["focused implementation check", "review inspection"],
            map_disposition={"status": "not_applicable", "reason": "No navigation change"},
        )
        assert finish_replay == finished
        assert action_token_shape_valid(native_token)
    finally:
        db.close()


def test_review_fix_review_loop_preserves_structured_findings_and_verification(
    tmp_path: Path,
) -> None:
    engine, project_id, root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    try:
        work, _run = _native_work(db, project)
        _native_token, implement = _promote(db, project, work)
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        review = continue_action(
            db,
            action_token=implement["next_action"]["action_token"],
            report={
                "kind": "worker_result",
                "summary": "Implementation complete",
                "checks": ["implementation check"],
            },
        )
        fix = continue_action(
            db,
            action_token=review["next_action"]["action_token"],
            report={
                "kind": "worker_result",
                "summary": "One correctness issue remains",
                "checks": ["read-only inspection"],
                "verdict": "changes_required",
                "findings": [
                    {
                        "severity": "medium",
                        "category": "code",
                        "path": "app.py",
                        "problem": "VALUE must be 3 for the accepted behavior.",
                        "required_fix": "Set VALUE to 3.",
                    }
                ],
            },
        )
        assert fix["next_action"]["worker_kind"] == "correction"
        assert len(fix["next_action"]["worker"]["open_findings"]) == 1
        finding_id = fix["next_action"]["worker"]["open_findings"][0]["id"]

        (root / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        re_review = continue_action(
            db,
            action_token=fix["next_action"]["action_token"],
            report={
                "kind": "worker_result",
                "summary": "Corrected the finding",
                "checks": ["focused correction check"],
                "outcome": "done",
            },
        )
        assert re_review["next_action"]["worker_kind"] == "independent_check"
        verify_items = re_review["next_action"]["worker"]["findings_to_verify"]
        assert [item["id"] for item in verify_items] == [finding_id]

        done = continue_action(
            db,
            action_token=re_review["next_action"]["action_token"],
            report={
                "kind": "worker_result",
                "summary": "Correction verified independently",
                "checks": ["review inspection"],
                "verdict": "pass",
                "verification_results": [
                    {
                        "finding_id": finding_id,
                        "status": "verified",
                        "evidence": "app.py now contains VALUE = 3",
                    }
                ],
            },
        )
        assert done["next_action"]["kind"] == "done"
        finding = db.get(ReviewFinding, UUID(finding_id))
        assert finding is not None and finding.status == "verified"
        task = db.get(Task, finding.task_id)
        assert task is not None and task.status == "completed"
        assert [
            row.kind
            for row in db.scalars(
                select(TaskStage).where(TaskStage.task_id == task.id).order_by(TaskStage.ordinal)
            ).all()
        ] == ["implement", "review", "fix", "review"]
    finally:
        db.close()


def test_worker_block_resume_binds_fresh_worker_and_cannot_skip_managed_boundary(
    tmp_path: Path,
) -> None:
    engine, project_id, _root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    try:
        work, _run = _native_work(db, project)
        _native_token, implement = _promote(db, project, work)
        first_worker = implement["next_action"]["worker"]["worker_id"]
        blocked = continue_action(
            db,
            action_token=implement["next_action"]["action_token"],
            report={
                "kind": "worker_result",
                "summary": "Worker disconnected before producing changes",
                "outcome": "blocked",
            },
        )
        decision = blocked["next_action"]
        assert decision["kind"] == "human_decision"
        assert decision["choices"] == ["resume", "cancel"]
        with pytest.raises(ActionProtocolError, match="MANAGED_BOUNDARY_NOT_COMPLETE"):
            finish_action(
                db,
                action_token=decision["action_token"],
                summary="must not close here",
            )

        resumed = continue_action(
            db,
            action_token=decision["action_token"],
            report={
                "kind": "human_choice",
                "summary": "Retry with a fresh worker",
                "selection": "resume",
            },
        )
        assert resumed["next_action"]["kind"] == "run_worker"
        assert resumed["next_action"]["worker"]["worker_id"] != first_worker
        assert resumed["next_action"]["state_version"] > decision["state_version"]
    finally:
        db.close()


def test_restart_reuses_same_current_token_and_external_advance_makes_old_token_stale(
    tmp_path: Path,
) -> None:
    engine, project_id, _root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    work, _run = _native_work(db, project)
    work_id = work.id
    first = current_action(db, project, work)
    token = first["next_action"]["action_token"]
    db.close()

    db2, project2 = _rows(engine, project_id)
    try:
        work2 = db2.get(WorkItem, work_id)
        assert work2 is not None
        resumed = current_action(db2, project2, work2)
        assert resumed["next_action"]["action_token"] == token

        attach_reviewed_assurance(db2, project2, work2)
        with pytest.raises(ActionProtocolError, match="STALE_ACTION"):
            continue_action(
                db2,
                action_token=token,
                report={"kind": "native_result", "summary": "stale transcript result"},
            )
    finally:
        db2.close()


def test_dirty_native_promotion_adopts_same_work_and_starts_with_independent_review(
    tmp_path: Path,
) -> None:
    engine, project_id, root = _engine_project(tmp_path)
    _init_git(root)
    db, project = _rows(engine, project_id)
    try:
        work, _run = _native_work(db, project, goal="Adopt the existing implementation")
        current_action(db, project, work)
        (root / "app.py").write_text("VALUE = 9\n", encoding="utf-8")
        promoted = continue_action(
            db,
            action_token=db.get(WorkActionState, work.id).action_token,
            report={
                "kind": "assurance_request",
                "summary": "Review the existing dirty implementation",
                "outcome": "escalate",
            },
        )
        assert promoted["work"]["key"] == "W-0001"
        assert promoted["next_action"]["worker_kind"] == "independent_check"
        relation = db.scalar(
            select(TaskWorkRelation).where(
                TaskWorkRelation.work_id == work.id, TaskWorkRelation.role == "outcome"
            )
        )
        assert relation is not None
        task = db.get(Task, relation.task_id)
        assert task is not None
        assert task.execution_origin == "adopted_unmanaged_changes"
        assert int((task.adopted_changes or {}).get("total") or 0) == 1
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 1
    finally:
        db.close()


def test_action_debug_snapshot_does_not_expose_action_token(tmp_path: Path) -> None:
    engine, project_id, _root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    try:
        work, _run = _native_work(db, project)
        response = current_action(db, project, work)
        snapshot = action_debug_snapshot(db, work)
        assert response["next_action"]["action_token"] not in repr(snapshot)
        assert snapshot["action"]["kind"] == "native_engineering"
    finally:
        db.close()


def test_promotion_fails_closed_when_git_state_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, project_id, _root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    try:
        work, _run = _native_work(db, project)
        initial = current_action(db, project, work)
        token = initial["next_action"]["action_token"]

        def unavailable(_root: Path) -> dict:
            raise RuntimeError("git state unavailable")

        monkeypatch.setattr(
            "ai_layer.application.action_engine.git_changed_paths",
            unavailable,
        )
        with pytest.raises(ActionProtocolError, match="REPOSITORY_STATE_UNAVAILABLE"):
            continue_action(
                db,
                action_token=token,
                report={
                    "kind": "assurance_request",
                    "summary": "Require reviewed assurance",
                    "outcome": "escalate",
                },
            )

        assert db.scalar(select(func.count()).select_from(Task)) == 0
        state = db.get(WorkActionState, work.id)
        assert state is not None and state.action_token == token
        assert db.scalar(select(func.count()).select_from(WorkActionSubmission)) == 0
    finally:
        db.close()


def test_unbound_same_goal_task_is_not_silently_claimed_by_work(tmp_path: Path) -> None:
    engine, project_id, _root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    try:
        work, _run = _native_work(db, project, goal="Repeated goal")
        create_task(
            db,
            project,
            goal="Repeated goal",
            acceptance_criteria=[],
            constraints=[],
            workflow="standard",
        )
        with pytest.raises(ActionProtocolError, match="OPEN_MANAGED_TASK_CONFLICT"):
            attach_reviewed_assurance(db, project, work)
        assert db.scalar(select(func.count()).select_from(TaskWorkRelation)) == 0
    finally:
        db.close()


def test_claimed_native_promotion_recovers_crash_between_task_create_and_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_layer.application.action_engine as action_engine

    engine, project_id, _root = _engine_project(tmp_path)
    db, project = _rows(engine, project_id)
    work, _run = _native_work(db, project, goal="Crash-safe promotion")
    work_id = work.id
    initial = current_action(db, project, work)
    token = initial["next_action"]["action_token"]
    report = {
        "kind": "assurance_request",
        "summary": "Require reviewed assurance",
        "outcome": "escalate",
    }
    original_bind = action_engine.bind_task_work
    crashed = False

    def crash_once(*args, **kwargs):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise SystemExit("simulated process crash after Task creation")
        return original_bind(*args, **kwargs)

    monkeypatch.setattr(action_engine, "bind_task_work", crash_once)
    with pytest.raises(SystemExit, match="simulated process crash"):
        continue_action(db, action_token=token, report=report)
    db.close()

    monkeypatch.setattr(action_engine, "bind_task_work", original_bind)
    db2, project2 = _rows(engine, project_id)
    try:
        recovered = continue_action(db2, action_token=token, report=report)
        assert recovered["next_action"]["kind"] == "run_worker"
        relation = db2.scalar(select(TaskWorkRelation).where(TaskWorkRelation.work_id == work_id))
        assert relation is not None and relation.role == "outcome"
        submission = db2.scalar(
            select(WorkActionSubmission).where(WorkActionSubmission.action_token == token)
        )
        assert submission is not None and submission.status == "completed"
    finally:
        db2.close()
