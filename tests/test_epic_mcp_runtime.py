import inspect

from ai_layer.core.mcp_runtime import (
    FAST_TOOLS,
    REPLAY_SAFE_TOOLS,
    timeout_for_tool,
)
from ai_layer.mcp.tools.epics import epic_next

EPIC_MUTATIONS = {
    "epic_create",
    "epic_spec_edit",
    "epic_spec_revise",
    "epic_audit_record",
    "epic_approve",
    "epic_next",
    "epic_start_next",
    "epic_intervening_review_record",
    "epic_reconcile_complete",
    "epic_plan_set",
    "epic_archive",
}

EPIC_READS = {
    "epic_get",
    "epic_list",
    "epic_spec_get",
    "epic_audit_prepare",
    "epic_intervening_review_prepare",
}


def test_epic_reads_are_fast_and_replay_safe() -> None:
    assert EPIC_READS <= FAST_TOOLS
    assert EPIC_READS <= REPLAY_SAFE_TOOLS
    assert timeout_for_tool("epic_get") == 10.0
    assert timeout_for_tool("epic_list") == 10.0
    assert timeout_for_tool("epic_spec_get") == 10.0
    assert timeout_for_tool("epic_audit_prepare") == 15.0
    assert timeout_for_tool("epic_intervening_review_prepare") == 20.0


def test_epic_next_epic_key_is_optional() -> None:
    parameter = inspect.signature(epic_next).parameters["epic_key"]
    assert parameter.default is None


def test_epic_mutations_are_never_replayed_after_ambiguous_delivery() -> None:
    assert EPIC_MUTATIONS.isdisjoint(REPLAY_SAFE_TOOLS)
    assert timeout_for_tool("epic_spec_edit") == 45.0
    assert timeout_for_tool("epic_intervening_review_record") == 45.0
    assert timeout_for_tool("epic_next") == 45.0
    assert timeout_for_tool("epic_start_next") == 45.0
