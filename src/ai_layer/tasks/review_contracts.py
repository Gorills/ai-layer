from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import ReviewFinding, Task, utcnow
from ai_layer.core.redaction import redact_secrets
from ai_layer.observability.domain_events import append_event
from ai_layer.tasks.constants import (
    MAX_EXTERNAL_ACTIONS, MAX_EXTERNAL_TARGET_CHARS, MAX_EXTERNAL_TEXT_CHARS, MAX_FINDINGS,
    MAX_FINDING_PATH_CHARS, MAX_FINDING_TEXT_CHARS, MAX_VERIFICATION_EVIDENCE_CHARS,
    READ_ONLY_STAGES, REVIEW_VERDICT_ALIASES,
)
from ai_layer.tasks.contracts import _bounded_text
from ai_layer.tasks.views import _findings

def _normalize_external_actions(actions: list[dict] | None, *, stage_kind: str) -> list[dict]:
    raw_actions = list(actions or [])
    if len(raw_actions) > MAX_EXTERNAL_ACTIONS:
        raise ValueError(
            f"external_actions exceeds the {MAX_EXTERNAL_ACTIONS}-item limit; "
            "split the work into smaller stages instead of dropping audit evidence."
        )
    result: list[dict] = []
    for index, raw in enumerate(raw_actions, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"external action #{index} must be an object.")
        kind = str(raw.get("kind") or "").strip().lower().replace("-", "_")
        if kind not in {"verification", "mutation"}:
            raise ValueError(
                f"external action #{index} requires kind=verification or kind=mutation."
            )
        if stage_kind in READ_ONLY_STAGES and kind == "mutation":
            if stage_kind == "review":
                raise ValueError("Read-only review cannot record or perform external mutation actions.")
            raise ValueError("Read-only discovery cannot record or perform external mutation actions.")
        target = _bounded_text(
            raw.get("target"), field=f"external action #{index} target", max_chars=MAX_EXTERNAL_TARGET_CHARS, required=True
        )
        summary = _bounded_text(
            raw.get("summary"), field=f"external action #{index} summary", max_chars=MAX_EXTERNAL_TEXT_CHARS, required=True
        )
        evidence = _bounded_text(
            raw.get("evidence"), field=f"external action #{index} evidence", max_chars=MAX_EXTERNAL_TEXT_CHARS
        )
        result.append(
            {
                "kind": kind,
                "target": redact_secrets(target),
                "summary": redact_secrets(summary),
                "evidence": redact_secrets(evidence),
            }
        )
    return result


def _normalize_findings(findings: list[dict] | None) -> tuple[list[dict], list[str]]:
    raw_findings = list(findings or [])
    if len(raw_findings) > MAX_FINDINGS:
        raise ValueError(f"review findings exceeds the {MAX_FINDINGS}-item limit.")
    result = []
    normalizations: list[str] = []
    severity_aliases = {"warning": "medium", "major": "high", "minor": "low"}
    for index, raw in enumerate(raw_findings, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"review finding #{index} must be an object.")
        problem_key = next(
            (key for key in ("problem", "issue", "message", "description") if str(raw.get(key) or "").strip()),
            None,
        )
        problem = (
            _bounded_text(
                raw.get(problem_key), field=f"review finding #{index} problem", max_chars=MAX_FINDING_TEXT_CHARS, redact=True
            )
            if problem_key
            else ""
        )
        if not problem:
            raise ValueError(
                f"review finding #{index} requires a problem description; use `problem` "
                "(`issue`, `message`, and `description` are accepted aliases)."
            )
        if problem_key != "problem":
            normalizations.append(f"finding[{index}].{problem_key}->problem")

        severity_raw = str(raw.get("severity") or "medium").strip().lower()
        severity = severity_aliases.get(severity_raw, severity_raw)
        if severity != severity_raw:
            normalizations.append(f"finding[{index}].severity:{severity_raw}->{severity}")
        if severity not in {"critical", "high", "medium", "low"}:
            raise ValueError(
                f"review finding #{index} has unsupported severity `{severity_raw}`; "
                "use critical|high|medium|low."
            )

        path_key = next((key for key in ("path", "file_path", "file") if str(raw.get(key) or "").strip()), None)
        fix_key = next(
            (key for key in ("required_fix", "fix", "recommendation") if str(raw.get(key) or "").strip()),
            None,
        )
        if path_key and path_key != "path":
            normalizations.append(f"finding[{index}].{path_key}->path")
        if fix_key and fix_key != "required_fix":
            normalizations.append(f"finding[{index}].{fix_key}->required_fix")

        result.append(
            {
                "severity": severity,
                "category": str(raw.get("category") or "code").strip()[:64] or "code",
                "path": (
                    _bounded_text(
                        raw.get(path_key), field=f"review finding #{index} path", max_chars=MAX_FINDING_PATH_CHARS, redact=True
                    )
                    if path_key
                    else ""
                ),
                "problem": problem,
                "required_fix": (
                    _bounded_text(
                        raw.get(fix_key),
                        field=f"review finding #{index} required_fix",
                        max_chars=MAX_FINDING_TEXT_CHARS,
                        redact=True,
                    )
                    if fix_key
                    else ""
                ),
            }
        )
    return result, normalizations


