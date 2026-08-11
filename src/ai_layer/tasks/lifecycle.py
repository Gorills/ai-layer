from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.core.filelock import directory_lock
from ai_layer.db.models import Project, Task, TaskStage, utcnow
from ai_layer.domain.orchestrator import orchestrator_stage_instruction
from ai_layer.agents.policy import load_policy
from ai_layer.observability.domain_events import append_event
from ai_layer.memory.knowledge_store import abandon_task_drafts
from ai_layer.tasks.constants import MAX_TASK_GOAL_CHARS, OPEN_TASK_STATUSES, READ_ONLY_STAGES
from ai_layer.tasks.concurrency import assert_expected_version, bump_task_version, lock_project
from ai_layer.tasks.contracts import _bounded_text, _bounded_text_list, _classify_task
from ai_layer.tasks.navigation import (
    _latest_resumable_stage,
    _safe_git_changes,
)
from ai_layer.tasks.state_store import (
    bind_task_baseline,
    load_stage_start as _load_stage_start,
    materialize_baseline,
    materialize_stage_start,
    memory_hash_seed as _memory_hash_seed,
    task_key,
    task_lock as _task_lock,
    task_work_dir as _task_work_dir,
)
from ai_layer.workspace.repository import (
    git_changed_paths as _git_changed_paths,
    capture_repository_state,
    repository_changes,
)
from ai_layer.tasks.views import (
    _active_stage,
    _cleanup_task_review_sandboxes,
    _create_stage,
    _human_attention_reason,
    _persist_task_view,
    _validate_worker_id,
    task_to_dict,
)
from ai_layer.tasks.worker_leases import recover_disconnected_worker, start_worker_lease


def _materialize_recovery_cache(
    db: Session, project: Project, task: Task, stage: TaskStage | None
) -> None:
    """Best-effort local projection; PostgreSQL remains authoritative."""
    try:
        materialize_baseline(db, project, task)
        if stage is not None:
            materialize_stage_start(db, project, task, stage)
    except (OSError, RuntimeError, TypeError, ValueError):
        return


def create_task(
    db: Session,
    project: Project,
    *,
    goal: str,
    acceptance_criteria: list[str],
    constraints: list[str],
    workflow: str = "auto",
    risk: str = "auto",
    complexity: str = "auto",
    uncertainty: str = "auto",
    cost_policy: str = "auto",
) -> dict:
    goal = _bounded_text(
        goal, field="task_create: `goal`", max_chars=MAX_TASK_GOAL_CHARS, required=True, redact=True
    )
    criteria = _bounded_text_list(
        acceptance_criteria, field="task_create: `acceptance_criteria`", redact=True
    )
    task_constraints = _bounded_text_list(
        constraints, field="task_create: `constraints`", redact=True
    )
    classification = _classify_task(
        project,
        goal=goal,
        acceptance_criteria=criteria,
        constraints=task_constraints,
        workflow=workflow,
        risk=risk,
        complexity=complexity,
        uncertainty=uncertainty,
        cost_policy=cost_policy,
    )
    with directory_lock(_task_lock(project), timeout_seconds=15):
        lock_project(db, project)
        existing = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status.in_(sorted(OPEN_TASK_STATUSES)))
            .limit(1)
        )
        if existing is not None:
            raise RuntimeError(
                f"Project already has active task {task_key(existing)} ({existing.status}). "
                "Sequential execution forbids a second task; continue or cancel the current task."
            )
        dirty = _safe_git_changes(Path(project.root_path).expanduser().resolve()) or {}
        preexisting = dict(dirty) if int(dirty.get("total") or 0) else {}
        if preexisting:
            preexisting["assurance"] = (
                "captured as pre-existing worktree state at task creation; the immutable task baseline "
                "protects this state, but AI Layer does not claim who authored those earlier edits"
            )
            preexisting["task_delta_contract"] = (
                "managed changes are measured against the captured task baseline, not against Git HEAD"
            )
        previous_sequence = db.scalar(
            select(func.max(Task.sequence)).where(Task.project_id == project.id)
        )
        baseline = capture_repository_state(project.root_path, previous=_memory_hash_seed(project))
        task = Task(
            project_id=project.id,
            sequence=int(previous_sequence or 0) + 1,
            goal=goal,
            acceptance_criteria=criteria,
            constraints=task_constraints,
            status="active",
            baseline_digest=str(baseline["digest"]),
            baseline_files=int(baseline["file_count"]),
            execution_origin="managed",
            adopted_changes={},
            preexisting_changes=preexisting,
            workflow_version=classification["workflow_version"],
            workflow_profile=classification["workflow_profile"],
            risk_level=classification["risk_level"],
            risk_reasons=classification["risk_reasons"],
            complexity_level=classification["complexity_level"],
            uncertainty_level=classification["uncertainty_level"],
            cost_policy=classification["cost_policy"],
            discovery_result={},
        )
        db.add(task)
        db.flush()
        baseline_snapshot = bind_task_baseline(db, project, task, baseline)
        first_kind = (
            "discovery"
            if task.workflow_profile in {"discovery_first", "analysis_only"}
            else "implement"
        )
        stage = _create_stage(
            db, task, kind=first_kind, state=baseline, start_snapshot_id=baseline_snapshot.id
        )
        append_event(
            db,
            event_type="TaskCreated",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={
                "key": task_key(task),
                "workflow_profile": task.workflow_profile,
                "preexisting_paths": int(preexisting.get("total") or 0),
                "baseline_mode": "captured_worktree",
            },
        )
        append_event(
            db,
            event_type="TaskClassified",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={
                "risk": task.risk_level,
                "complexity": task.complexity_level,
                "uncertainty": task.uncertainty_level,
                "cost_policy": task.cost_policy,
            },
        )
        db.commit()
        _materialize_recovery_cache(db, project, task, stage)
        return _persist_task_view(db, project, task)


