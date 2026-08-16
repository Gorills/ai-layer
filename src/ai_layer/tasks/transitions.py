from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, ReviewFinding, RuntimeEvent, Task, TaskStage, utcnow
from ai_layer.memory.knowledge_store import has_task_drafts, publish_task_drafts
from ai_layer.observability.work_events import append_task_event
from ai_layer.privacy.service import privacy_check
from ai_layer.sessions.service import save_session
from ai_layer.tasks.concurrency import bump_task_version
from ai_layer.tasks.constants import (
    HIGH_RISK_TERMS,
    HUMAN_ATTENTION_PREFIX,
    MAX_AUTOMATIC_FIX_ROUNDS,
)
from ai_layer.tasks.contracts import _contains_any
from ai_layer.tasks.micro_policy import micro_envelope as _micro_envelope
from ai_layer.tasks.review_contracts import (
    _add_findings,
    _apply_verification_results,
    _open_findings,
)
from ai_layer.tasks.state_store import load_baseline as _load_baseline
from ai_layer.tasks.state_store import task_key
from ai_layer.tasks.views import (
    _create_stage,
    _findings,
    _remediation_fix_count,
    _stage_label,
    _stages,
)
from ai_layer.workspace.repository import repository_changes


def _knowledge_review_inspected(db: Session, stage: TaskStage) -> bool:
    return (
        db.scalar(
            select(RuntimeEvent.id)
            .where(
                RuntimeEvent.event_type == "KnowledgeReviewInspected",
                RuntimeEvent.aggregate_type == "knowledge_review",
                RuntimeEvent.aggregate_id == str(stage.id),
            )
            .limit(1)
        )
        is not None
    )


def _complete_task(
    db: Session, project: Project, task: Task, final_state: dict, summary: str
) -> None:
    baseline = _load_baseline(db, project, task)
    task.final_changes = repository_changes(baseline, final_state)
    task.status = "completed"
    task.blocked_reason = ""
    adopted_origin = (task.execution_origin or "managed") == "adopted_unmanaged_changes"
    task.completion_summary = summary.strip() or (
        "Adopted unmanaged changes passed mandatory review/remediation verification."
        if adopted_origin
        else f"Adaptive {task.workflow_profile or 'standard'} workflow completed."
    )
    task.completed_at = utcnow()
    bump_task_version(task)
    task.updated_at = utcnow()

    stages = _stages(db, task)
    actions = [
        f"{_stage_label(stage)}: {stage.summary.strip()}"
        for stage in stages
        if stage.status == "completed" and stage.summary.strip()
    ][-12:]
    external_action_facts = [
        f"{_stage_label(stage)} external {action.get('kind')}: {action.get('target')} — {action.get('summary')}"
        for stage in stages
        for action in list(stage.external_actions or [])
        if stage.status == "completed" and action.get("kind") and action.get("target")
    ][-12:]
    actions.extend(external_action_facts)
    resolved_findings = [
        (
            f"[{item.severity}] {item.path + ': ' if item.path else ''}{item.problem} "
            f"(status={item.status})"
        )
        for item in _findings(db, task)[-20:]
    ]
    final_changes = task.final_changes or {}
    delta_label = "Managed post-adoption delta" if adopted_origin else "Final repository delta"
    change_fact = (
        f"{delta_label}: {final_changes.get('total', 0)} file(s) changed "
        f"({len(final_changes.get('added') or [])} added, "
        f"{len(final_changes.get('modified') or [])} modified, "
        f"{len(final_changes.get('deleted') or [])} deleted)."
    )
    verified_facts = [
        f"Workflow profile {task.workflow_profile or 'legacy_standard'} completed with {task.review_round} review round(s) and {task.fix_round} fix round(s).",
        change_fact,
    ]
    preexisting = dict(task.preexisting_changes or {})
    if int(preexisting.get("total") or 0):
        verified_facts.append(
            f"Task started from a captured dirty worktree baseline containing {int(preexisting.get('total') or 0)} pre-existing changed path(s); final repository delta is measured from that baseline, not Git HEAD."
        )
    knowledge_publication = {"published": 0, "superseded": 0}
    reviewed = any(
        stage.kind == "review" and stage.status == "completed" and stage.outcome == "pass"
        for stage in stages
    )
    if reviewed:
        knowledge_publication = publish_task_drafts(db, project, str(task.id))
    elif has_task_drafts(db, project, str(task.id)):
        verified_facts.append(
            "Project Knowledge drafts were not published because this workflow had no independent passing review."
        )
    if knowledge_publication["published"]:
        verified_facts.append(
            f"Published {knowledge_publication['published']} reviewed Project Knowledge card(s); "
            f"superseded {knowledge_publication['superseded']} older verified version(s)."
        )
        append_task_event(
            db,
            task=task,
            event_type="KnowledgePublished",
            project=project,
            aggregate_type="task",
            aggregate_id=str(task.id),
            payload=knowledge_publication,
        )
    if external_action_facts:
        verified_facts.append(
            f"Task stages declared {len(external_action_facts)} external action(s); these are audit declarations, not independently detected host mutations."
        )
    current_state_text = f"{task_key(task)} completed through workflow profile {task.workflow_profile or 'legacy_standard'}."
    if adopted_origin:
        adopted = dict(task.adopted_changes or {})
        verified_facts.insert(
            0,
            "This task adopted pre-existing unmanaged repository changes for review/remediation; "
            f"AI Layer did not claim the original implementation stage. Git dirty paths at adoption: {adopted.get('total', 0)}.",
        )
        current_state_text = (
            f"{task_key(task)} completed after adopting unmanaged changes and passing the managed "
            "review/remediation pipeline; no managed implementation stage was claimed."
        )
    handoff = save_session(
        db,
        project,
        goal=task.goal,
        completed_actions=actions,
        current_state=current_state_text,
        next_steps=[],
        important_decisions=[],
        verified_facts=verified_facts,
        notable_findings=resolved_findings,
    )
    task.handoff_session_id = str(handoff.id)


