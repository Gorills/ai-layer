from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_layer.application.action_state import OPEN_TASK_STATUSES as _OPEN_TASK_STATUSES
from ai_layer.application.action_state import (
    ActionProtocolError,
    _finished_response,
    _protocol_error,
    _state_response,
    _upsert_action_state,
    action_debug_snapshot,
    action_token_shape_valid,
    report_fingerprint,
)
from ai_layer.application.action_state import latest_outcome_task as _latest_outcome_task
from ai_layer.application.action_state import report_checks as _report_checks
from ai_layer.application.managed_action import managed_action as _managed_action
from ai_layer.application.work_relations import bind_task_work, task_work_binding
from ai_layer.db.action_models import WorkActionState, WorkActionSubmission
from ai_layer.db.models import Project, Task, TaskStage, utcnow
from ai_layer.db.work_models import WorkItem
from ai_layer.tasks.service import adopt_task, cancel_task, complete_stage, create_task, resume_task
from ai_layer.work.service import finish_work, work_key
from ai_layer.workspace.repository import git_changed_paths

__all__ = (
    "ActionProtocolError",
    "action_debug_snapshot",
    "action_token_shape_valid",
    "attach_reviewed_assurance",
    "continue_action",
    "current_action",
    "finish_action",
    "report_fingerprint",
)


def current_action(db: Session, project: Project, work: WorkItem) -> dict:
    """Return the durable current public action, deriving it from authoritative Task state when needed."""
    if work.project_id != project.id:
        raise ValueError("Work belongs to another project")
    if work.status not in {"active", "blocked"}:
        return _finished_response(db, project, work)
    task = _latest_outcome_task(db, work)
    if task is not None:
        response = _managed_action(db, project, work, task)
        db.commit()
        return response

    state = db.get(WorkActionState, work.id)
    if (
        state is not None
        and state.task_id is None
        and state.action_kind
        in {
            "native_engineering",
            "human_decision",
            "done",
        }
    ):
        return _state_response(db, project, work, state)
    state_version = int(state.state_version) + 1 if state is not None else 1
    state = _upsert_action_state(
        db,
        project,
        work,
        task=None,
        stage=None,
        kind="native_engineering",
        worker_kind=None,
        worker_id="",
        state_version=state_version,
        instruction="Use native repository tools to implement and verify the requested outcome.",
    )
    db.commit()
    return _state_response(db, project, work, state)


def _safe_dirty_worktree(project: Project) -> bool:
    try:
        changes = git_changed_paths(Path(project.root_path).expanduser().resolve())
    except RuntimeError:
        _protocol_error(
            "REPOSITORY_STATE_UNAVAILABLE",
            "cannot safely choose clean vs dirty assurance promotion while Git state is unavailable",
        )
    return bool(int(changes.get("total") or 0))


def _open_project_task(db: Session, project: Project) -> Task | None:
    return db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status.in_(_OPEN_TASK_STATUSES))
        .order_by(Task.updated_at.desc())
        .limit(1)
    )


def _recover_claimed_unbound_open_task(
    db: Session, project: Project, work: WorkItem
) -> Task | None:
    """Recover only an orphan Task proven to belong to this Work by a durable submission."""
    task = _open_project_task(db, project)
    if task is None:
        return None
    binding = task_work_binding(db, task)
    if binding is not None:
        return task if binding.work.id == work.id and binding.role == "outcome" else None
    if str(task.goal).strip() != str(work.goal).strip():
        return None
    bind_task_work(db, project, task, work, role="outcome")
    db.commit()
    return task


def attach_reviewed_assurance(
    db: Session,
    project: Project,
    work: WorkItem,
    *,
    acceptance_criteria: list[str] | None = None,
    constraints: list[str] | None = None,
) -> dict:
    """Attach managed STANDARD assurance to the same Work, using adoption only for a dirty tree."""
    if work.project_id != project.id:
        raise ValueError("Work belongs to another project")
    if work.status not in {"active", "blocked"}:
        raise RuntimeError("cannot attach managed assurance to terminal Work")
    existing = _latest_outcome_task(db, work)
    if existing is not None:
        return current_action(db, project, work)

    open_task = _open_project_task(db, project)
    if open_task is not None:
        binding = task_work_binding(db, open_task)
        if binding is None or binding.work.id != work.id or binding.role != "outcome":
            _protocol_error(
                "OPEN_MANAGED_TASK_CONFLICT",
                "another managed Task is already open for this project",
            )
        return current_action(db, project, work)

    criteria = list(acceptance_criteria or [])
    limits = list(constraints or [])
    if _safe_dirty_worktree(project):
        created = adopt_task(
            db,
            project,
            goal=work.goal,
            acceptance_criteria=criteria,
            constraints=limits,
        )
    else:
        created = create_task(
            db,
            project,
            goal=work.goal,
            acceptance_criteria=criteria,
            constraints=limits,
            workflow="standard",
            risk="auto",
            complexity="auto",
            uncertainty="auto",
            cost_policy="auto",
        )
    task = db.get(Task, UUID(str(created["id"])))
    if task is None:
        raise RuntimeError("managed Task creation did not persist its Task")
    bind_task_work(db, project, task, work, role="outcome")
    db.commit()
    return current_action(db, project, work)


