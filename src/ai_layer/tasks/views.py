from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, ReviewFinding, Task, TaskStage
from ai_layer.domain.orchestrator import orchestrator_stage_instruction
from ai_layer.domain.workflow import stage_definition
from ai_layer.memory.knowledge_store import has_task_drafts
from ai_layer.tasks.constants import (
    HUMAN_ATTENTION_PREFIX,
    MAX_AUTOMATIC_FIX_ROUNDS,
    MAX_FINDINGS,
    MAX_STAGE_HISTORY,
    MAX_WORKER_ID_CHARS,
    OPEN_TASK_STATUSES,
    READ_ONLY_STAGES,
    TASK_STATE_SCHEMA,
)
from ai_layer.tasks.contracts import _configure_stage_agent, _stage_agent_policy
from ai_layer.tasks.delegation_contract import build_delegation_contract
from ai_layer.tasks.micro_runtime import (
    INLINE_MICRO_WORKER_ID,
    inline_micro_next_action,
    is_inline_micro_stage,
    should_inline_micro_implementation,
)
from ai_layer.tasks.review_workspace import cleanup_review_sandbox
from ai_layer.tasks.stage_views import (
    _completion_contract,
    _stage_payload_with_verification,
)
from ai_layer.tasks.stage_views import (
    _stage_label as _stage_label,
)
from ai_layer.tasks.stage_views import (
    _stage_payload as _stage_payload,
)
from ai_layer.tasks.state_store import (
    atomic_write_json as _atomic_write_json,
)
from ai_layer.tasks.state_store import (
    create_repository_snapshot,
    snapshot_store,
    task_key,
)
from ai_layer.tasks.state_store import (
    task_root as _task_root,
)


def _human_attention_reason(task: Task) -> str | None:
    raw = (task.blocked_reason or "").strip()
    if not raw.startswith(HUMAN_ATTENTION_PREFIX):
        return None
    return raw[len(HUMAN_ATTENTION_PREFIX) :].strip() or "Automatic remediation limit reached."


def _active_stage(db: Session, task: Task) -> TaskStage | None:
    return db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == task.id, TaskStage.status == "active")
        .order_by(TaskStage.ordinal.desc())
        .limit(1)
    )


def _stages(db: Session, task: Task) -> list[TaskStage]:
    return list(
        db.scalars(
            select(TaskStage).where(TaskStage.task_id == task.id).order_by(TaskStage.ordinal)
        ).all()
    )


def _remediation_fix_count(db: Session, task: Task) -> int:
    """Count completed FIX stages that performed actual remediation."""
    return sum(
        1
        for stage in _stages(db, task)
        if stage.kind == "fix"
        and stage.status == "completed"
        and stage.outcome != "no_changes_needed"
    )


def _cleanup_task_review_sandboxes(db: Session, project: Project, task: Task) -> None:
    for stage in _stages(db, task):
        if stage.kind not in READ_ONLY_STAGES:
            continue
        try:
            cleanup_review_sandbox(project, str(stage.id))
        except (OSError, RuntimeError):
            continue


def _findings(db: Session, task: Task) -> list[ReviewFinding]:
    return list(
        db.scalars(
            select(ReviewFinding)
            .where(ReviewFinding.task_id == task.id)
            .order_by(ReviewFinding.created_at, ReviewFinding.id)
        ).all()
    )


def _next_ordinal(db: Session, task: Task) -> int:
    value = db.scalar(select(func.max(TaskStage.ordinal)).where(TaskStage.task_id == task.id))
    return int(value or 0) + 1


def _create_stage(
    db: Session,
    task: Task,
    *,
    kind: str,
    state: dict,
    review_round: int = 0,
    fix_round: int = 0,
    start_snapshot_id: UUID | None = None,
) -> TaskStage:
    snapshot = snapshot_store(db).get(start_snapshot_id) if start_snapshot_id is not None else None
    if start_snapshot_id is not None:
        if snapshot is None or snapshot.project_id != task.project_id:
            raise RuntimeError("Stage start snapshot is missing or belongs to another project.")
        if snapshot.digest != str(state.get("digest") or ""):
            raise RuntimeError(
                "Stage start snapshot does not match the requested repository state."
            )
    else:
        snapshot = create_repository_snapshot(
            db,
            project_id=task.project_id,
            state=state,
            snapshot_kind="stage_start",
        )
    inline_micro = should_inline_micro_implementation(task, kind)
    stage = TaskStage(
        task_id=task.id,
        ordinal=_next_ordinal(db, task),
        kind=kind,
        status="active",
        review_round=review_round,
        fix_round=fix_round,
        delegation_required=not inline_micro,
        worker_id=INLINE_MICRO_WORKER_ID if inline_micro else "",
        repository_digest_before=str(state.get("digest") or ""),
        start_snapshot_id=snapshot.id,
    )
    _configure_stage_agent(task, stage)
    db.add(stage)
    db.flush()
    return stage


