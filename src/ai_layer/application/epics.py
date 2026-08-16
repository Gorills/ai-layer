"""Public Epic application use cases.

The facade is intentionally thin: specification lifecycle, planning, execution, review and
navigation are separate owners.
"""

from pathlib import Path

from ai_layer.application.epic_execution import start_drift_reconciliation, start_next
from ai_layer.application.epic_lifecycle import (
    approve,
    archive,
    create,
    edit_spec,
    get,
    get_spec_version,
    list_for_project,
    record_audit,
    revise_spec,
)
from ai_layer.application.epic_navigation import next_action as _next_action
from ai_layer.application.epic_planning import reconcile_complete, set_plan
from ai_layer.application.epic_review import (
    prepare_intervening_review,
    prepare_spec_audit,
    record_intervening_review,
)
from ai_layer.domain.agent_contract import ENVELOPE_MANAGED_NEXT, with_envelope


def next_action(project_root: str | Path, *, key: str | None = None) -> dict:
    """Return authoritative live Epic navigation without reprinting the runtime contract."""
    return with_envelope(dict(_next_action(project_root, key=key)), ENVELOPE_MANAGED_NEXT)


__all__ = [
    "create",
    "list_for_project",
    "get",
    "get_spec_version",
    "revise_spec",
    "edit_spec",
    "prepare_spec_audit",
    "record_audit",
    "approve",
    "start_next",
    "reconcile_complete",
    "set_plan",
    "next_action",
    "start_drift_reconciliation",
    "prepare_intervening_review",
    "record_intervening_review",
    "archive",
]
