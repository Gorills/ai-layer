from __future__ import annotations

from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.projections.dashboard_reference import rules_payload

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/ai_layer/dashboard/static"


def _read(*parts: str) -> str:
    return STATIC.joinpath(*parts).read_text(encoding="utf-8")


def test_dashboard_keeps_project_context_across_navigation() -> None:
    app_js = _read("js", "app.js")
    index_html = _read("index.html")
    workspace_css = _read("css", "workspace.css")

    assert "function scopedHref" in app_js
    assert "element.href = scopedHref(target, knownProject)" in app_js
    assert 'parts[2] === "work"' in app_js
    assert 'parts[2] === "knowledge"' in app_js
    assert "project-context-bar" in app_js
    assert "project-context-tabs" in app_js
    assert 'id="project-home-nav"' in index_html
    assert "Контекст сохраняется при переходах" in index_html
    assert 'href="/dashboard-assets/css/workspace.css"' in index_html
    assert ".project-context-bar" in workspace_css
    assert "position: sticky" in workspace_css


def test_project_workspace_answers_operational_questions_without_screen_hopping() -> None:
    project_js = _read("js", "views", "project.js")
    app_js = _read("js", "app.js")

    for label in (
        "Сейчас",
        "Требует внимания",
        "Недавние результаты",
        "Контекст проекта",
        "Вся работа проекта в одном месте",
        "Project Knowledge",
        "Project Map",
        "Правила проекта",
        "Skills",
    ):
        assert label in project_js

    assert "changedLabel(work)" in project_js
    assert "checksLabel(work)" in project_js
    assert "workMethod(work)" in project_js
    assert "Promise.all([" in app_js
    assert "api.work({ project_key: current.key" in app_js
    assert "api.tasks({ project_key: current.key" in app_js
    assert "api.epics({ project_key: current.key" in app_js
    assert "api.knowledge(current.key" in app_js


def test_overview_is_attention_first_portfolio_not_dense_project_table() -> None:
    overview_js = _read("js", "views", "overview.js")

    assert "Сначала внимание" in overview_js
    assert "Сейчас выполняется" in overview_js
    assert "Последние результаты" in overview_js
    assert "portfolio-project-grid" in overview_js
    assert "Открыть проект →" in overview_js
    assert "<table" not in overview_js
    assert overview_js.index("Сначала внимание") < overview_js.index("Сейчас выполняется")
    assert overview_js.index("Сейчас выполняется") < overview_js.index("Проекты")


def test_knowledge_without_project_does_not_silently_pick_first_project() -> None:
    app_js = _read("js", "app.js")

    assert "Сначала выберите проект" in app_js
    assert "Project Knowledge всегда принадлежит конкретному проекту" in app_js
    assert "overviewCache.projects?.[0]?.key" not in app_js


def test_standard_project_rules_are_read_from_zero_footprint_machine_state(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    try:
        register_project(project, "p-dashboard", "Dashboard", mode="standard", provenance="allow")
        state = home / "projects" / "p-dashboard"
        state.mkdir(parents=True)
        (state / "rules.md").write_text(
            "# Project rules\n\n- Keep the project context stable.\n", encoding="utf-8"
        )

        payload = rules_payload("p-dashboard")

        assert payload is not None
        assert payload["project"]["has_custom_rules"] is True
        assert payload["project"]["rule_count"] == 1
        assert "Keep the project context stable" in payload["project"]["content"]
        assert not (project / ".ai-layer").exists()
    finally:
        get_settings.cache_clear()
