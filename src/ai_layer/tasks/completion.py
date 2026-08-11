from __future__ import annotations

import shutil
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.core.filelock import directory_lock
from ai_layer.db.models import Project, ReviewFinding, Task, TaskStage, utcnow
from ai_layer.privacy.service import privacy_check
from ai_layer.observability.domain_events import append_event
from ai_layer.sessions.service import save_session
from ai_layer.tasks.concurrency import assert_expected_version, bump_task_version
from ai_layer.tasks.constants import (
    HIGH_RISK_TERMS,
    HUMAN_ATTENTION_PREFIX,
    MAX_AUTOMATIC_FIX_ROUNDS,
    MAX_STAGE_CHECKS,
    MAX_STAGE_CHECK_CHARS,
    MAX_STAGE_SUMMARY_CHARS,
    READ_ONLY_STAGES,
    TERMINAL_TASK_STATUSES,
)
from ai_layer.tasks.contracts import (
    _bounded_result_data,
    _bounded_text,
    _bounded_text_list,
    _contains_any,
)
from ai_layer.tasks.review_contracts import (
    _add_findings,
    _apply_verification_results,
    _normalize_external_actions,
    _normalize_review_submission,
    _normalize_verification_results,
    _open_findings,
)
from ai_layer.tasks.micro_policy import micro_envelope as _micro_envelope
from ai_layer.tasks.state_store import (
    load_stage_start as _load_stage_start,
    materialize_stage_start,
    task_key,
    task_lock as _task_lock,
    task_work_dir as _task_work_dir,
)
from ai_layer.workspace.repository import capture_repository_state, repository_changes
from ai_layer.tasks.review_checks import (
    evidence_check_strings,
    latest_review_check_evidence,
    review_check_evidence,
)
from ai_layer.tasks.review_workspace import cleanup_review_sandbox
from ai_layer.tasks.stage_validation import _validate_stage_result
from ai_layer.tasks.transitions import (
    _advance_discovery,
    _advance_fix,
    _advance_implement,
    _advance_review,
)
from ai_layer.tasks.views import (
    _active_stage,
    _completion_contract,
    _create_stage,
    _finding_payload,
    _findings,
    _persist_task_view,
    _remediation_fix_count,
    _stage_label,
    _stages,
    _validate_worker_id,
)


def _record_stage_evidence(
    stage: TaskStage,
    *,
    worker: str,
    summary: str,
    checks: list[str],
    external_actions: list[dict],
    changes: dict,
    result_data: dict,
    current_state: dict,
) -> None:
    stage.worker_id = worker
    stage.summary = summary
    stage.checks = checks
    stage.external_actions = external_actions
    stage.changes = changes
    stage.result_data = result_data
    stage.repository_digest_after = str(current_state.get("digest") or "")
    stage.completed_at = utcnow()


def _block_stage(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    outcome: str,
    reason: str,
    cleanup_sandbox: bool = False,
) -> dict:
    stage.status = "blocked" if outcome == "blocked" else "invalid"
    stage.outcome = outcome
    task.status = "blocked"
    task.blocked_reason = reason
    bump_task_version(task)
    task.updated_at = utcnow()
    append_event(
        db,
        event_type="StageInvalidated",
        project=project,
        aggregate_type="task_stage",
        aggregate_id=str(stage.id),
        payload={
            "task_id": str(task.id),
            "kind": stage.kind,
            "outcome": outcome,
            "reason": reason[:1000],
        },
    )
    append_event(
        db,
        event_type="TaskBlocked",
        project=project,
        aggregate_type="task",
        aggregate_id=str(task.id),
        payload={"stage_id": str(stage.id), "reason": reason[:1000]},
    )
    db.commit()
    payload = _persist_task_view(db, project, task)
    if cleanup_sandbox:
        try:
            cleanup_review_sandbox(project, str(stage.id))
        except (OSError, RuntimeError):
            payload["sandbox_cleanup_warning"] = "Review sandbox cleanup failed."
    return payload


def _normalize_completion_input(
    stage_id: str,
    summary: str,
    checks: list[str],
    outcome: str,
    result_data: dict | None,
) -> tuple[UUID, str, list[str], str, dict]:
    try:
        wanted_stage = UUID(stage_id)
    except ValueError as exc:
        raise ValueError("task_stage_complete: invalid `stage_id`.") from exc
    normalized_summary = _bounded_text(
        summary,
        field="task_stage_complete: `summary`",
        max_chars=MAX_STAGE_SUMMARY_CHARS,
        required=True,
        redact=True,
    )
    normalized_checks = _bounded_text_list(
        checks,
        field="task_stage_complete: `checks`",
        max_items=MAX_STAGE_CHECKS,
        max_chars=MAX_STAGE_CHECK_CHARS,
        redact=True,
    )
    return (
        wanted_stage,
        normalized_summary,
        normalized_checks,
        (outcome or "done").strip().lower(),
        _bounded_result_data(result_data),
    )


