from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, Task, TaskStage
from ai_layer.domain.orchestrator import (
    managed_orchestrator_contract,
    orchestrator_stage_instruction,
)
from ai_layer.tasks.constants import OPEN_TASK_STATUSES, READ_ONLY_STAGES
from ai_layer.tasks.contracts import _stage_agent_policy
from ai_layer.tasks.review_checks import run_review_check
from ai_layer.tasks.review_workspace import cleanup_review_sandbox, prepare_review_sandbox
from ai_layer.tasks.state_store import (
    load_stage_start as _load_stage_start,
)
from ai_layer.tasks.state_store import (
    task_key,
)
from ai_layer.tasks.views import (
    _active_stage,
    _completion_contract,
    _human_attention_reason,
    current_task,
)
from ai_layer.workspace.repository import (
    capture_repository_state,
    repository_changes,
)
from ai_layer.workspace.repository import (
    git_changed_paths as _git_changed_paths,
)


def _safe_git_changes(root: Path) -> dict | None:
    try:
        return _git_changed_paths(root)
    except RuntimeError:
        return None


def _known_completed_terminal_state(db: Session, project: Project, root: Path) -> dict | None:
    latest = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "completed")
        .order_by(Task.completed_at.desc(), Task.updated_at.desc())
        .limit(1)
    )
    if latest is None:
        return None
    terminal_stage = db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == latest.id, TaskStage.status == "completed")
        .order_by(TaskStage.ordinal.desc())
        .limit(1)
    )
    expected_digest = str((terminal_stage.repository_digest_after if terminal_stage else "") or "")
    if not expected_digest:
        return None
    current = capture_repository_state(root)
    if str(current.get("digest") or "") != expected_digest:
        return None
    return {
        "task": task_key(latest),
        "repository_digest": expected_digest,
        "execution_origin": latest.execution_origin or "managed",
        "assurance": "current repository state exactly matches the last completed managed Task terminal state",
    }


def _latest_resumable_stage(db: Session, task: Task) -> TaskStage | None:
    return db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == task.id, TaskStage.status.in_(["blocked", "invalid"]))
        .order_by(TaskStage.ordinal.desc())
        .limit(1)
    )


def _blocked_stage_repository_guard(
    db: Session,
    project: Project,
    task: Task,
    root: Path,
) -> dict | None:
    """Detect repository mutations that happened after an ordinary stage became blocked.

    A blocked worker completion already stores repository_digest_after. That digest is the durable
    recovery boundary: task_resume must not silently adopt later out-of-stage edits as the baseline
    of a replacement stage. Invalid review/unexpected-change recovery keeps its stricter restore-to-
    stage-start rule and is handled separately by resume_task.
    """
    prior = _latest_resumable_stage(db, task)
    if prior is None or prior.status != "blocked" or prior.outcome != "blocked":
        return None
    expected = str(prior.repository_digest_after or "").strip()
    if not expected:
        # Historical/corrupt state without a terminal digest cannot be silently trusted. Recovery
        # remains explicit instead of manufacturing a new baseline from the current worktree.
        return {
            "stage_id": str(prior.id),
            "stage": prior.kind,
            "expected_repository_digest": None,
            "current_repository_digest": None,
            "reason": "blocked stage is missing its durable repository terminal digest",
        }
    current = capture_repository_state(root)
    current_digest = str(current.get("digest") or "")
    if current_digest == expected:
        return None
    return {
        "stage_id": str(prior.id),
        "stage": prior.kind,
        "expected_repository_digest": expected,
        "current_repository_digest": current_digest,
        "reason": "repository changed after the stage entered blocked state",
    }


