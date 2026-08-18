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
    from ai_layer.dashboard import activity_api

    seen_work = {}

    def work_items(**kwargs):
        seen_work.update(kwargs)
        return {
            "contract_version": 1,
            "generated_at": "2026-08-13T00:00:00+00:00",
            "items": [],
            "pagination": {
                "page": 1,
                "page_size": 10,
                "total": 0,
                "pages": 0,
                "has_previous": False,
                "has_next": False,
            },
            "projects": [],
            "filters": {
                "project_key": kwargs.get("project_key_value"),
                "status": kwargs.get("status"),
            },
            "ordering": ["updated_at:desc", "id:desc"],
        }

    monkeypatch.setattr(dashboard_api, "work_items_payload", work_items)
    monkeypatch.setattr(
        dashboard_api,
        "tasks_payload",
        lambda **kwargs: {"kind": "tasks", "kwargs": kwargs},
    )
    monkeypatch.setattr(
        dashboard_api,
        "epics_payload",
        lambda **kwargs: {"kind": "epics", "kwargs": kwargs},
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
    seen_activity = {}

    def activity_payload(**kwargs):
        seen_activity.update(kwargs)
        return {
            "contract_version": 2,
            "generated_at": "2026-08-13T00:00:00+00:00",
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "limit": kwargs["limit"],
            "projects": [],
            "filters": {
                "project_key": kwargs["project_key_value"],
                "mode": kwargs["mode"],
                "occurred_after": None,
                "occurred_before": None,
                "work_id": None,
                "task_id": None,
                "epic_id": None,
                "actor_id": kwargs["actor_id"],
                "event_type": kwargs["event_type"],
                "status": kwargs["status"],
                "importance": kwargs["importance"],
                "assurance": kwargs["assurance"],
            },
            "ordering": ["occurred_at:desc", "event_id:desc"],
            "retention": "durable RuntimeEvent journal",
        }

    monkeypatch.setattr(activity_api, "activity_payload", activity_payload)

    from ai_layer.api.app import create_app

    application = create_app()
    client = TestClient(application)
    work = client.get("/api/v1/dashboard/work?project_key=p1&status=blocked&page=2&page_size=10")
    tasks = client.get("/api/v1/dashboard/tasks?project_key=p1&page=2&page_size=10")
    epics = client.get("/api/v1/dashboard/epics?project_key=p1&status=open&page=2&page_size=10")
    skills = client.get("/api/v1/dashboard/skills?project_key=p1&page_size=10")
    rules = client.get("/api/v1/dashboard/rules?project_key=p1")
    knowledge = client.get("/api/v1/dashboard/knowledge/p1?status=DRAFT&page_size=10")
    monitoring = client.get("/api/v1/dashboard/monitoring?project_key=p1")
    activity = client.get(
        "/api/v1/dashboard/activity?project_key=p1&mode=all&event_type=WorkCompleted"
        "&status=completed&actor_id=agent:root&importance=high"
        "&assurance=host_reported&limit=20"
    )

    assert work.status_code == 200
    assert seen_work["project_key_value"] == "p1"
    assert seen_work["status"] == "blocked"
    assert seen_work["page"] == 2
    schema = application.openapi()
    assert (
        schema["paths"]["/api/v1/dashboard/work"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/WorkListRead"
    )
    assert (
        schema["paths"]["/api/v1/dashboard/work/{project_key}/{work_key}"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/WorkDetailRead"
    )
    assert (
        schema["paths"]["/api/v1/dashboard/activity"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/ActivityRead"
    )
    activity_payload_schema = schema["components"]["schemas"]["SafeEventPayload"]
    assert "additionalProperties" not in activity_payload_schema
    assert set(activity_payload_schema["properties"]) == {
        "status",
        "summary",
        "reason",
        "goal",
        "kind",
        "tool",
        "command_name",
        "duration_ms",
        "error_type",
        "updated",
        "removed",
        "scope_paths",
        "map_status",
    }
    assert (
        schema["paths"]["/api/v1/dashboard/activity"]["get"]["responses"]["422"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/DashboardValidationError"
    )
    assert tasks.status_code == 200
    assert tasks.json()["kwargs"]["project_key_value"] == "p1"
    assert tasks.json()["kwargs"]["page"] == 2
    assert epics.status_code == 200
    assert epics.json()["kwargs"]["project_key_value"] == "p1"
    assert epics.json()["kwargs"]["status"] == "open"
    assert epics.json()["kwargs"]["page"] == 2
    assert skills.status_code == 200
    assert skills.json()["kwargs"]["project_key_value"] == "p1"
    assert rules.json() == {"kind": "rules", "project_key": "p1"}
    assert knowledge.status_code == 200
    assert knowledge.json()["kwargs"]["status"] == "DRAFT"
    assert monitoring.status_code == 200
    assert monitoring.json() == {"kind": "monitoring", "project_key": "p1"}
    assert activity.status_code == 200
    assert seen_activity["project_key_value"] == "p1"
    assert seen_activity["mode"] == "all"
    assert seen_activity["event_type"] == "WorkCompleted"
    assert seen_activity["status"] == "completed"
    assert seen_activity["actor_id"] == "agent:root"
    assert seen_activity["importance"] == "high"
    assert seen_activity["assurance"] == "host_reported"
    assert seen_activity["limit"] == 20


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

    assert "slice(0, 5)" in project_js
    assert "slice(0, 10)" in overview_js
    assert "page_size: 10" in app_js
    assert 'current.kind === "epics"' in app_js
    assert "неограниченная история" not in epic_js
    assert "IDE-интеграции" in operations_js
    for label in (
        "Работа",
        "Задачи",
        "Эпики",
        "Скиллы",
        "Правила",
        "База знаний",
        "Мониторинг",
        "Активность",
    ):
        assert label in index_html
    assert 'data-route="epics"' in index_html
    assert "профиль пользователя" not in index_html.casefold()
    assert "личный кабинет" not in index_html.casefold()


def test_dashboard_design_system_uses_flat_layers_and_project_scope():
    root = Path(__file__).resolve().parents[1]
    static = root / "src/ai_layer/dashboard/static"
    index_html = (static / "index.html").read_text(encoding="utf-8")
    tokens_css = (static / "css/tokens.css").read_text(encoding="utf-8")
    app_css = (static / "css/app.css").read_text(encoding="utf-8")
    components_css = (static / "css/components.css").read_text(encoding="utf-8")

    assert 'id="project-scope"' in index_html
    assert 'href="/dashboard-assets/css/tokens.css"' in index_html
    assert 'href="/dashboard-assets/css/components.css"' in index_html
    assert "--accent:" in tokens_css
    assert "radial-gradient" not in app_css
    assert "linear-gradient" not in app_css
    assert "radial-gradient" not in components_css
    assert "linear-gradient" not in components_css


def test_dashboard_interface_does_not_cross_projection_boundaries():
    root = Path(__file__).resolve().parents[1]
    api_source = (root / "src/ai_layer/dashboard/api.py").read_text(encoding="utf-8")

    assert "ai_layer.db" not in api_source
    assert "ai_layer.tasks" not in api_source
    assert "ai_layer.skills" not in api_source
    assert "ai_layer.projections" in api_source