def _finding_payload(item: ReviewFinding) -> dict:
    history = list(item.verification_history or [])[-20:]
    return {
        "id": str(item.id),
        "severity": item.severity,
        "category": item.category,
        "path": item.path,
        "problem": item.problem,
        "required_fix": item.required_fix,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        "verification_evidence": item.verification_evidence or "",
        "verification_history": history,
        "provenance": dict(item.provenance or {}),
        "regression_count": sum(1 for entry in history if entry.get("status") == "regression"),
        "verified_by_stage_id": str(item.verified_by_stage_id)
        if item.verified_by_stage_id
        else None,
    }


def _next_action(task: Task, stage: TaskStage | None) -> dict:
    if task.status == "completed":
        if (task.execution_origin or "managed") == "adopted_unmanaged_changes":
            return {
                "action": "done",
                "message": "Adopted unmanaged changes passed the managed review/remediation gates; original implementation was not claimed as managed Task implementation.",
            }
        return {
            "action": "done",
            "message": f"Task completed through workflow profile {task.workflow_profile or 'legacy_standard'}.",
        }
    if task.status == "cancelled":
        return {"action": "none", "message": "Task is cancelled."}
    if task.status == "blocked":
        attention = _human_attention_reason(task)
        if attention is not None:
            return {
                "action": "human_attention_required",
                "message": attention,
                "resume": "Inspect the unresolved findings, then call task_resume only if you explicitly want one more remediation cycle.",
            }
        return {
            "action": "resolve_blocker_then_resume",
            "message": task.blocked_reason or "Task is blocked and must be resumed explicitly.",
        }
    if stage is None:
        return {
            "action": "inspect_state",
            "message": "No active stage was found for an active task.",
        }
    role = stage_definition(stage.kind).role
    if is_inline_micro_stage(stage):
        return inline_micro_next_action(stage)
    if stage.worker_id:
        return {
            "action": "record_stage_result",
            "role": role,
            "stage_id": str(stage.id),
            "worker_id": stage.worker_id,
            "orchestrator_contract": orchestrator_stage_instruction(
                stage_kind=stage.kind, delegated=True, worker_id=stage.worker_id
            ),
            "completion_precondition": (
                "The bound worker actually ran this stage and returned the evidence being recorded. "
                "If the worker has not actually been started yet, start it now; the orchestrator must not perform the stage."
            ),
            "message": (
                "Use only the actual delegated worker result. If that worker has not run yet, start it now. "
                "Do not edit the repository or substitute orchestrator work; if the worker cannot run, report the blocker."
            ),
        }
    message = {
        "implement": "Delegate implementation to a fresh subagent. The orchestrator must not edit the repository.",
        "review": "Delegate read-only review to a fresh separate reviewer subagent. Any managed repository-state change invalidates the review.",
        "fix": "Delegate fixes to a fresh subagent using only the open review findings and task contract.",
        "discovery": "Delegate read-only discovery to the requested subagent profile. Gather verified facts/risks/plan; do not edit the repository.",
    }.get(stage.kind, "Delegate the active stage to a fresh subagent.")
    return {
        "action": "delegate_stage",
        "role": role,
        "stage_id": str(stage.id),
        "tool": "task_stage_delegate",
        "required": ["worker_id"],
        "agent_policy": _stage_agent_policy(stage),
        "orchestrator_contract": orchestrator_stage_instruction(
            stage_kind=stage.kind, delegated=False
        ),
        "message": message
        + " After binding, start that worker; never perform the stage yourself as fallback.",
    }


def _delegation_contract(db: Session, task: Task, stage: TaskStage | None) -> dict | None:
    if stage is None or task.status != "active":
        return None
    open_findings = [
        _finding_payload(item)
        for item in _findings(db, task)
        if item.status in {"open", "pending_verification"}
    ]
    knowledge_review_required = False
    if stage.kind == "review":
        project = db.get(Project, task.project_id)
        knowledge_review_required = bool(
            project is not None and has_task_drafts(db, project, str(task.id))
        )
    return build_delegation_contract(
        task,
        stage,
        open_findings,
        _completion_contract(stage, open_findings),
        knowledge_review_required=knowledge_review_required,
    )