def _inactive_navigation(db: Session, project: Project, runtime: dict, root: Path) -> dict:
    dirty = _safe_git_changes(root) or {}
    preexisting = dirty if int(dirty.get("total") or 0) else {}
    known_terminal = _known_completed_terminal_state(db, project, root) if preexisting else None
    if preexisting:
        message = (
            f"No managed Task is active and the repository already has {int(preexisting.get('total') or 0)} "
            "pre-existing changed path(s). Ordinary host-native work remains allowed. If strict/durable managed "
            "execution is explicitly useful, task_create can baseline the exact current worktree and measure only "
            "later managed changes; use task_adopt only when the existing edits themselves should enter managed "
            "review/remediation. Never stash/reset/restore/commit merely to satisfy AI Layer."
        )
    else:
        message = (
            "No managed Task is active. Continue ordinary work through the host-native agent runtime; create a "
            "managed Task only when durable state, strict review/remediation, or explicit user intent makes it useful."
        )
    payload = {
        **runtime,
        "state": "idle_with_preexisting_changes" if preexisting else runtime.get("state"),
        "project_root": str(root),
        "preexisting_changes": preexisting,
        "next_action": {
            "action": "host_native",
            "tool": None,
            "message": message,
            "managed_option": {
                "tool": "task_create",
                "required": ["goal"],
                "optional": [
                    "acceptance_criteria",
                    "constraints",
                    "workflow",
                    "risk",
                    "cost_policy",
                ],
            },
            "alternative": (
                "Use task_adopt only if the pre-existing dirty changes are themselves the work to review/manage."
                if preexisting
                else None
            ),
            "worktree_rule": "Do not stash/reset/restore/commit solely to satisfy AI Layer.",
        },
    }
    if known_terminal is not None:
        payload["known_preexisting_state"] = known_terminal
    return payload


def _active_stage_navigation(
    db: Session, project: Project, task: Task, stage: TaskStage, task_payload: dict, root: Path
) -> dict | None:
    if stage.worker_id:
        task_payload["next_action"] = {
            "action": "record_stage_result",
            "tool": _completion_contract(stage, task_payload.get("active_findings") or [])["tool"],
            "stage": stage.kind,
            "stage_id": str(stage.id),
            "worker_id": stage.worker_id,
            "agent_policy": _stage_agent_policy(stage),
            "orchestrator_contract": orchestrator_stage_instruction(
                stage_kind=stage.kind, delegated=True, worker_id=stage.worker_id
            ),
            "completion_precondition": (
                "The bound worker actually ran and returned the evidence being recorded. "
                "If it has not run yet, start it now; do not perform the stage yourself."
            ),
            "forbidden": [
                "orchestrator repository edits",
                "orchestrator external mutations",
                "starting another stage",
                "completion from orchestrator-authored work",
            ],
            "message": (
                "Use the actual bound worker result only. If the worker has not actually run yet, start it now. "
                "If it cannot run or fails, report/block; never implement, fix, review, or discover as fallback."
            ),
        }
        task_payload["completion_contract"] = _completion_contract(
            stage, task_payload.get("active_findings") or []
        )
        return None
    if not bool(stage.delegation_required):
        task_payload["next_action"] = {
            "action": "record_legacy_stage_result",
            "tool": "task_stage_complete",
            "stage": stage.kind,
            "stage_id": str(stage.id),
            "required": ["stage_id", "worker_id", "summary", "checks"],
            "message": (
                "This active stage predates explicit-delegation enforcement. Complete this one legacy "
                "in-flight stage without retroactive task_stage_delegate; do not claim authenticated authorship. "
                "Every subsequently created stage uses the strict delegation contract."
            ),
            "forbidden": [
                "task_stage_delegate",
                "retroactive delegation",
                "orchestrator repository edits",
            ],
            "identity_assurance": "legacy-unverified-worker-label",
        }
        task_payload["legacy_stage_compatibility"] = {
            "delegation_required": False,
            "assurance": (
                "Stage was created before explicit delegation enforcement; AI Layer can complete its durable "
                "workflow state but cannot prove authorship of existing edits."
            ),
        }
        return task_payload["next_action"]
    start_state = _load_stage_start(db, project, task, stage)
    current_state = capture_repository_state(root, previous=start_state)
    drift = repository_changes(start_state, current_state)
    if drift["total"]:
        task_payload["next_action"] = {
            "action": "unmanaged_stage_mutation",
            "code": "UNMANAGED_STAGE_MUTATION",
            "message": (
                "Repository changed before the active stage was explicitly delegated. Do not attribute these "
                "edits to a worker retroactively. Revert them and delegate, or cancel the task and use task_adopt "
                "if these are the intended changes."
            ),
            "forbidden": ["task_stage_complete", "continue editing", "claim worker execution"],
        }
        task_payload["undelegated_changes"] = drift
        return None
    task_payload["next_action"] = {
        "action": "delegate_stage",
        "tool": "task_stage_delegate",
        "required": ["worker_id"],
        "stage": stage.kind,
        "stage_id": str(stage.id),
        "forbidden": [
            "orchestrator repository edits",
            "orchestrator external mutations",
            "stage completion before delegation",
            "orchestrator fallback implementation",
        ],
        "agent_policy": _stage_agent_policy(stage),
        "orchestrator_contract": orchestrator_stage_instruction(
            stage_kind=stage.kind, delegated=False
        ),
        "message": (
            "Bind a fresh worker, then START that native worker with the returned delegation contract. "
            "The orchestrator must not perform the stage itself. If the worker cannot be started, report the blocker."
        ),
    }
    return None


