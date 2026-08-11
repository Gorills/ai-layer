from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from ai_layer.application.security import decide
from ai_layer.core.request_context import current_operation
from ai_layer.core.service import get_project
from ai_layer.db.models import Task
from ai_layer.db.session import session_scope
from ai_layer.domain.ports import VerificationExecutor
from ai_layer.domain.security import LOCAL_TRUSTED_ACTOR
from ai_layer.domain.verification import VerificationRequest
from ai_layer.observability.domain_events import append_event
from ai_layer.tasks.views import _active_stage
from ai_layer.verification.runner import persist_verification


def run_stage_verification(
    project_root: str | Path,
    *,
    command: list[str] | tuple[str, ...],
    cwd: str = ".",
    timeout_seconds: int = 300,
    environment: dict[str, str] | None = None,
    executor: VerificationExecutor | None = None,
) -> dict:
    """Execute authoritative verification for a delegated IMPLEMENT/FIX stage."""
    with session_scope() as db:
        project = get_project(db, project_root)
        task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status == "active")
            .order_by(Task.updated_at.desc())
            .limit(1)
        )
        if task is None:
            raise RuntimeError("No active task exists for verification.")
        stage = _active_stage(db, task)
        if stage is None or stage.kind not in {"implement", "fix"}:
            raise RuntimeError(
                "verification_run is for active IMPLEMENT/FIX stages; use review_check_run for read-only REVIEW/DISCOVERY."
            )
        if not stage.worker_id:
            raise RuntimeError(
                "STAGE_NOT_DELEGATED: verification requires an explicitly delegated active stage."
            )
        request = VerificationRequest.from_values(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            environment=environment,
        )
        operation = current_operation()
        actor = operation.actor if operation is not None else LOCAL_TRUSTED_ACTOR
        policy = decide(actor, request.required_capability)
        if not policy.allowed:
            raise PermissionError(policy.reason)
        append_event(
            db,
            event_type="VerificationStarted",
            project=project,
            aggregate_type="task_stage",
            aggregate_id=str(stage.id),
            payload={"command": list(request.command), "cwd": request.cwd},
        )
        db.commit()
        if executor is None:
            from ai_layer.verification.runner import SubprocessVerificationExecutor

            executor = SubprocessVerificationExecutor()
        result, _ = executor.execute(
            project_id=project.id,
            project_root=project.root_path,
            request=request,
        )
        row = persist_verification(db, project, result, stage=stage)
        append_event(
            db,
            event_type="VerificationCompleted",
            project=project,
            aggregate_type="task_stage",
            aggregate_id=str(stage.id),
            payload={
                "verification_id": str(row.id),
                "assurance": result.assurance.value,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "ok": result.passed,
                "evidence_ref": result.evidence_ref,
            },
        )
        db.commit()
        return {
            "id": str(row.id),
            "stage_id": str(stage.id),
            "task_id": str(task.id),
            "assurance": result.assurance.value,
            "ok": result.passed,
            "command": list(result.command),
            "cwd": result.cwd,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "output_summary": result.output_summary,
            "evidence_ref": result.evidence_ref,
        }