def _submission_for_token(
    db: Session, token: str, *, lock: bool = False
) -> WorkActionSubmission | None:
    stmt = select(WorkActionSubmission).where(WorkActionSubmission.action_token == token)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _state_for_token(db: Session, token: str, *, lock: bool = False) -> WorkActionState | None:
    stmt = select(WorkActionState).where(WorkActionState.action_token == token)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _complete_submission(db: Session, submission: WorkActionSubmission, response: dict) -> dict:
    submission.status = "completed"
    submission.response = response
    submission.updated_at = utcnow()
    db.commit()
    return response


def _submission_replay_or_conflict(
    db: Session,
    submission: WorkActionSubmission,
    fingerprint: str,
) -> dict | None:
    if submission.report_fingerprint != fingerprint:
        _protocol_error(
            "IDEMPOTENCY_CONFLICT",
            "this action token was already submitted with different canonical content",
        )
    if submission.status == "completed":
        return dict(submission.response or {})
    return None


def _recover_processing_submission(
    db: Session,
    submission: WorkActionSubmission,
    fingerprint: str,
) -> dict | None:
    replay = _submission_replay_or_conflict(db, submission, fingerprint)
    if replay is not None:
        return replay
    work = db.get(WorkItem, submission.work_id)
    if work is None:
        _protocol_error("STALE_ACTION", "the Work for this token no longer exists")
    project = db.get(Project, work.project_id)
    if project is None:
        _protocol_error("STALE_ACTION", "the project for this token no longer exists")

    task = _latest_outcome_task(db, work)
    if task is None:
        recovered = _recover_claimed_unbound_open_task(db, project, work)
        if recovered is not None:
            response = current_action(db, project, work)
            return _complete_submission(db, submission, response)
        task = None
    if task is not None and int(task.version or 1) != int(submission.state_version):
        response = current_action(db, project, work)
        return _complete_submission(db, submission, response)

    state = db.get(WorkActionState, work.id)
    if state is not None and state.action_token != submission.action_token:
        return _complete_submission(db, submission, _state_response(db, project, work, state))
    _protocol_error(
        "ACTION_IN_PROGRESS",
        "an identical delivery already claimed this action token; retry after the current transition completes",
    )


def _claim_submission(
    db: Session,
    state: WorkActionState,
    fingerprint: str,
) -> WorkActionSubmission:
    submission = WorkActionSubmission(
        work_id=state.work_id,
        action_token=state.action_token,
        state_version=int(state.state_version),
        report_fingerprint=fingerprint,
        status="processing",
    )
    db.add(submission)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _submission_for_token(db, state.action_token, lock=True)
        if existing is None:
            raise
        recovered = _recover_processing_submission(db, existing, fingerprint)
        if recovered is not None:
            raise _ReplayResponse(recovered) from None
        raise AssertionError("unreachable") from None
    return submission


class _ReplayResponse(Exception):
    def __init__(self, response: dict):
        super().__init__("idempotent replay")
        self.response = response


def _release_failed_claim_if_safe(db: Session, token: str, original_version: int) -> None:
    db.rollback()
    submission = _submission_for_token(db, token, lock=True)
    if submission is None or submission.status == "completed":
        return
    work = db.get(WorkItem, submission.work_id)
    task = _latest_outcome_task(db, work) if work is not None else None
    if task is not None and int(task.version or 1) != int(original_version):
        return
    db.delete(submission)
    db.commit()


