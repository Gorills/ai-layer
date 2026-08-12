from pathlib import Path

from fastapi.testclient import TestClient

from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.dashboard import api as dashboard_api
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


def test_dashboard_skills_read_bundled_catalog_without_materializing_home(
    monkeypatch, tmp_path: Path
):
    home = _home(monkeypatch, tmp_path)
    settings = get_settings()
    assert not home.exists()
    assert not settings.skills_dir.exists()

    payload = skills_payload(page=1, page_size=10)

    assert payload is not None
    assert payload["pagination"]["total"] > 0
    assert len(payload["items"]) <= 10
    assert "architecture" in {item["slug"] for item in payload["items"]}
    assert not settings.skills_dir.exists()
    assert not home.exists()
    get_settings.cache_clear()


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
    get_settings.cache_clear()


def test_dashboard_strict_private_rule_read_does_not_create_project_state(
    monkeypatch, tmp_path: Path
):
    home = _home(monkeypatch, tmp_path)
    project = tmp_path / "private-project"
    project.mkdir()
    register_project(
        project,
        "private-rules",
        "Private Rules",
        mode="strict-private",
        provenance="forbid",
    )
    project_state_root = home / "projects"
    assert not project_state_root.exists()

    payload = rules_payload("private-rules")

    assert payload is not None
    assert payload["project"]["strict_private"] is True
    assert payload["project"]["content"] == ""
    assert not project_state_root.exists()
    get_settings.cache_clear()


def test_dashboard_redesign_routes_are_wired_to_read_models(monkeypatch):
    monkeypatch.setattr(
        dashboard_api,
        "tasks_payload",
        lambda **kwargs: {"kind": "tasks", "kwargs": kwargs},
    )
    monkeypatch.setattr(
        dashboard_api,
        "skills_payload",
        lambda **kwargs: {"kind": "skills", "kwargs": kwargs},
    )
    monkeypatch.setattr(
        dashboard_api,
        "rules_payload",
        lambda project_key=None: {"kind": "rules", "project_key": project_key},
    )
    monkeypatch.setattr(
        dashboard_api,
        "knowledge_payload",
        lambda project_key, **kwargs: {
            "kind": "knowledge",
            "project_key": project_key,
            "kwargs": kwargs,
        },
    )
    monkeypatch.setattr(
        dashboard_api,
        "monitoring_payload",
        lambda project_key=None: {"kind": "monitoring", "project_key": project_key},
    )
    monkeypatch.setattr(
        dashboard_api,
        "activity_payload",
        lambda **kwargs: {"kind": "activity", "kwargs": kwargs},
    )

    from ai_layer.api.app import create_app

    client = TestClient(create_app())
    tasks = client.get("/api/v1/dashboard/tasks?project_key=p1&page=2&page_size=10")
    skills = client.get("/api/v1/dashboard/skills?project_key=p1&page_size=10")
    rules = client.get("/api/v1/dashboard/rules?project_key=p1")
    knowledge = client.get("/api/v1/dashboard/knowledge/p1?status=DRAFT&page_size=10")
    monitoring = client.get("/api/v1/dashboard/monitoring?project_key=p1")
    activity = client.get("/api/v1/dashboard/activity?project_key=p1&page=3&page_size=10")

    assert tasks.status_code == 200
    assert tasks.json()["kwargs"]["project_key_value"] == "p1"
    assert tasks.json()["kwargs"]["page"] == 2
    assert skills.status_code == 200
    assert skills.json()["kwargs"]["project_key_value"] == "p1"
    assert rules.json() == {"kind": "rules", "project_key": "p1"}
    assert knowledge.status_code == 200
    assert knowledge.json()["kwargs"]["status"] == "DRAFT"
    assert monitoring.status_code == 200
    assert monitoring.json() == {"kind": "monitoring", "project_key": "p1"}
    assert activity.status_code == 200
    assert activity.json()["kwargs"]["page"] == 3


def test_dashboard_frontend_bounds_dense_lists_and_exposes_real_sections():
    root = Path(__file__).resolve().parents[1]
    project_js = (root / "src/ai_layer/dashboard/static/js/views/project.js").read_text(
        encoding="utf-8"
    )
    overview_js = (root / "src/ai_layer/dashboard/static/js/views/overview.js").read_text(
        encoding="utf-8"
    )
    app_js = (root / "src/ai_layer/dashboard/static/js/app.js").read_text(encoding="utf-8")
    epic_js = (root / "src/ai_layer/dashboard/static/js/views/epic.js").read_text(encoding="utf-8")
    operations_js = (root / "src/ai_layer/dashboard/static/js/views/operations.js").read_text(
        encoding="utf-8"
    )
    index_html = (root / "src/ai_layer/dashboard/static/index.html").read_text(encoding="utf-8")

    assert "slice(0, 10)" in project_js
    assert "slice(0, 10)" in overview_js
    assert "page_size: 10" in app_js
    assert "неограниченная история" not in epic_js
    assert "IDE-интеграции" in operations_js
    for label in (
        "Задачи",
        "Скиллы",
        "Правила",
        "База знаний",
        "Мониторинг",
        "Активность",
    ):
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