def _normalize_review_submission(
    verdict: str | None, findings: list[dict] | None, *, allow_empty_changes_required: bool = False
) -> tuple[str, list[dict], list[str]]:
    raw_verdict = (verdict or "").strip().lower()
    normalized_verdict = REVIEW_VERDICT_ALIASES.get(raw_verdict)
    if normalized_verdict is None:
        raise ValueError(
            "Review verdict must mean `pass` or `changes_required`. Accepted aliases include "
            "passed/ok/approved and fail/failed/needs_changes/changes_requested."
        )
    normalizations: list[str] = []
    if normalized_verdict != raw_verdict:
        normalizations.append(f"verdict:{raw_verdict}->{normalized_verdict}")

    normalized_findings, finding_normalizations = _normalize_findings(findings)
    normalizations.extend(finding_normalizations)
    if normalized_verdict == "pass" and normalized_findings:
        normalized_verdict = "changes_required"
        normalizations.append("verdict:pass->changes_required(findings_present)")
    if normalized_verdict == "changes_required" and not normalized_findings and not allow_empty_changes_required:
        raise ValueError(
            "Review result means changes are required, but no structured findings were supplied. "
            "Add at least one finding with `problem` (or alias `issue`/`message`/`description`), "
            "or return verdict=`pass` when there are no actionable findings."
        )
    return normalized_verdict, normalized_findings, normalizations


def _normalize_verification_results(
    pending: list[ReviewFinding], verification_results: list[dict] | None
) -> tuple[dict[str, dict], list[str]]:
    """Require explicit, evidenced disposition of every finding awaiting verification."""
    if not pending:
        if verification_results:
            raise ValueError("verification_results were supplied but this review has no pending findings.")
        return {}, []
    if not verification_results:
        raise ValueError(
            "This review must return one verification_results entry for every pending finding id."
        )
    expected = {str(item.id): item for item in pending}
    result: dict[str, dict] = {}
    normalizations: list[str] = []
    aliases = {
        "verified": "verified", "pass": "verified", "passed": "verified", "fixed": "verified",
        "still_open": "still_open", "open": "still_open", "failed": "still_open", "not_fixed": "still_open",
    }
    for index, raw in enumerate(verification_results, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"verification result #{index} must be an object.")
        raw_id = str(raw.get("finding_id") or raw.get("id") or "").strip()
        if not raw_id or raw_id not in expected:
            raise ValueError(f"verification result #{index} references an unknown finding_id `{raw_id}`.")
        if raw_id in result:
            raise ValueError(f"verification result for finding `{raw_id}` was supplied more than once.")
        raw_status = str(raw.get("status") or raw.get("result") or "").strip().lower()
        status = aliases.get(raw_status)
        if status is None:
            raise ValueError(
                f"verification result for finding `{raw_id}` must be verified or still_open."
            )
        evidence = _bounded_text(
            raw.get("evidence") or raw.get("reason"),
            field=f"verification result for finding `{raw_id}` evidence",
            max_chars=MAX_VERIFICATION_EVIDENCE_CHARS,
            redact=True,
        )
        if not evidence:
            raise ValueError(f"verification result for finding `{raw_id}` requires concrete evidence.")
        if raw_status != status:
            normalizations.append(f"verification[{raw_id}]:{raw_status}->{status}")
        result[raw_id] = {"status": status, "evidence": evidence}
    missing = sorted(set(expected) - set(result))
    if missing:
        raise ValueError("verification_results missing pending finding ids: " + ", ".join(missing))
    return result, normalizations