def adopt_task(
    db: Session,
    project: Project,
    *,
    goal: str,
    acceptance_criteria: list[str],
    constraints: list[str],
) -> dict:
    """Adopt already-existing unmanaged Git work for review/remediation without rewriting history.

    No IMPLEMENT stage is created. The current dirty worktree is recorded as pre-task provenance and
    the task starts directly at REVIEW. Any later fixer changes are measured separately from the
    adopted work.
    """
    goal = _bounded_text(
        goal, field="task_adopt: `goal`", max_chars=MAX_TASK_GOAL_CHARS, required=True, redact=True
    )
    root = Path(project.root_path).expanduser().resolve()
    with directory_lock(_task_lock(project), timeout_seconds=15):
        lock_project(db, project)
        existing = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status.in_(sorted(OPEN_TASK_STATUSES)))
            .limit(1)
        )
        if existing is not None:
            raise RuntimeError(
                f"Project already has active task {task_key(existing)} ({existing.status}). "
                "Sequential execution forbids adoption while another task is open."
            )
        adopted = _git_changed_paths(root)
        if not adopted.get("total"):
            raise RuntimeError(
                "task_adopt found no staged, unstaged, or untracked Git changes. "
                "Use task_create before new implementation instead of creating retrospective history."
            )
        current_state = capture_repository_state(root, previous=_memory_hash_seed(project))
        adopted["repository_digest_at_adoption"] = str(current_state.get("digest") or "")
        criteria = _bounded_text_list(
            acceptance_criteria, field="task_adopt: `acceptance_criteria`", redact=True
        )
        task_constraints = _bounded_text_list(
            constraints, field="task_adopt: `constraints`", redact=True
        )
        adopted_paths = [str(item) for item in (adopted.get("paths") or [])[:40]]
        adopted_classification = _classify_task(
            project,
            goal=goal,
            acceptance_criteria=criteria,
            constraints=[*task_constraints, "affected paths: " + " ".join(adopted_paths)],
            workflow="standard",
            risk="auto",
            cost_policy=str(load_policy().get("default_cost_policy") or "economy"),
        )
        adopted["assurance"] = (
            "explicitly-declared unmanaged pre-task work; Git identifies the dirty paths, but AI Layer "
            "does not claim who created them or when they were first edited"
        )
        previous_sequence = db.scalar(
            select(func.max(Task.sequence)).where(Task.project_id == project.id)
        )
        task = Task(
            project_id=project.id,
            sequence=int(previous_sequence or 0) + 1,
            goal=goal,
            acceptance_criteria=criteria,
            constraints=task_constraints,
            status="active",
            review_round=1,
            baseline_digest=str(current_state["digest"]),
            baseline_files=int(current_state["file_count"]),
            execution_origin="adopted_unmanaged_changes",
            adopted_changes=adopted,
            preexisting_changes={},
            workflow_version=2,
            workflow_profile="standard",
            risk_level=adopted_classification["risk_level"],
            risk_reasons=[
                "unmanaged pre-task changes require independent review",
                *list(adopted_classification.get("risk_reasons") or []),
            ],
            complexity_level=adopted_classification["complexity_level"],
            uncertainty_level=adopted_classification["uncertainty_level"],
            cost_policy=adopted_classification["cost_policy"],
            discovery_result={},
        )
        db.add(task)
        db.flush()
        baseline_snapshot = bind_task_baseline(db, project, task, current_state)
        stage = _create_stage(
            db,
            task,
            kind="review",
            state=current_state,
            review_round=1,
            start_snapshot_id=baseline_snapshot.id,
        )
        append_event(
            db,
            event_type="TaskAdopted",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={"key": task_key(task), "adopted_paths": adopted.get("total", 0)},
        )
        db.commit()
        _materialize_recovery_cache(db, project, task, stage)
        return _persist_task_view(db, project, task)


