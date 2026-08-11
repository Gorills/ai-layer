from __future__ import annotations

from sqlalchemy.orm import Session

from ai_layer.db.models import ReviewFinding, Task, TaskStage
from ai_layer.domain.workflow import stage_definition
from ai_layer.tasks.review_contracts import (
    _normalize_review_submission, _normalize_verification_results, _open_findings,
)

def _validate_stage_result(
    db: Session,
    task: Task,
    stage: TaskStage,
    *,
    outcome: str,
    verdict: str | None,
    findings: list[dict] | None,
    verification_results: list[dict] | None,
    sandbox_evidence: list[dict],
    open_items: list[ReviewFinding] | None,
) -> tuple[str, str, list[dict], list[str], list[ReviewFinding], dict[str, dict]]:
    normalized_verdict = ""
    normalized_findings: list[dict] = []
    input_normalizations: list[str] = []
    pending_to_verify: list[ReviewFinding] = []
    verification_map: dict[str, dict] = {}
    normalized_outcome = outcome
    definition = stage_definition(stage.kind)

    if stage.kind != "review" and normalized_outcome not in definition.allowed_outcomes:
        allowed = "|".join(sorted(definition.allowed_outcomes))
        raise ValueError(f"{stage.kind} stage outcome must be one of: {allowed}")

    if stage.kind == "discovery":
        if task.workflow_profile == "analysis_only" and normalized_outcome == "ready_for_implementation":
            raise ValueError(
                "analysis_only discovery cannot request implementation; create/continue a change task explicitly."
            )
        if task.workflow_profile == "discovery_first" and normalized_outcome == "analysis_complete":
            raise ValueError(
                "discovery_first requires ready_for_implementation or no_change_needed after discovery."
            )
    elif stage.kind == "review":
        pending_to_verify = [item for item in _open_findings(db, task) if item.status == "pending_verification"]
        verification_map, verification_normalizations = _normalize_verification_results(
            pending_to_verify, verification_results
        )
        verification_still_open = any(
            result["status"] == "still_open" for result in verification_map.values()
        )
        normalized_verdict, normalized_findings, input_normalizations = _normalize_review_submission(
            verdict, findings, allow_empty_changes_required=verification_still_open
        )
        failed_checks = [
            item for item in sandbox_evidence
            if int(item.get("exit_code", 1)) != 0 or bool(item.get("timed_out"))
        ]
        if failed_checks and normalized_verdict == "pass":
            raise ValueError(
                "Review cannot pass while an AI Layer sandbox verification check is failing. "
                "Return changes_required with a finding, or rerun a corrected check."
            )
        input_normalizations.extend(verification_normalizations)
        if verification_still_open and normalized_verdict == "pass":
            normalized_verdict = "changes_required"
            input_normalizations.append("verdict:pass->changes_required(finding_still_open)")
    elif stage.kind == "implement":
        pass
    elif stage.kind == "fix":
        assert open_items is not None
        if open_items and normalized_outcome == "no_changes_needed":
            raise ValueError("Fix stage cannot return no_changes_needed while review findings remain open.")
        if not open_items:
            normalized_outcome = "no_changes_needed"
    else:
        raise RuntimeError(f"Unsupported task stage kind: {stage.kind}")
    return (
        normalized_outcome,
        normalized_verdict,
        normalized_findings,
        input_normalizations,
        pending_to_verify,
        verification_map,
    )
