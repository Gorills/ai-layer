from ai_layer.skills.service import skill_core_content


def test_skill_core_content_never_clips_semantic_sections() -> None:
    apply_when = "## Apply when\n\nUse this skill for the exact domain."
    core_contract = "## Core contract\n\n" + ("context evidence decision verification " * 120)
    decision_rules = "## Decision rules\n\nAlways preserve the complete decision boundary."
    skill = {
        "slug": "bounded",
        "meta": {"entry_sections": ["Apply when", "Core contract", "Decision rules"]},
        "content": "\n\n".join([apply_when, core_contract, decision_rules]),
    }

    content = skill_core_content(skill, max_chars=2400)

    assert len(content) > 2400
    assert apply_when in content
    assert core_contract in content
    assert decision_rules in content
    assert "skill core clipped" not in content


def test_skill_core_zero_budget_can_explicitly_suppress_output() -> None:
    skill = {
        "slug": "suppressed",
        "meta": {"entry_sections": ["Apply when"]},
        "content": "## Apply when\n\nUse when relevant.",
    }

    assert skill_core_content(skill, max_chars=0) == ""
