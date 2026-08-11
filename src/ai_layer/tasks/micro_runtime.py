from __future__ import annotations

from ai_layer.db.models import Task, TaskStage
from ai_layer.domain.orchestrator import inline_micro_stage_instruction
from ai_layer.tasks.constants import INLINE_MICRO_WORKER_ID
from ai_layer.tasks.contracts import _stage_agent_policy


def should_inline_micro_implementation(task: Task, kind: str) -> bool:
    return (
        kind == "implement"
        and int(task.workflow_version or 1) >= 3
        and (task.workflow_profile or "standard") == "micro"
    )


def is_inline_micro_stage(stage: TaskStage) -> bool:
    return (
        stage.kind == "implement"
        and not bool(stage.delegation_required)
        and stage.worker_id == INLINE_MICRO_WORKER_ID
    )


def inline_micro_next_action(stage: TaskStage) -> dict:
    return {
        "action": "inline_micro_implement",
        "role": "inline_micro_implementer",
        "stage_id": str(stage.id),
        "tool": "task_implementation_complete",
        "required_after_implementation": ["summary", "checks"],
        "agent_policy": _stage_agent_policy(stage),
        "orchestrator_contract": inline_micro_stage_instruction(),
        "completion_precondition": (
            "Perform the localized change and real focused verification before recording completion."
        ),
        "message": (
            "This MICRO IMPLEMENT stage is explicitly authorized inline: make only the localized repository "
            "change, run the narrowest relevant check, then call task_implementation_complete. No separate "
            "implementer subagent is required. AI Layer will inspect the real diff and escalate to STANDARD "
            "review if the micro envelope is exceeded."
        ),
        "forbidden": [
            "external mutations",
            "broadening the requested scope",
            "treating inline authority as permission for later REVIEW/FIX stages",
        ],
    }