def _apply_verification_results(
    db: Session, stage: TaskStage, pending: list[ReviewFinding], results: dict[str, dict]
) -> bool:
    still_open = False
    now = utcnow()
    for item in pending:
        result = results[str(item.id)]
        item.verification_evidence = result["evidence"]
        item.verified_by_stage_id = stage.id
        history = list(item.verification_history or [])
        history.append(
            {
                "stage_id": str(stage.id),
                "status": result["status"],
                "evidence": result["evidence"],
                "recorded_at": now.isoformat(),
            }
        )
        item.verification_history = history[-50:]
        if result["status"] == "verified":
            item.status = "verified"
            item.verified_at = now
            append_event(
                db, event_type="FindingVerified", project_id=None, aggregate_type="finding",
                aggregate_id=str(item.id), payload={"task_id": str(item.task_id), "stage_id": str(stage.id)},
            )
        else:
            item.status = "open"
            item.verified_at = None
            still_open = True
    return still_open


def _finding_signature(*, category: str, path: str, problem: str) -> tuple[str, str, str]:
    normalize = lambda value: " ".join(str(value or "").casefold().split())
    return normalize(category), normalize(path), normalize(problem)


def _add_findings(db: Session, task: Task, stage: TaskStage, findings: list[dict]) -> dict[str, int]:
    """Add genuinely new findings while reopening/reusing semantically identical records.

    Review history must remain durable, but the active working set should not grow simply because
    a later reviewer describes the same defect again. Exact normalized category/path/problem
    matches therefore reuse the original finding id and append a history event.
    """
    existing = _findings(db, task)
    by_signature = {
        _finding_signature(category=item.category, path=item.path, problem=item.problem): item
        for item in existing
    }
    stats = {"created": 0, "reused": 0, "regressions": 0}
    now = utcnow()
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for raw in findings:
        signature = _finding_signature(
            category=raw["category"], path=raw["path"], problem=raw["problem"]
        )
        prior = by_signature.get(signature)
        if prior is None:
            prior = ReviewFinding(
                task_id=task.id,
                stage_id=stage.id,
                severity=raw["severity"],
                category=raw["category"],
                path=raw["path"],
                problem=raw["problem"],
                required_fix=raw["required_fix"],
                status="open",
                provenance={
                    "opened_by_stage_id": str(stage.id),
                    "review_round": int(stage.review_round or 0),
                    "worker_id": stage.worker_id or None,
                    "source": "independent_review",
                },
            )
            db.add(prior)
            db.flush()
            append_event(
                db, event_type="FindingOpened", project_id=task.project_id, aggregate_type="finding",
                aggregate_id=str(prior.id), payload={
                    "task_id": str(task.id), "stage_id": str(stage.id), "severity": prior.severity,
                    "category": prior.category, "path": prior.path,
                },
            )
            by_signature[signature] = prior
            stats["created"] += 1
            continue

        was_verified = prior.status == "verified"
        prior.stage_id = stage.id
        if severity_rank.get(raw["severity"], 1) > severity_rank.get(prior.severity, 1):
            prior.severity = raw["severity"]
        if raw.get("required_fix"):
            prior.required_fix = raw["required_fix"]
        prior.status = "open"
        prior.verified_at = None
        prior.verified_by_stage_id = None
        prior.verification_evidence = ""
        provenance = dict(prior.provenance or {})
        reports = list(provenance.get("reports") or [])
        reports.append({"stage_id": str(stage.id), "worker_id": stage.worker_id or None, "recorded_at": now.isoformat()})
        provenance["reports"] = reports[-20:]
        prior.provenance = provenance
        history = list(prior.verification_history or [])
        history.append(
            {
                "stage_id": str(stage.id),
                "status": "regression" if was_verified else "re_reported",
                "evidence": "Reviewer reported the same normalized finding again; existing finding id was reused.",
                "recorded_at": now.isoformat(),
            }
        )
        prior.verification_history = history[-50:]
        stats["reused"] += 1
        if was_verified:
            stats["regressions"] += 1
    return stats


def _open_findings(db: Session, task: Task) -> list[ReviewFinding]:
    return db.scalars(
        select(ReviewFinding)
        .where(
            ReviewFinding.task_id == task.id,
            ReviewFinding.status.in_(["open", "pending_verification"]),
        )
        .order_by(ReviewFinding.created_at, ReviewFinding.id)
    ).all()