def delegate_current_stage(
    db: Session,
    project: Project,
    *,
    worker_id: str,
    actual_model: str | None = None,
    model_assurance: str = "requested_unverified",
    telemetry: dict | None = None,
    expected_version: int | None = None,
) -> dict:
    """Bind a fresh worker before any managed stage mutation can be attributed to that worker."""
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
        if stage is None:
            raise RuntimeError(f"Active task {task_key(task)} has no active stage.")
        if stage.worker_id:
            worker = _validate_worker_id(db, task, worker_id, current_stage_id=stage.id)
            if stage.worker_id != worker:
                raise RuntimeError(
                    f"Stage {stage.id} is already delegated to `{stage.worker_id}`; "
                    "sequential execution forbids rebinding it to another worker."
                )
            payload = task_to_dict(db, task, include_history=False)
            payload["delegation_idempotent"] = True
            return payload
        if not bool(stage.delegation_required):
            raise RuntimeError(
                "LEGACY_STAGE_NO_RETROACTIVE_DELEGATION: this in-flight stage predates explicit "
                "delegation enforcement. Complete it once through task_stage_complete as returned "
                "by task_next; do not create retrospective delegation history."
            )

        worker = _validate_worker_id(db, task, worker_id, current_stage_id=stage.id)

        start_state = _load_stage_start(db, project, task, stage)
        current_state = capture_repository_state(project.root_path, previous=start_state)
        drift = repository_changes(start_state, current_state)
        if drift["total"]:
            raise RuntimeError(
                "UNMANAGED_STAGE_MUTATION: repository changed before the active stage was explicitly delegated. "
                "Do not attribute these edits to a worker retroactively. Revert them before delegation, or cancel "
                "the task and use task_adopt if the changes are intended unmanaged work."
            )
        assurance = str(model_assurance or "requested_unverified").strip().lower()
        if assurance not in {"requested_unverified", "host_reported"}:
            raise ValueError(
                "model_assurance must be requested_unverified|host_reported; verified requires a trusted host adapter."
            )
        actual = str(actual_model or "").strip()
        if assurance == "host_reported" and not actual:
            raise ValueError("actual_model is required when model_assurance=host_reported.")
        stage.worker_id = worker
        stage.delegated_at = utcnow()
        start_worker_lease(stage, now=stage.delegated_at)
        stage.actual_model = actual
        stage.model_assurance = assurance
        stage.telemetry = dict(telemetry or {})
        bump_task_version(task)
        task.updated_at = utcnow()
        append_event(
            db,
            event_type="StageDelegated",
            project=project,
            aggregate_type="task_stage",
            aggregate_id=str(stage.id),
            payload={"task_id": str(task.id), "worker_id": worker, "kind": stage.kind},
        )
        append_event(
            db,
            event_type="AgentAssigned",
            project=project,
            aggregate_type="task_stage",
            aggregate_id=str(stage.id),
            payload={
                "worker_id": worker,
                "requested_model": stage.agent_model,
                "actual_model": actual or None,
                "model_assurance": assurance,
                "tier": stage.agent_tier,
                "profile": stage.agent_profile,
            },
        )
        db.commit()
        payload = _persist_task_view(db, project, task)
        payload["orchestrator_handoff"] = {
            **orchestrator_stage_instruction(
                stage_kind=stage.kind, delegated=True, worker_id=worker
            ),
            "next_host_action": "START_THE_DELEGATED_WORKER_NOW",
            "delegation_contract": payload.get("delegation_contract"),
        }
        return payload


