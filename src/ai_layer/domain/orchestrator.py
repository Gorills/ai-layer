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
            "Represent substantive user work with WorkItem lifecycle. Short work normally needs only "
            "work_begin plus one terminal call; managed Tasks remain optional assurance."
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

- Start registered-project work with `project_status(project_root=<workspace root>)`. Apply its `project_policy` and use `work.current_focus` / `work.continuation` to interpret requests such as "continue" without rediscovering prior work.
- A substantive ordinary request is represented by one WorkItem. Use `work_begin` when new work starts and one terminal Work call when it ends. Use `work_checkpoint` only for a meaningful milestone or blocker, not every tool/file action. Managed Tasks are optional strict assurance and do not replace WorkItem identity.
- If the user already names a precise file or symbol, open that current source directly after status. Do not add search ceremony that cannot improve the answer.
- If the relevant code location is unknown, call `project_search` before broad repository grep/search. For non-English natural-language intent, make the primary query concise English and code-centric while preserving exact repository identifiers; use at most one original-language/mixed variant when it materially widens domain recall. Treat returned paths/symbols as breadcrumbs and inspect current source.
- For end-to-end flow questions, do not stop at the first hit: establish the relevant entrypoint/handler, core service/domain, persistence or external integration, and tests before claiming the flow is complete.
- Project Map is read with `project_search` and updated/reviewed with `project_map_reconcile`. Reconcile only inspected scope and use `no_changes_reason` when existing semantics are already accurate.
- Use `knowledge_search` for reviewed project facts/invariants and `decision_search` for architectural history only when relevant. They are not substitutes for current source.
- Native read/edit/search/shell/test/subagent capabilities remain available. AI Layer does not grant per-edit permission and must not replace the host's own agent loop.
- Existing managed Tasks and Epics remain durable strict workflows. When status reports one as the current managed focus, or the user explicitly chooses managed execution, use `task_next` / `epic_next` and follow that workflow's strict contracts.
- Never stash, reset, restore, discard or commit user changes merely to satisfy AI Layer; a dirty worktree is valid project state.
- If AI Layer state/index retrieval fails, disclose the missing context and continue with native source inspection when safe. Never fabricate Work/Task/Epic/Knowledge state.
"""


def native_bootstrap_markdown() -> str:
    """Small always-on bootstrap: retrieve useful state, then let the host work natively."""
    startup = """## Mandatory project-intelligence startup

For work involving a registered project:

1. The first AI Layer project-state call MUST be `project_status(project_root=<workspace root>)` before implementation or broad repository discovery. Apply `project_policy.text` when present; its version/hash identifies the delivered policy revision.
2. Read `work.current_focus` and `work.continuation`. If the user says "continue" (or equivalent), resume that exact live Work/managed Task/Epic instead of reconstructing state from chat or rescanning the repository.
3. For a new substantive request call `work_begin` once. Short work should normally use only `work_begin` plus one of `work_complete`, `work_fail`, `work_interrupt`, or `work_abandon`; use `work_checkpoint` only at a meaningful milestone/blocker. Managed Task is optional assurance, not ordinary-work identity.
4. If the relevant file/symbol is already known from the user or status, inspect it directly with host-native tools.
5. If code location is unknown, call `project_search` before broad grep/find/repository exploration. For non-English natural-language goals, derive a concise English code-centric primary query and preserve exact paths/symbols/routes/config keys/env keys/error strings/tables/fields verbatim. Use at most one original-language or mixed `query_variants` entry when domain aliases or weak coverage justify widening.
6. Treat Project Map results as breadcrumbs only. If semantic search is degraded or the result is implausible, retry with English code-centric terms if needed and then perform one bounded native exact-token search. For end-to-end flows cover entrypoint/handler, core service/domain, persistence/external integration and relevant tests before declaring the flow understood.
7. Project Map reads use `project_search`; Project Map updates/reviews use `project_map_reconcile`. Inspect only relevant current source and reconcile checked scope. For a completed managed Task/Epic pass its Task key as `source_task_key`; if no semantic change is needed, record `no_changes_reason` rather than inventing entries.
8. Use `knowledge_search` for durable reviewed facts/invariants and `decision_search` for prior architectural decisions when those facts can materially affect the task. Do not call them mechanically.
9. Execute normally through the host: native reads, edits, shell, tests, code search and subagents are allowed. Prefer the smallest sufficient exploration and cheapest adequate execution path.
10. Managed Tasks/Epics are optional durable assurance workflows, not a universal permission layer. Call `task_next` / `epic_next` when resuming an already-managed focus or when managed/strict execution is explicitly chosen.
11. Current repository source is final code truth. Project Map is a navigation index; Project Knowledge is reviewed semantic memory; Decisions explain prior choices. Verify relevant current source before edits or code-truth claims.
12. Agent Skills are selected by the host natively. Do not manually preload unrelated skills. Use `skill_get` only for explicit retrieval/package details when host-native skill activation is insufficient.

Token-economy objective: use AI Layer to avoid rediscovering known project structure and state, not to add ceremony. A control-plane call is justified only when it reduces uncertainty, preserves durable state, or supplies evidence the host would otherwise have to reconstruct.
"""
    return (
        critical_orchestrator_markdown()
        + "\n"
        + agent_runtime_bootstrap_line()
        + "\n\n"
        + startup
        + "\n"
        + static_policy_markdown()
    )


def mcp_bootstrap_instructions() -> str:
    """Compact fallback when native bootstrap delivery is unavailable or drifted."""
    return agent_runtime_bootstrap_line()


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
