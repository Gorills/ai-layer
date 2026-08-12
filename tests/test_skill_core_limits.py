from ai_layer.skills.service import skill_core_content


def test_skill_core_content_never_exceeds_requested_bound() -> None:
    skill = {
        "slug": "bounded",
        "meta": {"entry_sections": ["Apply when"]},
        "content": "## Apply when\n\n" + ("context evidence decision verification " * 200),
    }

    for max_chars in (0, 1, 16, 48, 64, 2400):
        content = skill_core_content(skill, max_chars=max_chars)
        assert len(content) <= max_chars