def _complete_worker_action(
    db: Session,
    project: Project,
    work: WorkItem,
    state: WorkActionState,
    report: Mapping[str, Any],
) -> dict:
    if str(report.get("kind") or "") != "worker_result":
        _protocol_error("REPORT_KIND_MISMATCH", "run_worker requires report.kind=worker_result")
    task = db.get(Task, state.task_id) if state.task_id else None
    stage = db.get(TaskStage, state.stage_id) if state.stage_id else None
    if task is None or stage is None:
        _protocol_error(
            "STALE_ACTION", "the managed Task/stage bound to this action is unavailable"
        )
    if task.status != "active" or stage.status != "active":
        _protocol_error(
            "STALE_ACTION", "the managed stage already advanced; refresh current action"
        )
    if stage.worker_id != state.worker_id:
        _protocol_error("STALE_ACTION", "the active worker binding no longer matches this action")

    kwargs: dict[str, Any] = {
        "stage_id": str(stage.id),
        "worker_id": state.worker_id,
        "summary": str(report.get("summary") or ""),
        "checks": _report_checks(report),
        "outcome": str(report.get("outcome") or "done"),
        "expected_version": int(state.state_version),
    }
    for key in ("verdict", "findings", "verification_results", "external_actions", "result_data"):
        if key in report:
            kwargs[key] = report[key]
    complete_stage(db, project, **kwargs)
    refreshed_task = db.get(Task, task.id)
    if refreshed_task is None:
        raise RuntimeError("managed Task disappeared after completion")
    return _managed_action(db, project, work, refreshed_task)


def _handle_human_decision(
    db: Session,
    project: Project,
    work: WorkItem,
    state: WorkActionState,
    report: Mapping[str, Any],
) -> dict:
    if str(report.get("kind") or "") != "human_choice":
        _protocol_error("REPORT_KIND_MISMATCH", "human_decision requires report.kind=human_choice")
    task = db.get(Task, state.task_id) if state.task_id else None
    selection = str(report.get("selection") or "").strip().casefold()
    if task is None:
        if selection == "resume":
            next_state = _upsert_action_state(
                db,
                project,
                work,
                task=None,
                stage=None,
                kind="native_engineering",
                worker_kind=None,
                worker_id="",
                state_version=int(state.state_version) + 1,
                instruction="Resume native repository engineering from the current Work state.",
            )
            return _state_response(db, project, work, next_state)
        if selection == "cancel":
            next_state = _upsert_action_state(
                db,
                project,
                work,
                task=None,
                stage=None,
                kind="done",
                worker_kind=None,
                worker_id="",
                state_version=int(state.state_version) + 1,
                instruction="Native work was cancelled; close the durable Work with the appropriate status.",
            )
            return _state_response(db, project, work, next_state)
        _protocol_error("INVALID_HUMAN_CHOICE", "selection must be resume or cancel")
    if selection == "resume":
        resume_task(db, project, expected_version=int(state.state_version))
        task = db.get(Task, task.id)
        if task is None:
            raise RuntimeError("managed Task disappeared after resume")
        return _managed_action(db, project, work, task)
    if selection == "cancel":
        cancel_task(
            db,
            project,
            reason=str(report.get("summary") or "Cancelled through facade human decision."),
            expected_version=int(state.state_version),
        )
        task = db.get(Task, task.id)
        if task is None:
            raise RuntimeError("managed Task disappeared after cancellation")
        return _managed_action(db, project, work, task)
    _protocol_error("INVALID_HUMAN_CHOICE", "selection must be resume or cancel")


def _advance_native_action(
    db: Session,
    project: Project,
    work: WorkItem,
    state: WorkActionState,
    report: Mapping[str, Any],
) -> dict:
    kind = str(report.get("kind") or "")
    outcome = str(report.get("outcome") or "").strip().casefold()
    if kind == "assurance_request" or outcome == "escalate":
        return attach_reviewed_assurance(db, project, work)
    if kind != "native_result":
        _protocol_error(
            "REPORT_KIND_MISMATCH",
            "native_engineering requires native_result or assurance_request",
        )
    next_kind = "human_decision" if outcome == "blocked" else "done"
    instruction = (
        str(report.get("summary") or "Native engineering is blocked; choose how to continue.")
        if next_kind == "human_decision"
        else "Native engineering is complete; record the durable Work outcome."
    )
    next_state = _upsert_action_state(
        db,
        project,
        work,
        task=None,
        stage=None,
        kind=next_kind,
        worker_kind=None,
        worker_id="",
        state_version=int(state.state_version) + 1,
        instruction=instruction,
        payload={"choices": ["resume", "cancel"]} if next_kind == "human_decision" else {},
    )
    return _state_response(db, project, work, next_state)