def _privacy_findings(project: Project) -> list[dict]:
    result = privacy_check(project.root_path)
    if result.get("ok", True):
        return []
    findings = []
    for violation in (result.get("violations") or [])[:50]:
        path = str(violation.get("path") or "")
        code = str(violation.get("code") or "privacy_violation")
        line = violation.get("line")
        location = f"{path}:{line}" if line else path
        findings.append(
            {
                "severity": "high",
                "category": "privacy",
                "path": path,
                "problem": f"Privacy gate failed at {location or 'repository'} ({code}).",
                "required_fix": "Remove the privacy/provenance violation and run the mandatory review again.",
            }
        )
    return findings or [
        {
            "severity": "high",
            "category": "privacy",
            "path": "",
            "problem": "Strict-private privacy gate failed.",
            "required_fix": "Resolve privacy violations before task completion.",
        }
    ]


def _advance_discovery(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    current_state: dict,
    summary: str,
    outcome: str,
    result_data: dict,
) -> TaskStage | None:
    stage.status = "completed"
    stage.outcome = outcome
    task.discovery_result = {
        "summary": summary,
        "verified_facts": list(result_data.get("verified_facts") or []),
        "risks": list(result_data.get("risks") or []),
        "proposed_plan": list(result_data.get("proposed_plan") or []),
        "proposed_acceptance_criteria": list(result_data.get("proposed_acceptance_criteria") or []),
        "completed_at": utcnow().isoformat(),
    }
    if outcome != "ready_for_implementation":
        _complete_task(db, project, task, current_state, summary)
        return None
    discovery_text = " ".join(
        [
            *list(result_data.get("risks") or []),
            *list(result_data.get("proposed_plan") or []),
        ]
    ).casefold()
    if _contains_any(discovery_text, HIGH_RISK_TERMS) and task.risk_level != "high":
        task.risk_level = "high"
        task.risk_reasons = [
            *list(task.risk_reasons or []),
            "discovery identified a high-risk implementation domain",
        ]
    return _create_stage(db, task, kind="implement", state=current_state)


