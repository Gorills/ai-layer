from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import TaskStage, VerificationRun
from ai_layer.tasks.contracts import _stage_agent_policy
from ai_layer.tasks.micro_runtime import is_inline_micro_stage


def _stage_label(stage: TaskStage) -> str:
    if stage.kind == "review":
        return f"review #{stage.review_round}"
    if stage.kind == "fix":
        return f"fix #{stage.fix_round}"
    if stage.kind == "discovery":
        return "discovery"
    return "implementation"


def _stage_payload(stage: TaskStage) -> dict:
    sandbox_checks = [
        item for item in list(stage.checks or []) if str(item).startswith("[ai-layer-sandbox]")
    ]
    inline_micro = is_inline_micro_stage(stage)
    return {
        "id": str(stage.id),
        "ordinal": stage.ordinal,
        "kind": stage.kind,
        "label": _stage_label(stage),
        "status": stage.status,
        "review_round": stage.review_round,
        "fix_round": stage.fix_round,
        "execution_mode": "inline_micro" if inline_micro else "delegated",
        "delegation_required": bool(stage.delegation_required),
        "delegated": bool(stage.delegated_at),
        "explicitly_delegated": bool(stage.delegated_at),
        "delegated_at": stage.delegated_at.isoformat() if stage.delegated_at else None,
        "worker_heartbeat_at": stage.worker_heartbeat_at.isoformat()
        if stage.worker_heartbeat_at
        else None,
        "worker_lease_expires_at": (
            stage.worker_lease_expires_at.isoformat() if stage.worker_lease_expires_at else None
        ),
        "worker_id": None if inline_micro else (stage.worker_id or None),
        "agent_policy": _stage_agent_policy(stage),
        "model_identity": {
            "requested": stage.agent_model or None,
            "actual": stage.actual_model or None,
            "assurance": stage.model_assurance or "requested_unverified",
        },
        "telemetry": dict(stage.telemetry or {}),
        "worker_identity_assurance": (
            "inline-top-level-actor"
            if inline_micro
            else (
                "legacy-unverified-worker-label"
                if stage.worker_id and not stage.delegation_required
                else ("label-only" if stage.worker_id else None)
            )
        ),
        "delegation_assurance": (
            "inline-micro-machine-authorized"
            if inline_micro
            else (
                "legacy-no-explicit-delegation"
                if not stage.delegation_required
                else (
                    "explicit-pre-mutation-label"
                    if stage.delegated_at
                    else "required-not-yet-bound"
                )
            )
        ),
        "outcome": stage.outcome or None,
        "summary": stage.summary,
        "checks": list(stage.checks or []),
        "external_actions": list(stage.external_actions or []),
        "check_evidence_assurance": (
            "ai-layer-executed-sandbox+reported-by-worker"
            if sandbox_checks
            else (
                "reported-by-inline-actor"
                if inline_micro and stage.checks
                else ("reported-by-worker" if stage.checks else None)
            )
        ),
        "changes": dict(stage.changes or {}),
        "result_data": dict(stage.result_data or {}),
        "start_snapshot_id": str(stage.start_snapshot_id) if stage.start_snapshot_id else None,
        "created_at": stage.created_at.isoformat() if stage.created_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
    }


def _verification_payloads(db: Session, stage: TaskStage) -> list[dict]:
    rows = db.scalars(
        select(VerificationRun)
        .where(VerificationRun.stage_id == stage.id)
        .order_by(VerificationRun.created_at)
    ).all()
    return [
        {
            "id": str(row.id),
            "assurance": row.assurance,
            "command": list(row.command or []),
            "cwd": row.cwd,
            "started_at": row.started_at.isoformat(),
            "completed_at": row.completed_at.isoformat(),
            "exit_code": row.exit_code,
            "timed_out": bool(row.timed_out),
            "passed": (not row.timed_out and row.exit_code == 0),
            "output_summary": row.output_summary,
            "evidence_ref": row.evidence_ref,
        }
        for row in rows
    ]


def _stage_payload_with_verification(db: Session, stage: TaskStage) -> dict:
    payload = _stage_payload(stage)
    payload["verification"] = _verification_payloads(db, stage)
    return payload


def _completion_contract(stage: TaskStage, findings: list[dict]) -> dict:
    pending = [item for item in findings if item.get("status") == "pending_verification"]
    inline_micro = is_inline_micro_stage(stage)
    common = {
        "stage": stage.kind,
        "stage_id": str(stage.id),
        "worker_id": None if inline_micro else (stage.worker_id or None),
        "agent_policy": _stage_agent_policy(stage),
        "orchestrator_records_result": not inline_micro,
    }
    if stage.kind == "discovery":
        return {
            **common,
            "tool": "task_discovery_complete",
            "required": ["summary", "checks", "outcome"],
            "optional": [
                "verified_facts",
                "risks",
                "proposed_plan",
                "proposed_acceptance_criteria",
                "external_actions",
            ],
            "outcomes": [
                "ready_for_implementation",
                "analysis_complete",
                "no_change_needed",
                "blocked",
            ],
        }
    if stage.kind == "review":
        return {
            **common,
            "tool": "task_review_complete",
            "required": ["summary", "checks", "verdict"]
            + (["verification_results"] if pending else []),
            "optional": ["findings", "external_actions"],
            "verdicts": ["pass", "changes_required"],
            "finding_required_fields": ["severity", "problem"],
            "verification_required_fields": ["finding_id", "status", "evidence"],
            "findings_to_verify": [item.get("id") for item in pending],
        }
    if stage.kind == "fix":
        return {
            **common,
            "tool": "task_fix_complete",
            "required": ["summary", "checks"],
            "optional": ["outcome", "external_actions"],
            "outcomes": ["done", "no_changes_needed", "blocked"],
        }
    return {
        **common,
        "tool": "task_implementation_complete",
        "required": ["summary", "checks"],
        "optional": ["outcome", "external_actions"],
        "outcomes": ["done", "blocked"],
    }