def _advance_completed_stage(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    current_state: dict,
    summary: str,
    outcome: str,
    result_data: dict,
    changes: dict,
    external_actions: list[dict],
    verdict: str,
    findings: list[dict],
    pending_to_verify: list[ReviewFinding],
    verification_map: dict[str, dict],
    input_normalizations: list[str],
    open_items: list[ReviewFinding] | None,
) -> TaskStage | None:
    if stage.kind == "discovery":
        return _advance_discovery(
            db,
            project,
            task,
            stage,
            current_state=current_state,
            summary=summary,
            outcome=outcome,
            result_data=result_data,
        )
    if stage.kind == "review":
        return _advance_review(
            db,
            project,
            task,
            stage,
            current_state=current_state,
            summary=summary,
            verdict=verdict,
            findings=findings,
            pending_to_verify=pending_to_verify,
            verification_map=verification_map,
            input_normalizations=input_normalizations,
        )
    if stage.kind == "implement":
        return _advance_implement(
            db,
            project,
            task,
            stage,
            current_state=current_state,
            summary=summary,
            changes=changes,
            external_actions=external_actions,
        )
    assert open_items is not None
    return _advance_fix(
        db, task, stage, current_state=current_state, outcome=outcome, open_items=open_items
    )


def _finalize_completion(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    next_stage: TaskStage | None,
    current_state: dict,
    input_normalizations: list[str],
    normalized_verdict: str,
) -> dict:
    bump_task_version(task)
    task.updated_at = utcnow()
    append_event(
        db,
        event_type="StageCompleted",
        project=project,
        aggregate_type="task_stage",
        aggregate_id=str(stage.id),
        payload={
            "task_id": str(task.id),
            "kind": stage.kind,
            "outcome": stage.outcome,
            "next_stage_id": str(next_stage.id) if next_stage else None,
        },
    )
    if task.status == "blocked":
        append_event(
            db,
            event_type="TaskBlocked",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={"stage_id": str(stage.id), "reason": task.blocked_reason[:1000]},
        )
    elif task.status == "completed":
        append_event(
            db,
            event_type="TaskCompleted",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={"stage_id": str(stage.id), "summary": task.completion_summary[:1000]},
        )
    db.commit()
    if next_stage is not None:
        try:
            materialize_stage_start(db, project, task, next_stage)
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
    payload = _persist_task_view(db, project, task)
    if stage.kind in READ_ONLY_STAGES:
        try:
            cleanup_review_sandbox(project, str(stage.id))
        except (OSError, RuntimeError):
            payload["sandbox_cleanup_warning"] = (
                "Review sandbox cleanup failed; run review_sandbox_cleanup."
            )
    if input_normalizations:
        payload["input_normalizations"] = input_normalizations
        payload["effective_review_verdict"] = normalized_verdict
    if task.status in TERMINAL_TASK_STATUSES:
        shutil.rmtree(_task_work_dir(project, task.id), ignore_errors=True)
    return payload