def resume_task(db: Session, project: Project, *, expected_version: int | None = None) -> dict:
    with directory_lock(_task_lock(project), timeout_seconds=15):
        task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status == "blocked")
            .order_by(Task.updated_at.desc())
            .limit(1)
            .with_for_update()
        )
        if task is None:
            raise RuntimeError("No blocked task exists for this project.")
        assert_expected_version(task, expected_version)
        attention_reason = _human_attention_reason(task)
        if attention_reason is not None:
            prior = db.scalar(
                select(TaskStage)
                .where(
                    TaskStage.task_id == task.id,
                    TaskStage.kind == "review",
                    TaskStage.status == "completed",
                    TaskStage.outcome == "changes_required",
                )
                .order_by(TaskStage.ordinal.desc())
                .limit(1)
            )
            if prior is None:
                raise RuntimeError(
                    f"Human-attention task {task_key(task)} has no completed changes_required review to continue."
                )
            stage_start = _load_stage_start(db, project, task, prior)
            current_state = capture_repository_state(project.root_path, previous=stage_start)
            drift = repository_changes(stage_start, current_state)
            if drift["total"]:
                raise RuntimeError(
                    "Cannot resume after human attention because the canonical repository changed "
                    "outside a managed stage. Restore/commit the intended state and start a new task, "
                    "or restore the review snapshot before resuming."
                )
            task.status = "active"
            task.blocked_reason = ""
            task.fix_round += 1
            replacement = _create_stage(
                db,
                task,
                kind="fix",
                state=current_state,
                fix_round=task.fix_round,
            )
            bump_task_version(task)
            task.updated_at = utcnow()
            append_event(
                db,
                event_type="TaskResumed",
                project=project,
                aggregate_type="task",
                aggregate_id=str(task.id),
                payload={"from": "human_attention", "stage_id": str(replacement.id)},
            )
            db.commit()
            return _persist_task_view(db, project, task)

        prior = _latest_resumable_stage(db, task)
        if prior is None:
            raise RuntimeError(f"Blocked task {task_key(task)} has no resumable stage.")
        stage_start = _load_stage_start(db, project, task, prior)
        current_state = capture_repository_state(project.root_path, previous=stage_start)
        restore_required = (
            prior.status == "invalid" and prior.kind in READ_ONLY_STAGES
        ) or prior.outcome in {"unexpected_changes", "worker_disconnected_with_changes"}
        if restore_required:
            drift = repository_changes(stage_start, current_state)
            if drift["total"]:
                raise RuntimeError(
                    "Cannot resume stage after unauthorized repository changes: repository still differs "
                    "from the stage starting state. Restore those changes first."
                )
        elif prior.status == "blocked" and prior.outcome == "blocked":
            expected_digest = str(prior.repository_digest_after or "").strip()
            current_digest = str(current_state.get("digest") or "")
            if not expected_digest or current_digest != expected_digest:
                raise RuntimeError(
                    "UNMANAGED_STAGE_MUTATION: repository changed after the stage entered blocked state. "
                    "AI Layer will not adopt those edits as the baseline of a resumed managed stage. "
                    "Restore the exact blocked-stage repository state, or cancel and use task_adopt if "
                    "the later changes are intended unmanaged work."
                )
        task.status = "active"
        task.blocked_reason = ""
        replacement = _create_stage(
            db,
            task,
            kind=prior.kind,
            state=current_state,
            review_round=prior.review_round,
            fix_round=prior.fix_round,
        )
        bump_task_version(task)
        task.updated_at = utcnow()
        append_event(
            db,
            event_type="TaskResumed",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload={"stage_id": str(replacement.id)},
        )
        db.commit()
        return _persist_task_view(db, project, task)


def cancel_task(
    db: Session, project: Project, *, reason: str, expected_version: int | None = None
) -> dict:
    with directory_lock(_task_lock(project), timeout_seconds=15):
        task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status.in_(sorted(OPEN_TASK_STATUSES)))
            .order_by(Task.updated_at.desc())
            .limit(1)
            .with_for_update()
        )
        if task is None:
            latest = db.scalar(
                select(Task)
                .where(Task.project_id == project.id)
                .order_by(Task.updated_at.desc())
                .limit(1)
            )
            if latest is None:
                raise RuntimeError("No task exists for this project.")
            if latest.status == "cancelled":
                payload = task_to_dict(db, latest)
                payload["idempotent"] = True
                return payload
            if latest.status == "completed":
                raise RuntimeError(
                    f"Task {task_key(latest)} is already completed and cannot be cancelled."
                )
            raise RuntimeError("No active or blocked task exists for this project.")
        assert_expected_version(task, expected_version)
        stage = _active_stage(db, task)
        if stage is not None:
            stage.status = "cancelled"
            stage.outcome = "cancelled"
            stage.summary = reason.strip() or "Cancelled by orchestrator."
            stage.completed_at = utcnow()
        task.status = "cancelled"
        task.blocked_reason = ""
        task.completion_summary = reason.strip() or "Cancelled by orchestrator."
        task.completed_at = utcnow()
        abandon_task_drafts(db, project, str(task.id))
        bump_task_version(task)
        task.updated_at = utcnow()
        db.commit()
        payload = _persist_task_view(db, project, task)
        _cleanup_task_review_sandboxes(db, project, task)
        shutil.rmtree(_task_work_dir(project, task.id), ignore_errors=True)
        return payload