def continue_action(db: Session, *, action_token: str, report: Mapping[str, Any]) -> dict:
    """Consume one public action token exactly once and return the next server-owned action."""
    token = str(action_token or "")
    if not action_token_shape_valid(token):
        _protocol_error("INVALID_ACTION_TOKEN", "action token is malformed")
    fingerprint = report_fingerprint(report)
    existing = _submission_for_token(db, token, lock=True)
    if existing is not None:
        recovered = _recover_processing_submission(db, existing, fingerprint)
        if recovered is not None:
            return recovered

    state = _state_for_token(db, token, lock=True)
    if state is None:
        _protocol_error(
            "STALE_ACTION",
            "action token is no longer current; refresh with project_enter(intent=resume)",
        )
    work = db.get(WorkItem, state.work_id)
    project = db.get(Project, state.project_id)
    if work is None or project is None:
        _protocol_error("STALE_ACTION", "action token points to unavailable durable state")
    if work.status not in {"active", "blocked"}:
        _protocol_error("STALE_ACTION", "Work is already terminal")

    try:
        submission = _claim_submission(db, state, fingerprint)
    except _ReplayResponse as replay:
        return replay.response
    original_version = int(state.state_version)
    try:
        if state.action_kind == "native_engineering":
            response = _advance_native_action(db, project, work, state, report)
        elif state.action_kind == "run_worker":
            response = _complete_worker_action(db, project, work, state, report)
        elif state.action_kind == "human_decision":
            response = _handle_human_decision(db, project, work, state, report)
        else:
            _protocol_error(
                "ACTION_REQUIRES_FINISH",
                "done actions are consumed by work_finish, not work_continue",
            )
    except Exception:
        _release_failed_claim_if_safe(db, token, original_version)
        raise

    submission = _submission_for_token(db, token, lock=True) or submission
    return _complete_submission(db, submission, response)


def finish_action(
    db: Session,
    *,
    action_token: str,
    summary: str,
    status: str = "completed",
    verification: list[str] | None = None,
    map_disposition: dict | None = None,
) -> dict:
    """Consume a terminal done token and close Work; replay is durable and side-effect free."""
    token = str(action_token or "")
    if not action_token_shape_valid(token):
        _protocol_error("INVALID_ACTION_TOKEN", "action token is malformed")
    report = {
        "kind": "finish",
        "summary": str(summary or ""),
        "status": str(status or "completed"),
        "verification": list(verification or []),
        "map_disposition": dict(map_disposition or {}),
    }
    fingerprint = report_fingerprint(report)
    existing = _submission_for_token(db, token, lock=True)
    if existing is not None:
        replay = _submission_replay_or_conflict(db, existing, fingerprint)
        if replay is not None:
            return replay
        _protocol_error("ACTION_IN_PROGRESS", "terminal Work closure is already in progress")

    state = _state_for_token(db, token, lock=True)
    if state is None:
        _protocol_error("STALE_ACTION", "done token is no longer current")
    if state.action_kind != "done":
        _protocol_error(
            "MANAGED_BOUNDARY_NOT_COMPLETE", "Work cannot finish before the server returns done"
        )
    work = db.get(WorkItem, state.work_id)
    project = db.get(Project, state.project_id)
    if work is None or project is None:
        _protocol_error("STALE_ACTION", "done token points to unavailable durable state")

    try:
        submission = _claim_submission(db, state, fingerprint)
    except _ReplayResponse as replay:
        return replay.response
    try:
        task = _latest_outcome_task(db, work)
        if task is not None and task.status not in {"completed", "cancelled"}:
            _protocol_error(
                "MANAGED_BOUNDARY_NOT_COMPLETE",
                "managed assurance is not terminal; Work closure is forbidden",
            )
        checks = [
            {"name": item, "status": "reported", "summary": item} for item in verification or []
        ]
        work_status = "abandoned" if str(status).strip().casefold() == "cancelled" else status
        finish_work(
            db,
            project,
            work_key_value=work_key(work),
            status=work_status,
            summary=summary,
            checks=checks if checks else None,
            map_disposition=map_disposition,
        )
        db.delete(state)
        response = _finished_response(db, project, work)
        submission = _submission_for_token(db, token, lock=True) or submission
        submission.status = "completed"
        submission.response = response
        submission.updated_at = utcnow()
        db.commit()
        return response
    except Exception:
        _release_failed_claim_if_safe(db, token, int(state.state_version))
        raise
