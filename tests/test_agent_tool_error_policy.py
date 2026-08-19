from __future__ import annotations

from ai_layer.domain.static_policy import static_policy_markdown


def test_static_policy_requires_fail_fast_ai_layer_tool_error_handling() -> None:
    text = static_policy_markdown()

    assert "explicitly branch on success versus error" in text
    assert "A tool error is a control-flow branch" in text
    assert "exact tool schema/signature" in text
    assert "`skill_get` takes `slug`, not `skill_name`" in text
    assert "`PROJECT_CONTEXT_REQUIRED`" in text
    assert "`PROJECT_CONTEXT_AMBIGUOUS`" in text
    assert "canonical `project_root`" in text
    assert "never shell cwd or a guessed path" in text
    assert "A failed `work_begin` means Work was not started" in text
    assert "at most one corrected retry" in text
    assert "same error code repeats" in text