def _advance_review(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    current_state: dict,
    summary: str,
    verdict: str,
    findings: list[dict],
    pending_to_verify: list[ReviewFinding],
    verification_map: dict[str, dict],
    input_normalizations: list[str],
) -> TaskStage | None:
    if (
        verdict == "pass"
        and has_task_drafts(db, project, str(task.id))
        and not _knowledge_review_inspected(db, stage)
    ):
        raise RuntimeError(
            "PROJECT_KNOWLEDGE_REVIEW_REQUIRED: this task has DRAFT Project Knowledge. "
            "The delegated reviewer must call knowledge_list(status='DRAFT', source_task_id=<task_id>) "
            "during this review stage before a passing verdict can publish it."
        )
    stage.status = "completed"
    stage.outcome = verdict
    task.review_round = max(task.review_round, stage.review_round)
    if verdict == "changes_required":
        if pending_to_verify:
            _apply_verification_results(db, task, stage, pending_to_verify, verification_map)
        finding_stats = _add_findings(db, task, stage, findings)
        if any(finding_stats.values()):
            input_normalizations.append(
                "finding_lifecycle:"
                f"created={finding_stats['created']},reused={finding_stats['reused']},"
                f"regressions={finding_stats['regressions']}"
            )
        remediation_count = _remediation_fix_count(db, task)
        if remediation_count >= MAX_AUTOMATIC_FIX_ROUNDS:
            task.status = "blocked"
            task.blocked_reason = (
                HUMAN_ATTENTION_PREFIX
                + f" Automatic remediation stopped after {remediation_count} remediation attempt(s). "
                "Actionable findings remain; inspect the active finding set before explicitly resuming."
            )
            return None
        task.fix_round += 1
        return _create_stage(db, task, kind="fix", state=current_state, fix_round=task.fix_round)

    if pending_to_verify:
        _apply_verification_results(db, task, stage, pending_to_verify, verification_map)
    db.flush()
    if _open_findings(db, task):
        raise RuntimeError("Review passed while actionable findings still remain.")
    privacy_findings = _privacy_findings(project)
    if privacy_findings:
        _add_findings(db, task, stage, privacy_findings)
        task.fix_round += 1
        return _create_stage(db, task, kind="fix", state=current_state, fix_round=task.fix_round)
    if int(task.workflow_version or 1) < 2 and not (
        stage.review_round >= 2 and task.fix_round >= 1
    ):
        task.fix_round += 1
        return _create_stage(db, task, kind="fix", state=current_state, fix_round=task.fix_round)
    _complete_task(db, project, task, current_state, summary)
    return None


def _advance_implement(
    db: Session,
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    current_state: dict,
    summary: str,
    changes: dict,
    external_actions: list[dict],
) -> TaskStage | None:
    stage.status = "completed"
    stage.outcome = "done"
    if task.workflow_profile == "micro" and int(task.workflow_version or 1) >= 2:
        eligible, reasons = _micro_envelope(project, task, changes, external_actions)
        privacy_findings = _privacy_findings(project) if eligible else []
        if eligible and not privacy_findings:
            _complete_task(db, project, task, current_state, summary)
            return None
        task.workflow_profile = "standard"
        task.risk_level = "normal" if task.risk_level == "low" else task.risk_level
        if privacy_findings:
            task.risk_reasons = [
                *list(task.risk_reasons or []),
                "micro escalation: privacy gate produced actionable findings",
            ]
            _add_findings(db, task, stage, privacy_findings)
            task.fix_round += 1
            return _create_stage(
                db, task, kind="fix", state=current_state, fix_round=task.fix_round
            )
        task.risk_reasons = [
            *list(task.risk_reasons or []),
            *[f"micro escalation: {reason}" for reason in reasons],
        ]
    task.review_round = max(task.review_round, 1)
    return _create_stage(
        db, task, kind="review", state=current_state, review_round=task.review_round
    )


def _advance_fix(
    db: Session,
    task: Task,
    stage: TaskStage,
    *,
    current_state: dict,
    outcome: str,
    open_items: list[ReviewFinding],
) -> TaskStage:
    for item in open_items:
        if item.status == "open":
            item.status = "pending_verification"
    stage.status = "completed"
    stage.outcome = outcome
    next_review = max(task.review_round + 1, 2)
    task.review_round = next_review
    return _create_stage(db, task, kind="review", state=current_state, review_round=next_review)