def next_task_action(db: Session, project: Project) -> dict:
    """Return one deterministic workflow instruction instead of asking the agent to remember state."""
    runtime = current_task(db, project, include_history=False)
    root = Path(project.root_path).expanduser().resolve()
    if not runtime.get("active"):
        return _inactive_navigation(db, project, runtime, root)

    task_payload = dict(runtime.get("task") or {})
    task = db.get(Task, UUID(str(task_payload["id"])))
    stage = _active_stage(db, task) if task is not None else None
    if task is not None and task.status == "blocked" and _human_attention_reason(task) is None:
        blocked_drift = _blocked_stage_repository_guard(db, project, task, root)
        if blocked_drift is not None:
            task_payload["next_action"] = {
                "action": "unmanaged_stage_mutation",
                "code": "UNMANAGED_STAGE_MUTATION",
                "message": (
                    "Repository changed after the previous stage was recorded as blocked. task_resume will not "
                    "adopt those edits as a new managed-stage baseline. Restore the exact blocked-stage repository "
                    "state, or cancel and use task_adopt if the later changes are the intended unmanaged work."
                ),
                "forbidden": ["task_resume", "continue editing", "claim managed worker execution"],
            }
            task_payload["blocked_repository_drift"] = blocked_drift
    elif task is not None and task.status == "active" and stage is not None:
        _active_stage_navigation(db, project, task, stage, task_payload, root)
    return {
        "active": True,
        "state": runtime.get("state"),
        "project_root": str(root),
        "orchestrator_contract": managed_orchestrator_contract(),
        "task": task_payload,
        "next_action": task_payload.get("next_action"),
    }


def prepare_current_review_sandbox(db: Session, project: Project) -> dict:
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "active")
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None:
        raise RuntimeError("No active task exists for this project.")
    stage = _active_stage(db, task)
    if stage is None or stage.kind not in READ_ONLY_STAGES:
        raise RuntimeError(
            "Read-only sandbox is available only while the active task stage is discovery or review."
        )
    if bool(stage.delegation_required) and not stage.worker_id:
        raise RuntimeError(
            "STAGE_NOT_DELEGATED: delegate the reviewer before preparing its sandbox."
        )
    return prepare_review_sandbox(project, task, stage)


def run_current_review_check(
    db: Session,
    project: Project,
    *,
    command: list[str],
    cwd: str | None = None,
    timeout_seconds: int = 300,
) -> dict:
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "active")
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None:
        raise RuntimeError("No active task exists for this project.")
    stage = _active_stage(db, task)
    if stage is None or stage.kind not in READ_ONLY_STAGES:
        raise RuntimeError(
            "review_check_run is available only while the active task stage is discovery or review."
        )
    if bool(stage.delegation_required) and not stage.worker_id:
        raise RuntimeError(
            "STAGE_NOT_DELEGATED: delegate the reviewer before running review checks."
        )
    return run_review_check(
        project,
        task,
        stage,
        command=command,
        relative_cwd=cwd,
        timeout_seconds=timeout_seconds,
    )


def cleanup_current_review_sandbox(db: Session, project: Project) -> dict:
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status.in_(sorted(OPEN_TASK_STATUSES)))
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None:
        raise RuntimeError("No active or blocked task exists for this project.")
    stage = _active_stage(db, task)
    if stage is None:
        stage = db.scalar(
            select(TaskStage)
            .where(TaskStage.task_id == task.id, TaskStage.kind.in_(["review", "discovery"]))
            .order_by(TaskStage.ordinal.desc())
            .limit(1)
        )
    if stage is None:
        return {"ok": True, "removed": False, "reason": "task has no discovery/review stage"}
    return cleanup_review_sandbox(project, str(stage.id))
