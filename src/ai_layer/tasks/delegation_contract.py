from __future__ import annotations

from ai_layer.db.models import Task, TaskStage
from ai_layer.tasks.contracts import _stage_agent_policy
from ai_layer.tasks.state_store import task_key


def _worker_role_contract(stage_kind: str) -> str:
    if stage_kind in {"implement", "fix"}:
        return "This delegated worker is the only actor allowed to perform repository/external mutations for this stage."
    return "This delegated worker is read-only and must not mutate repository/external state."


def _expertise_contract() -> dict:
    return {
        "routing_owner": "The host agent's native Agent Skills mechanism owns skill relevance and activation. AI Layer does not provide a parallel required/recommended/on-demand plan.",
        "authoritative_content": "When a native skill activates, retrieve the smallest relevant authoritative AI Layer section with skill_get instead of guessing or eagerly loading unrelated domain guidance.",
        "progressive_retrieval": "Prefer an exact section; request full skill content only when targeted sections are insufficient. Host automatic-vs-manual activation is not observable by AI Layer.",
    }


def _knowledge_review_contract(task: Task) -> dict:
    return {
        "source_task_id": str(task.id),
        "tool": "knowledge_list",
        "rule": (
            "Inspect DRAFT Project Knowledge cards for this task when present. Verify each semantic claim "
            "against the cited current repository evidence; a passing review publishes those drafts."
        ),
    }


def _provenance_notice(task: Task) -> str | None:
    if (task.execution_origin or "managed") == "adopted_unmanaged_changes":
        return (
            "Repository changes predate this managed task; review/remediate them without claiming "
            "AI Layer executed the original implementation."
        )
    if int((task.preexisting_changes or {}).get("total") or 0):
        return (
            "This task started from a dirty worktree captured as an immutable baseline. Preserve pre-existing edits. "
            "Managed task delta is measured against that baseline, not Git HEAD. Never stash/reset/restore/commit "
            "pre-existing work merely to satisfy AI Layer workflow."
        )
    return None


