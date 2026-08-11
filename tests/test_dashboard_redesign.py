from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.projections.dashboard_common import page_info
from ai_layer.projections.dashboard_reference import rules_payload, skills_payload


def _home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    return home


def test_dashboard_pagination_is_bounded():
    page = page_info(123, page=3, page_size=10)
    assert page == {
        "page": 3,
        "page_size": 10,
        "total": 123,
        "pages": 13,
        "has_previous": True,
        "has_next": True,
    }

    capped = page_info(123, page=99, page_size=500)
    assert capped["page_size"] == 50
    assert capped["page"] == capped["pages"]


def test_dashboard_skills_read_bundled_catalog_without_materializing_home(monkeypatch, tmp_path: Path):
    home = _home(monkeypatch, tmp_path)
    settings = get_settings()
    assert not home.exists()
    assert not settings.skills_dir.exists()

    payload = skills_payload(page=1, page_size=10)

    assert payload is not None
    assert payload["pagination"]["total"] > 0
    assert len(payload["items"]) <= 10
    assert any(item["slug"] == "architecture" for item in payload["items"] + []) or payload[
        "pagination"
    ]["pages"] > 1
    assert not settings.skills_dir.exists()
    assert not home.exists()


def test_dashboard_rules_fall_back_to_bundled_policy_without_writing(monkeypatch, tmp_path: Path):
    home = _home(monkeypatch, tmp_path)
    settings = get_settings()
    global_path = settings.policies_dir / "global.md"
    assert not global_path.exists()

    payload = rules_payload()

    assert payload is not None
    assert payload["global"]["rule_count"] >= 10
    assert "Token economy is mandatory" in payload["global"]["content"]
    assert not global_path.exists()
    assert not home.exists()


def test_dashboard_frontend_bounds_dense_lists_and_exposes_real_sections():
    root = Path(__file__).resolve().parents[1]
    project_js = (root / "src/ai_layer/dashboard/static/js/views/project.js").read_text(
        encoding="utf-8"
    )
    overview_js = (root / "src/ai_layer/dashboard/static/js/views/overview.js").read_text(
        encoding="utf-8"
    )
    operations_js = (root / "src/ai_layer/dashboard/static/js/views/operations.js").read_text(
        encoding="utf-8"
    )
    index_html = (root / "src/ai_layer/dashboard/static/index.html").read_text(encoding="utf-8")

    assert "slice(0, 10)" in project_js
    assert "slice(0, 10)" in overview_js
    assert "page_size: 10" in operations_js
    for label in ("Задачи", "Скиллы", "Правила", "База знаний", "Мониторинг", "Активность"):
        assert label in index_html
    assert "профиль пользователя" not in index_html.casefold()
    assert "личный кабинет" not in index_html.casefold()


def test_dashboard_interface_does_not_cross_projection_boundaries():
    root = Path(__file__).resolve().parents[1]
    api_source = (root / "src/ai_layer/dashboard/api.py").read_text(encoding="utf-8")

    assert "ai_layer.db" not in api_source
    assert "ai_layer.tasks" not in api_source
    assert "ai_layer.skills" not in api_source
    assert "ai_layer.projections" in api_source
