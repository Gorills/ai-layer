from __future__ import annotations

from typing import Any

from ai_layer.domain.agent_contract import (
    AGENT_RUNTIME_CONTRACT_VERSION,
    agent_runtime_bootstrap_line,
)
from ai_layer.domain.project_map import project_map_bootstrap_line
from ai_layer.domain.static_policy import static_policy_markdown

CRITICAL_ORCHESTRATOR_CONTRACT_VERSION = 9


def critical_orchestrator_contract() -> dict[str, Any]:
    """Host-neutral always-on contract for the Project Intelligence control plane."""
    return {
        "version": CRITICAL_ORCHESTRATOR_CONTRACT_VERSION,
        "agent_runtime_contract_version": AGENT_RUNTIME_CONTRACT_VERSION,
        "role": "host_native_engineer",
        "authority": "host_native_execution",
        "repository_mutation": "host_native",
        "external_mutation": "host_native_subject_to_user_permissions",
        "startup_rule": "Call project_status before beginning registered-project work.",
        "work_rule": (
            "When project_status continuation.kind is none, explicit user Task/standard-Task-protocol intent "
            "goes directly to task_create; otherwise substantive work starts with work_begin. Backing Work for "
            "managed Tasks is automatic."
        ),
        "discovery_rule": (
            "When code location is unknown, use a concise English code-centric project_search query for "
            "non-English goals, preserve exact identifiers, and use at most one original/mixed widening variant."
        ),
        "project_map_rule": project_map_bootstrap_line(),
        "project_policy_rule": "Apply project_status.project_policy before implementation.",
        "source_truth": "Current repository source is authoritative; Project Map and Knowledge are shortcuts.",
        "skills_rule": "Use host-native Agent Skills by relevance; do not preload unrelated skills.",
        "managed_workflow_rule": (
            "Task/Epic navigators are authoritative only after a managed Task/Epic is explicitly active or selected."
        ),
        "failure_rule": (
            "If Project Intelligence is temporarily unavailable, report that loss of context and continue with "
            "host-native source inspection rather than inventing state or becoming blocked by the control plane."
        ),
    }


def managed_orchestrator_contract() -> dict[str, Any]:
    """Coordinator boundary that applies only while an explicit managed Task is active."""
    return {
        "version": CRITICAL_ORCHESTRATOR_CONTRACT_VERSION,
        "agent_runtime_contract_version": AGENT_RUNTIME_CONTRACT_VERSION,
        "role": "orchestrator",
        "authority": "managed_task_coordination",
        "repository_mutation": "forbidden",
        "external_mutation": "forbidden",
        "scope": "active_managed_task_only",
        "worker_rule": (
            "Delegated IMPLEMENT/FIX belongs to the bound writable worker; delegated DISCOVERY/REVIEW "
            "belongs to the bound read-only worker."
        ),
        "evidence_rule": "Record actual worker/check evidence only; never fabricate stage execution.",
        "exit_rule": "The global host-native execution contract resumes outside this managed Task.",
    }