def build_delegation_contract(
    task: Task, stage: TaskStage, open_findings: list[dict], completion_contract: dict
) -> dict:
    contract: dict[str, object] = {
        "task": task_key(task),
        "stage_id": str(stage.id),
        "stage": stage.kind,
        "role": {
            "implement": "implementer",
            "review": "reviewer",
            "fix": "fixer",
            "discovery": "discovery",
        }.get(stage.kind),
        "goal": task.goal,
        "acceptance_criteria": list(task.acceptance_criteria or []),
        "constraints": list(task.constraints or []),
        "execution_origin": task.execution_origin or "managed",
        "workflow": {
            "version": int(task.workflow_version or 1),
            "profile": task.workflow_profile or "legacy_standard",
        },
        "risk": {"level": task.risk_level or "normal", "reasons": list(task.risk_reasons or [])},
        "cost_policy": task.cost_policy or "economy",
        "agent_policy": _stage_agent_policy(stage),
        "discovery_result": dict(task.discovery_result or {}),
        "adopted_changes": dict(task.adopted_changes or {}),
        "preexisting_changes": dict(task.preexisting_changes or {}),
        "fresh_subagent_required": True,
        "orchestrator_edits_forbidden": True,
        "orchestrator_fallback_forbidden": True,
        "worker_role_contract": _worker_role_contract(stage.kind),
        "task_state_tools_forbidden_for_worker": True,
        "return_to_orchestrator": "Return actual stage evidence/results only; the parent records the transition and must never perform or finish this stage on your behalf.",
        "worker_id_requirement": "Use a new stable label for this delegated worker; labels cannot be reused inside one task.",
        "identity_enforcement": "AI Layer enforces label uniqueness and discovery/reviewer read-only managed-repository identity; the current host protocol does not expose authenticated native-subagent identity, so actor independence is a protocol requirement rather than a cryptographic guarantee.",
        "check_evidence_assurance": "Stage checks are worker-reported evidence. AI Layer requires them but does not independently execute arbitrary reported host commands.",
        "external_action_policy": {
            "verification": "Read-only shell/HTTP/staging observations may be performed by the delegated worker and recorded as verification evidence.",
            "mutation": "Any external system mutation required by acceptance belongs to the delegated implementer/fixer stage, not the orchestrator, and must be declared in external_actions.",
            "read_only_stages": "Discovery/review may record only verification actions; external mutations are forbidden.",
            "assurance": "AI Layer can audit declared external actions but cannot independently detect mutations made outside its tools/host protocol.",
        },
        "expertise_contract": _expertise_contract(),
    }
    provenance_notice = _provenance_notice(task)
    if provenance_notice:
        contract["provenance_notice"] = provenance_notice

    if stage.kind == "discovery":
        contract.update(
            {
                "repository_mode": "read-only",
                "context_policy": {
                    "mode": "isolated_discovery",
                    "include": [
                        "task goal and constraints",
                        "current source/project intelligence",
                        "host-selected relevant skill instructions",
                        "read-only verification evidence",
                    ],
                    "exclude": [
                        "implementation assumptions presented as facts",
                        "full orchestration transcript when isolated context is available",
                    ],
                },
                "requirements": [
                    "Investigate the actual repository before proposing implementation.",
                    "Separate verified facts from hypotheses and risks.",
                    "Return a compact proposed plan/acceptance refinements when implementation is warranted.",
                    "Do not modify repository files or external state.",
                ],
            }
        )
    elif stage.kind == "review":
        pending_verification = [
            item for item in open_findings if item.get("status") == "pending_verification"
        ]
        contract.update(
            {
                "repository_mode": "read-only",
                "review_round": stage.review_round,
                "findings_to_verify": pending_verification,
                "project_knowledge_review": _knowledge_review_contract(task),
                "context_policy": {
                    "mode": "isolated_review",
                    "include": [
                        "task goal and acceptance criteria",
                        "task constraints",
                        "current repository state and diff",
                        "relevant project evidence",
                        "pending finding IDs requiring verification",
                    ],
                    "exclude": [
                        "implementer/fixer self-assessment",
                        "prior reviewer conclusions except pending finding records",
                        "parent/orchestrator persuasion or full transcript",
                    ],
                    "host_requirement": "Start the reviewer from this compact contract plus repository access; do not inject the full orchestration transcript when the host supports isolated subagent context.",
                },
                "requirements": [
                    "Inspect the actual implementation and relevant tests.",
                    "Explicitly verify every finding_to_verify against the current repository state and return one verification_results entry per finding id with evidence.",
                    "Run appropriate verification checks. If checks may write caches/test artifacts, use the AI Layer review sandbox instead of the canonical repository.",
                    "Assess documentation impact from the actual diff. Changes to configuration, setup, deployment, public API, persistence/media, migrations requiring operator action, or runtime processes must update the existing owning docs/examples when such documentation exists; internal-only changes do not require documentation churn.",
                    "Call knowledge_list(status=DRAFT, source_task_id=project_knowledge_review.source_task_id) and independently verify any returned Project Knowledge cards; unsupported or incomplete claims are actionable findings.",
                    "Do not modify repository files.",
                    "Return verdict=pass only when no actionable findings remain.",
                ],
            }
        )
    elif stage.kind == "fix":
        contract.update(
            {
                "repository_mode": "write",
                "fix_round": stage.fix_round,
                "open_findings": open_findings,
                "requirements": [
                    "Address the review findings without broad unrelated changes.",
                    "Apply documentation-impact fixes only when the changed external/developer/operator contract requires them; update the existing owning document rather than creating parallel guidance.",
                    "If there are no findings, verify that no fix is needed and complete as no_changes_needed.",
                ],
            }
        )
    else:
        contract.update(
            {
                "repository_mode": "write",
                "requirements": [
                    "Implement the task contract completely.",
                    "Use knowledge_draft_upsert only when the task explicitly requires creating/updating Project Knowledge; never turn ordinary coding work into automatic documentation generation.",
                    "Add or update tests appropriate to the change.",
                    "Assess documentation impact: update existing setup/config/deploy/API/storage/migration/runtime documentation or safe examples when the task changes those contracts; do not churn docs for internal-only changes.",
                    "Run focused verification before returning to the orchestrator.",
                ],
            }
        )
    contract["completion_contract"] = completion_contract
    return contract
