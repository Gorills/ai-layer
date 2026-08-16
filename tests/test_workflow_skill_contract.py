from __future__ import annotations

from pathlib import Path

from ai_layer.domain.agent_contract import (
    agent_runtime_bootstrap_line,
    agent_runtime_contract,
)
from ai_layer.domain.orchestrator import native_bootstrap_markdown

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "src/ai_layer/builtin_skills/ai-layer-workflow.md"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}\n"
    start = text.index(marker)
    rest = text[start + len(marker) :]
    next_heading = rest.find("\n## ")
    return rest if next_heading < 0 else rest[:next_heading]


def test_workflow_skill_documents_workitem_lifecycle_and_short_work_budget() -> None:
    skill = _skill_text()
    decision_rules = _section(skill, "Decision rules")
    workflow = _section(skill, "Workflow")
    terminals = agent_runtime_contract()["work"]["terminal"]

    for body in (decision_rules, workflow):
        assert "`work_begin`" in body
        assert "`work_checkpoint`" in body
        assert "milestone" in body.casefold()
        assert "blocker" in body.casefold()
        for terminal in terminals:
            assert f"`{terminal}`" in body
        assert "one terminal" in body.casefold()


def test_workflow_skill_continue_follows_status_focus_including_ordinary_work() -> None:
    skill = _skill_text()
    decision_rules = _section(skill, "Decision rules")
    continuation = _section(skill, "Implementation patterns")
    task_at = decision_rules.index("If `kind` is `task`")
    work_at = decision_rules.index("If `kind` is `work`")
    epic_at = decision_rules.index("If `kind` is `epic`")

    assert task_at < work_at < epic_at
    assert "same WorkItem" in decision_rules
    assert "`task_next`" in decision_rules
    assert "`epic_next`" in decision_rules
    assert "If there is no managed focus" not in skill
    assert "whether there is a Task or Epic to resume" not in skill
    assert "Dispatch on `kind`" in continuation
    assert (
        "Resume live ordinary Work through host-native execution on that same WorkItem" not in skill
    )


def test_workflow_skill_search_matches_runtime_contract_v2() -> None:
    skill = _skill_text()
    decision_rules = _section(skill, "Decision rules")
    contract = agent_runtime_contract()

    assert "English and code-centric" in decision_rules
    assert "`query_variants`" in decision_rules
    assert "at most one original-language" in decision_rules
    assert (
        "For non-English natural-language goals, make the primary query concise English "
        "and code-centric; never use raw user prose as the only query."
    ) in decision_rules
    assert contract["search"]["max_queries"] == 2
    assert "Send the real query as written" not in skill
    assert "Do not spend a separate model step translating a Russian query" not in skill
    assert "query=<actual user goal>" not in skill
    assert "with the original query" not in skill


def test_workflow_skill_is_not_a_copy_of_always_on_bootstrap() -> None:
    skill = _skill_text()
    bootstrap = native_bootstrap_markdown()

    assert agent_runtime_bootstrap_line() not in skill
    assert "Mandatory project-intelligence startup" not in skill
    assert "Token-economy objective: use AI Layer to avoid rediscovering" not in skill
    assert skill != bootstrap
    assert "`work_begin`" in bootstrap
    assert "English code-centric" in bootstrap
    assert "## AI Layer control-plane boundary" in bootstrap
    assert "Mandatory project-intelligence startup" not in bootstrap
    assert agent_runtime_bootstrap_line() not in bootstrap
    writing = _section(skill, "Project Map writing contract")
    assert "`source_work_key`" in writing
    assert "`source_task_key`" in writing
    assert "never both" in writing


def test_workflow_skill_apply_when_does_not_auto_load_for_ordinary_chats() -> None:
    apply_when = _section(_skill_text(), "Apply when")
    assert "beginning of a project-related request" not in apply_when
    assert "Do not load it at the start of every registered-project chat" in apply_when
    assert "always-on bootstrap" in apply_when
    assert "ordinary procedure" in apply_when.casefold()
