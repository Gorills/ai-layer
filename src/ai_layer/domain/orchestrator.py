from __future__ import annotations

from typing import Any

from ai_layer.domain.static_policy import static_policy_markdown

CRITICAL_ORCHESTRATOR_CONTRACT_VERSION = 6


def critical_orchestrator_contract() -> dict[str, Any]:
    """Host-neutral always-on contract for the Project Intelligence control plane."""
    return {
        "version": CRITICAL_ORCHESTRATOR_CONTRACT_VERSION,
        "role": "host_native_engineer",
        "authority": "host_native_execution",
        "repository_mutation": "host_native",
        "external_mutation": "host_native_subject_to_user_permissions",
        "startup_rule": "Call project_status before beginning registered-project work.",
        "discovery_rule": (
            "When the relevant code location is unknown, call project_search before broad repository discovery."
        ),
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


def critical_orchestrator_markdown() -> str:
    return """## AI Layer control-plane boundary

AI Layer provides Project Intelligence, durable work state, professional skills, verification evidence and observability. The host agent runtime remains the execution engine.

- Start registered-project work with `project_status(project_root=<workspace root>)`. Use the returned `current_focus` to interpret requests such as "continue" without rediscovering prior work.
- If the user already names a precise file or symbol, open that current source directly after status. Do not add a search ceremony that cannot improve the answer.
- If the relevant code location is unknown, call `project_search(query=<actual goal>)` before broad repository grep/search. Treat its paths and symbols as breadcrumbs, then inspect current source with native tools.
- Use `knowledge_search` for reviewed project facts/invariants and `decision_search` for architectural history only when they are relevant. They are not substitutes for current source.
- Native read/edit/search/shell/test/subagent capabilities remain available. AI Layer does not grant per-edit permission and must not replace the host's own agent loop.
- Existing managed Tasks and Epics remain durable workflows. When `project_status` reports one as the current focus, or when the user explicitly chooses managed execution, use `task_next` / `epic_next` and follow that workflow's strict contracts.
- If AI Layer state/index retrieval fails, disclose the missing context and continue with native source inspection when safe. Never fabricate Task/Epic/Knowledge state.
"""


def native_bootstrap_markdown() -> str:
    """Small always-on bootstrap: retrieve useful state, then let the host work natively."""
    startup = """## Mandatory project-intelligence startup

For work involving a registered project:

1. The first AI Layer project-state call MUST be `project_status(project_root=<workspace root>)` before implementation or broad repository discovery.
2. Read its `work.current_focus` and `work.continuation`. If the user says "continue" (or equivalent) and a managed Task/Epic is active, resume that exact work instead of reconstructing state from chat or rescanning the repository.
3. If the relevant file/symbol is already known from the user or status, inspect it directly with host-native tools.
4. If the code location is unknown, call `project_search(query=<actual user goal>, project_root=<canonical root>)` before broad grep/find/repository exploration. Open only the strongest current-source candidates first and widen only when evidence requires it.
5. Use `knowledge_search` for durable reviewed facts/invariants and `decision_search` for prior architectural decisions when those facts can materially affect the task. Do not call them mechanically.
6. Execute normally through the host: native reads, edits, shell, tests, code search and subagents are allowed. Prefer the smallest sufficient exploration and the cheapest adequate execution path.
7. Managed Tasks/Epics are durable work records plus optional strict workflows, not a universal permission layer. Call `task_next` / `epic_next` when resuming an already-managed focus or when managed/strict execution is explicitly chosen.
8. Current repository source is final code truth. Project Map is a navigation index; Project Knowledge is reviewed semantic memory; Decisions explain prior choices. Verify relevant current source before edits or code-truth claims.
9. Agent Skills are selected by the host natively. Do not manually preload unrelated skills. Use `skill_get` only for explicit retrieval/package details when host-native skill activation is insufficient.

Token-economy objective: use AI Layer to avoid rediscovering known project structure and state, not to add ceremony. A control-plane call is justified only when it reduces uncertainty, preserves durable state, or supplies evidence the host would otherwise have to reconstruct.
"""
    return critical_orchestrator_markdown() + "\n" + startup + "\n" + static_policy_markdown()


def mcp_bootstrap_instructions() -> str:
    """Compact fallback when native bootstrap delivery is unavailable or drifted."""
    return (
        "For registered-project work call project_status first. Use its current_focus to resume existing "
        "Task/Epic work. If code location is unknown, call project_search before broad repository discovery; "
        "if a precise file/symbol is already known, inspect it directly. Use knowledge_search/decision_search "
        "only when relevant. Current source is authoritative and native host reads/edits/tests/subagents remain "
        "the execution engine. task_next/epic_next govern only explicitly managed active workflows."
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