def critical_orchestrator_markdown() -> str:
    return """## AI Layer control-plane boundary

AI Layer provides Project Intelligence, durable ordinary-work state, optional managed assurance, professional skills, verification evidence and observability. The host agent runtime remains the execution engine.

- Start registered-project work with `project_status(project_root=<workspace root>)` before implementation or broad discovery. Apply `project_policy.text` when present; its version/hash identifies the delivered revision. Use `work.current_focus` / `work.continuation` to interpret "continue" without rediscovering prior work.
- After `project_status`, if `work.continuation.kind` is `none`, route by user intent: an explicit managed Task / standard Task protocol request calls `task_create` directly; otherwise substantive work (implement, diagnose, review, research, multi-step investigation, live checks) starts with `work_begin`. AI Layer creates or links backing Work for managed Tasks automatically. Tiny one-shot Q&A with no durable value may stay unmaterialized. Ordinary Work closes with one terminal Work call; use `work_checkpoint` only for a meaningful milestone or blocker.
- If the user already names a precise file or symbol, open that current source directly after status.
- If the relevant code location is unknown, call `project_search` before broad repository grep/search. For non-English natural-language intent, derive a concise English code-centric primary query and preserve exact identifiers; pass at most one original-language or mixed `query_variants` entry when it materially widens domain recall. Treat returned paths/symbols as breadcrumbs and inspect current source. If semantic search is degraded or implausible, retry with English code-centric terms, then one bounded native exact-token search. For end-to-end flows cover entrypoint/handler, core service/domain, persistence/external integration and tests before claiming the flow is complete.
- Project Map is read with `project_search` and updated with `project_map_reconcile`. Reconcile only inspected scope. Pass `source_work_key` for ordinary Work closure or `source_task_key` for a completed managed Task/Epic, never both; if no semantic change is needed, record `no_changes_reason`.
- Use `knowledge_search` for reviewed project facts/invariants and `decision_search` for architectural history only when relevant. They are not substitutes for current source.
- Native read/edit/search/shell/test/subagent capabilities remain available. Prefer the smallest sufficient exploration. AI Layer does not grant per-edit permission and must not replace the host's own agent loop.
- Existing managed Tasks and Epics remain durable strict workflows. Resume an active managed focus with `task_next` / `epic_next`; for a new explicit managed Task request, start with `task_create` and follow its returned live next action.
- Never stash, reset, restore, discard or commit user changes merely to satisfy AI Layer; a dirty worktree is valid project state.
- If AI Layer state/index retrieval fails, disclose the missing context and continue with native source inspection when safe. Never fabricate Work/Task/Epic/Knowledge state.
- Agent Skills are selected by the host natively. Do not preload unrelated skills. Use `skill_get` only when host-native activation is insufficient.
- A control-plane call is justified only when it reduces uncertainty, preserves durable state, or supplies evidence the host would otherwise reconstruct.

Current repository source is final code truth. Project Map is a navigation index; Project Knowledge is reviewed semantic memory; Decisions explain prior choices.
"""


def native_bootstrap_markdown() -> str:
    """Single always-on procedure copy plus the durable engineering floor."""
    return critical_orchestrator_markdown() + "\n" + static_policy_markdown()


def mcp_bootstrap_instructions() -> str:
    """Compact fallback when native bootstrap delivery is unavailable or drifted."""
    return (
        "If native AI Layer bootstrap is not already in context: " + agent_runtime_bootstrap_line()
    )


def inline_micro_stage_instruction() -> dict[str, Any]:
    """Temporary top-level mutation authority retained for legacy/strict MICRO Task execution."""
    return {
        "role": "inline_micro_implementer",
        "authority": "temporary_current_stage_only",
        "repository_mutation": "allowed_current_micro_stage_only",
        "external_mutation": "forbidden",
        "stage": "implement",
        "mandatory": (
            "Implement only the localized managed Task, run the narrowest relevant check, then call "
            "task_implementation_complete. AI Layer will inspect the actual repository delta before accepting "
            "MICRO completion."
        ),
        "completion_precondition": (
            "The top-level actor actually performed the current inline MICRO change and has real verification "
            "evidence to report."
        ),
        "escalation": (
            "If the actual diff exceeds the MICRO envelope or hits a protected condition, AI Layer converts the "
            "managed task to STANDARD and requires an independent delegated review."
        ),
        "failure": (
            "If the managed task is no longer localized or low-impact, stop broadening the edit and let the "
            "strict workflow escalate it."
        ),
    }


def orchestrator_stage_instruction(
    *, stage_kind: str, delegated: bool, worker_id: str | None = None
) -> dict[str, Any]:
    """Strict managed-Task stage contract, intentionally separate from the global host-native contract."""
    if delegated:
        return {
            "role": "managed_task_orchestrator",
            "repository_mutation": "forbidden_during_delegated_stage",
            "external_mutation": "forbidden_during_delegated_stage",
            "stage": stage_kind,
            "worker_id": worker_id,
            "mandatory": (
                "Use the actual result of the already-bound worker. If that worker has not actually been started "
                "yet, start it now. Do not perform this strict managed stage yourself."
            ),
            "completion_precondition": (
                "The bound worker actually ran this stage and returned the evidence being recorded."
            ),
            "failure": (
                "If the bound strict-stage worker cannot run or fails, report/block that managed stage; do not "
                "fabricate a worker result."
            ),
        }
    return {
        "role": "managed_task_orchestrator",
        "repository_mutation": "forbidden_during_delegated_stage",
        "external_mutation": "forbidden_during_delegated_stage",
        "stage": stage_kind,
        "mandatory": (
            "Bind a fresh worker for this strict managed stage, then start that worker. The global host-native "
            "execution contract resumes outside this explicit managed stage."
        ),
        "failure": (
            "If strict-stage delegation cannot proceed, report/block the managed stage rather than inventing "
            "delegation history."
        ),
    }
