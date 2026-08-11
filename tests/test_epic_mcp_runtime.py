from ai_layer.core.mcp_runtime import (
    FAST_TOOLS,
    REPLAY_SAFE_TOOLS,
    timeout_for_tool,
)

EPIC_MUTATIONS = {
    "epic_create",
    "epic_spec_revise",
    "epic_audit_record",
    "epic_approve",
    "epic_next",
    "epic_start_next",
    "epic_reconcile_complete",
    "epic_plan_set",
    "epic_archive",
}


def test_epic_reads_are_fast_and_replay_safe() -> None:
    assert {"epic_get", "epic_list"} <= FAST_TOOLS
    assert {"epic_get", "epic_list"} <= REPLAY_SAFE_TOOLS
    assert timeout_for_tool("epic_get") == 10.0
    assert timeout_for_tool("epic_list") == 10.0


def test_epic_mutations_are_never_replayed_after_ambiguous_delivery() -> None:
    assert EPIC_MUTATIONS.isdisjoint(REPLAY_SAFE_TOOLS)
    assert timeout_for_tool("epic_next") == 45.0
    assert timeout_for_tool("epic_start_next") == 45.0