def complete_stage(
    db: Session,
    project: Project,
    *,
    stage_id: str,
    worker_id: str,
    summary: str,
    checks: list[str],
    outcome: str = "done",
    verdict: str | None = None,
    findings: list[dict] | None = None,
    verification_results: list[dict] | None = None,
    external_actions: list[dict] | None = None,
    result_data: dict | None = None,
    expected_version: int | None = None,
) -> dict:
    wanted_stage, summary, normalized_checks, normalized_outcome, normalized_result_data = (
        _normalize_completion_input(stage_id, summary, checks, outcome, result_data)
    )

    with directory_lock(_task_lock(project), timeout_seconds=15):
        task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status == "active")
            .order_by(Task.updated_at.desc())
            .limit(1)
            .with_for_update()
        )
        if task is None:
            raise RuntimeError("No active task exists for this project.")
        assert_expected_version(task, expected_version)
        stage = _active_stage(db, task)
        if stage is None or stage.id != wanted_stage:
            expected = str(stage.id) if stage else "none"
            raise RuntimeError(
                f"Stage mismatch for {task_key(task)}: active stage is {expected}, received {stage_id}."
            )
        if bool(stage.delegation_required) and not stage.worker_id:
            raise RuntimeError(
                "STAGE_NOT_DELEGATED: this stage requires task_stage_delegate before completion. "
                "Do not attribute repository changes to a worker retroactively."
            )
        worker = stage.worker_id or _validate_worker_id(
            db, task, worker_id, current_stage_id=stage.id
        )
        if stage.worker_id and worker_id.strip() != stage.worker_id:
            raise ValueError(
                f"task_stage_complete: active stage is delegated to `{stage.worker_id}`, "
                f"but completion reported `{worker_id.strip()}`."
            )
        normalized_external_actions = _normalize_external_actions(
            external_actions, stage_kind=stage.kind
        )
        start_state = _load_stage_start(db, project, task, stage)
        current_state = capture_repository_state(project.root_path, previous=start_state)
        changes = repository_changes(start_state, current_state)
        sandbox_evidence = (
            latest_review_check_evidence(review_check_evidence(project, task, stage))
            if stage.kind in READ_ONLY_STAGES
            else []
        )
        normalized_checks = [*normalized_checks, *evidence_check_strings(sandbox_evidence)]
        evidence = dict(
            worker=worker,
            summary=summary,
            checks=normalized_checks,
            external_actions=normalized_external_actions,
            changes=changes,
            result_data=normalized_result_data,
            current_state=current_state,
        )

        if stage.kind in READ_ONLY_STAGES and changes["total"]:
            _record_stage_evidence(stage, **evidence)
            return _block_stage(
                db,
                project,
                task,
                stage,
                outcome="repository_modified",
                reason=(
                    f"Read-only {stage.kind} worker modified repository files. Restore the repository to the "
                    f"{stage.kind}-stage starting state, then resume the task with a fresh worker."
                ),
                cleanup_sandbox=True,
            )
        open_items = _open_findings(db, task) if stage.kind == "fix" else None
        if stage.kind == "fix" and not open_items and changes["total"]:
            _record_stage_evidence(stage, **evidence)
            return _block_stage(
                db,
                project,
                task,
                stage,
                outcome="unexpected_changes",
                reason=(
                    "Fixer changed repository files even though the preceding review had no findings. "
                    "Inspect/revert those unrelated changes before resuming."
                ),
            )
        if normalized_outcome == "blocked":
            _record_stage_evidence(stage, **evidence)
            return _block_stage(
                db,
                project,
                task,
                stage,
                outcome="blocked",
                reason=summary,
                cleanup_sandbox=stage.kind in READ_ONLY_STAGES,
            )
        if not normalized_checks:
            raise ValueError(
                "Every completed task stage requires at least one verification check "
                "(automated test, static check, or explicit manual inspection)."
            )

        (
            normalized_outcome,
            normalized_verdict,
            normalized_findings,
            input_normalizations,
            pending_to_verify,
            verification_map,
        ) = _validate_stage_result(
            db,
            task,
            stage,
            outcome=normalized_outcome,
            verdict=verdict,
            findings=findings,
            verification_results=verification_results,
            sandbox_evidence=sandbox_evidence,
            open_items=open_items,
        )
        _record_stage_evidence(stage, **evidence)
        next_stage = _advance_completed_stage(
            db,
            project,
            task,
            stage,
            current_state=current_state,
            summary=summary,
            outcome=normalized_outcome,
            result_data=normalized_result_data,
            changes=changes,
            external_actions=normalized_external_actions,
            verdict=normalized_verdict,
            findings=normalized_findings,
            pending_to_verify=pending_to_verify,
            verification_map=verification_map,
            input_normalizations=input_normalizations,
            open_items=open_items,
        )

        return _finalize_completion(
            db,
            project,
            task,
            stage,
            next_stage,
            current_state,
            input_normalizations,
            normalized_verdict,
        )


def complete_current_stage(
    db: Session,
    project: Project,
    *,
    expected_kind: str,
    summary: str,
    checks: list[str],
    outcome: str = "done",
    verdict: str | None = None,
    findings: list[dict] | None = None,
    verification_results: list[dict] | None = None,
    external_actions: list[dict] | None = None,
    result_data: dict | None = None,
    expected_version: int | None = None,
) -> dict:
    """Compact completion path for the currently delegated stage.

    Stage id and worker id are intentionally inferred from durable state so a weak orchestrator
    cannot accidentally complete the wrong stage with stale transcript arguments.
    """
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "active")
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None:
        raise RuntimeError("No active task exists for this project.")
    stage = _active_stage(db, task)
    if stage is None:
        raise RuntimeError(f"Active task {task_key(task)} has no active stage.")
    if stage.kind != expected_kind:
        contract = _completion_contract(
            stage, [_finding_payload(item) for item in _open_findings(db, task)]
        )
        raise RuntimeError(
            f"STAGE_KIND_MISMATCH: active stage is `{stage.kind}`, not `{expected_kind}`. "
            f"Use `{contract['tool']}` as returned by task_next."
        )
    if not stage.worker_id:
        raise RuntimeError(
            "STAGE_NOT_DELEGATED: call task_stage_delegate with a fresh worker_id before recording completion."
        )
    return complete_stage(
        db,
        project,
        stage_id=str(stage.id),
        worker_id=stage.worker_id,
        summary=summary,
        checks=checks,
        outcome=outcome,
        verdict=verdict,
        findings=findings,
        verification_results=verification_results,
        external_actions=external_actions,
        result_data=result_data,
        expected_version=expected_version,
    )