def task_to_dict(db: Session, task: Task, *, include_history: bool = True) -> dict:
    stage = _active_stage(db, task)
    stages = _stages(db, task) if include_history else ([] if stage is None else [stage])
    findings = _findings(db, task)
    active_findings = [item for item in findings if item.status in {"open", "pending_verification"}]
    finding_status_counts = {
        status: sum(1 for item in findings if item.status == status)
        for status in ("open", "pending_verification", "verified")
    }
    attention_reason = _human_attention_reason(task)
    remediation_fix_count = _remediation_fix_count(db, task)
    active_finding_payloads = [_finding_payload(item) for item in active_findings[-MAX_FINDINGS:]]
    tier_counts = {"economy": 0, "balanced": 0, "strong": 0}
    delegated_stage_calls = 0
    for item in stages:
        tier = str(item.agent_tier or "")
        if tier in tier_counts:
            tier_counts[tier] += 1
        if item.delegated_at:
            delegated_stage_calls += 1
    agent_usage = {
        "delegated_stages": delegated_stage_calls,
        "requested_tiers": tier_counts,
        "strong_stages": tier_counts["strong"],
        "assurance": "per-stage model_identity distinguishes requested_unverified, host_reported, and trusted verified sources",
    }
    return {
        "schema": TASK_STATE_SCHEMA,
        "id": str(task.id),
        "key": task_key(task),
        "project_id": str(task.project_id),
        "goal": task.goal,
        "acceptance_criteria": list(task.acceptance_criteria or []),
        "constraints": list(task.constraints or []),
        "status": task.status,
        "version": int(task.version or 1),
        "baseline_snapshot_id": str(task.baseline_snapshot_id)
        if task.baseline_snapshot_id
        else None,
        "review_round": task.review_round,
        "fix_round": task.fix_round,
        "baseline_files": task.baseline_files,
        "final_changes": dict(task.final_changes or {}),
        "completion_summary": task.completion_summary,
        "blocked_reason": task.blocked_reason,
        "human_attention_required": attention_reason is not None,
        "human_attention_reason": attention_reason,
        "automatic_fix_round_limit": MAX_AUTOMATIC_FIX_ROUNDS,
        "automatic_remediation_count": remediation_fix_count,
        "handoff_session_id": task.handoff_session_id,
        "execution_origin": task.execution_origin or "managed",
        "adopted_changes": dict(task.adopted_changes or {}),
        "preexisting_changes": dict(task.preexisting_changes or {}),
        "workflow_version": int(task.workflow_version or 1),
        "workflow_profile": task.workflow_profile or "legacy_standard",
        "risk_level": task.risk_level or "normal",
        "risk_reasons": list(task.risk_reasons or []),
        "complexity_level": task.complexity_level or "normal",
        "uncertainty_level": task.uncertainty_level or "normal",
        "cost_policy": task.cost_policy or "economy",
        "discovery_result": dict(task.discovery_result or {}),
        "agent_usage": agent_usage,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "active_stage": _stage_payload_with_verification(db, stage) if stage else None,
        "next_action": _next_action(task, stage),
        "delegation_contract": _delegation_contract(db, task, stage),
        "completion_contract": (
            _completion_contract(stage, active_finding_payloads)
            if stage and stage.worker_id
            else None
        ),
        "stages": [
            _stage_payload_with_verification(db, item) for item in stages[-MAX_STAGE_HISTORY:]
        ],
        "findings": [
            _finding_payload(item)
            for item in (findings[-MAX_FINDINGS:] if include_history else active_findings[-20:])
        ],
        "active_findings": active_finding_payloads,
        "finding_summary": {"total": len(findings), **finding_status_counts},
        "open_findings": len(active_findings),
    }


def _persist_task_view(db: Session, project: Project, task: Task) -> dict:
    """Publish a best-effort disk projection after the DB transition is committed."""
    payload = task_to_dict(db, task)
    try:
        root = _task_root(project)
        if task.status in OPEN_TASK_STATUSES:
            _atomic_write_json(root / "current.json", payload)
        else:
            (root / "current.json").unlink(missing_ok=True)
            _atomic_write_json(root / "latest.json", payload)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        payload = dict(payload)
        payload["projection_warning"] = (
            f"task dashboard projection not updated: {type(exc).__name__}"
        )
    return payload


def current_task(db: Session, project: Project, *, include_history: bool = True) -> dict:
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status.in_(sorted(OPEN_TASK_STATUSES)))
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if task is None:
        latest = db.scalar(
            select(Task)
            .where(Task.project_id == project.id)
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        return {
            "active": False,
            "state": "no_active_task",
            "next_action": {
                "action": "host_native",
                "tool": None,
                "message": (
                    "No managed Task is active. Ordinary repository work may continue through the host-native "
                    "agent runtime; create a Task only when durable or strict managed execution is useful."
                ),
                "managed_option": {"tool": "task_create", "required": ["goal"]},
            },
            "latest": task_to_dict(db, latest, include_history=include_history) if latest else None,
        }
    return {
        "active": True,
        "state": task.status,
        "task": task_to_dict(db, task, include_history=include_history),
    }


def _validate_worker_id(
    db: Session,
    task: Task,
    worker_id: str,
    *,
    current_stage_id: UUID | None = None,
) -> str:
    worker = worker_id.strip()
    if not worker:
        raise ValueError("`worker_id` is required for every delegated subagent stage.")
    if current_stage_id is not None:
        current_stage = db.get(TaskStage, current_stage_id)
        if current_stage is not None and is_inline_micro_stage(current_stage):
            return INLINE_MICRO_WORKER_ID
    if len(worker) > MAX_WORKER_ID_CHARS:
        raise ValueError(f"`worker_id` exceeds the {MAX_WORKER_ID_CHARS}-character limit.")
    stmt = select(TaskStage.id).where(TaskStage.task_id == task.id, TaskStage.worker_id == worker)
    if current_stage_id is not None:
        stmt = stmt.where(TaskStage.id != current_stage_id)
    reused = db.scalar(stmt.limit(1))
    if reused is not None:
        raise ValueError(
            f"worker_id `{worker}` was already used in {task_key(task)}. "
            "Every stage requires a fresh worker_id label; native actor identity is host-enforced."
        )
    return worker
