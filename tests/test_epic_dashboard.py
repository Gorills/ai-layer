from __future__ import annotations

from pathlib import Path

from ai_layer.dashboard import api as dashboard_api
from ai_layer.projections import epics as epic_projection


def test_project_epics_projection_is_read_only_and_uses_registered_project(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(
        epic_projection,
        "list_registered_projects",
        lambda existing_only=True: [
            {"project_id": "project-1", "name": "demo", "root": str(root)}
        ],
    )
    monkeypatch.setattr(
        epic_projection.epic_uc,
        "list_for_project",
        lambda resolved, include_archived=True: [
            {
                "key": "E-0001",
                "title": "Durable Epic",
                "status": "running",
                "current_spec_version": 2,
                "approved_spec_version": 1,
                "execution_spec_version": 2,
                "plan": [],
            }
        ],
    )

    payload = epic_projection.project_epics_payload("project-1")

    assert payload is not None
    assert payload["project_key"] == "project-1"
    assert payload["epics"][0]["key"] == "E-0001"
    assert payload["epics"][0]["execution_spec_version"] == 2


def test_epic_detail_projection_exposes_full_human_readable_history(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(
        epic_projection,
        "list_registered_projects",
        lambda existing_only=True: [{"project_id": "project-1", "root": str(root)}],
    )
    monkeypatch.setattr(
        epic_projection.epic_uc,
        "get",
        lambda resolved, key, include_history=True: {
            "key": key,
            "title": "Durable Epic",
            "status": "draft",
            "spec": {"version": 3, "content": "# Цель\nПолный продукт"},
            "spec_versions": [{"version": 1}, {"version": 2}, {"version": 3}],
            "audits": [{"spec_version": 2, "summary": "Independent audit"}],
            "plan": [],
        },
    )

    payload = epic_projection.epic_detail_payload("project-1", "E-0001")

    assert payload is not None
    assert payload["epic"]["spec"]["content"].startswith("# Цель")
    assert len(payload["epic"]["spec_versions"]) == 3
    assert payload["epic"]["audits"][0]["summary"] == "Independent audit"


def test_dashboard_api_exposes_epic_read_routes(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_api,
        "project_epics_payload",
        lambda key: {"project_key": key, "epics": [{"key": "E-0001"}]},
    )
    monkeypatch.setattr(
        dashboard_api,
        "epic_detail_payload",
        lambda project_key, epic_key: {
            "project_key": project_key,
            "epic": {"key": epic_key, "spec": {"content": "# Goal"}},
        },
    )

    listed = dashboard_api.dashboard_project_epics("project-1")
    detail = dashboard_api.dashboard_epic("project-1", "E-0001")

    assert listed["epics"][0]["key"] == "E-0001"
    assert detail["epic"]["spec"]["content"] == "# Goal"


def test_dashboard_frontend_has_epic_routes_and_readable_spec_view() -> None:
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "src/ai_layer/dashboard/static/js/app.js").read_text(encoding="utf-8")
    epic_js = (root / "src/ai_layer/dashboard/static/js/views/epic.js").read_text(encoding="utf-8")
    index = (root / "src/ai_layer/dashboard/static/index.html").read_text(encoding="utf-8")

    assert 'current.kind === "epic"' in app_js
    assert "renderEpicDetail" in app_js
    assert "Specification v" in epic_js
    assert "Audits" in epic_js
    assert "Task plan" in epic_js
    assert "Spec history" in epic_js
    assert "/dashboard-assets/css/epics.css" in index
