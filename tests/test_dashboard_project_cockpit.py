from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_JS = ROOT / "src/ai_layer/dashboard/static/js/views/project.js"
APP_JS = ROOT / "src/ai_layer/dashboard/static/js/app.js"


def _work(key: str, goal: str, *, live: bool) -> dict:
    return {
        "key": key,
        "goal": goal,
        "kind": "implementation",
        "status": "active",
        "live": live,
        "updated_at": "2026-08-20T06:00:00+00:00",
        "result_summary": "Waiting for operator review",
        "runs": [],
        "changed_paths": [],
        "repository_delta": {},
        "checks": [],
    }


def _payload() -> dict:
    live = _work("W-0002", "Live migration", live=True)
    waiting = _work("W-0001", "Primary implementation", live=False)
    return {
        "project": {
            "key": "alpha",
            "name": "Alpha",
            "root": "/tmp/alpha",
            "project_state": "working",
            "work": {
                "active": [waiting, live],
                "live": [live],
                "recent": [],
                "attention": [],
            },
            "task": {},
            "project_map": {},
            "protocol_state": {},
            "memory_refresh": {},
            "mcp_bridges": [],
        },
        "tasks": {
            "items": [
                {
                    "key": "T-0001",
                    "goal": "Review rollout",
                    "status": "active",
                    "active_stage": {"kind": "implementation"},
                    "review_round": 0,
                    "fix_round": 0,
                    "open_findings": 0,
                }
            ]
        },
        "epics": {
            "items": [
                {
                    "key": "E-0001",
                    "title": "Dashboard UX",
                    "status": "running",
                    "progress": {"completed": 1, "total": 3},
                    "updated_at": "2026-08-20T06:00:00+00:00",
                }
            ]
        },
        "skill_state": {"configured_catalog": {}},
        "metrics": {},
    }


def test_project_cockpit_keeps_daily_workflows_on_summary_screen() -> None:
    script = (
        f"import {{ renderProject }} from {json.dumps(PROJECT_JS.as_uri())};\n"
        f"const payload = {json.dumps(_payload())};\n"
        "process.stdout.write(renderProject(payload));\n"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=True,
        capture_output=True,
        text=True,
    )
    html = result.stdout

    assert "PROJECT COCKPIT" in html
    assert "В работе" in html
    assert "План и assurance" in html
    assert "Managed Tasks" in html
    assert "Review rollout" in html
    assert "Dashboard UX" in html
    assert "cockpit-work-row is-focus" in html
    assert "Текущий фокус" in html
    assert html.count('data-work-complete="true"') == 1


def test_project_route_uses_bounded_cockpit_cache() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert "const PROJECT_COCKPIT_CACHE_MS = IDLE_POLL_MS;" in source
    assert "async function projectCockpitData(projectKey)" in source
    assert "api.tasks({ project_key: projectKey, page: 1, page_size: 6 })" in source
    assert "api.epics({ project_key: projectKey, page: 1, page_size: 6 })" in source
    assert "projectCockpitCache.clear();" in source
    assert "tasks: cockpit.tasks, epics: cockpit.epics" in source


def test_project_summary_no_longer_renders_duplicate_now_panel() -> None:
    source = PROJECT_JS.read_text(encoding="utf-8")

    assert "function nowPanel(data)" not in source
    assert "${nowPanel(data)}" not in source
    assert "${workflowPanel(data)}" in source
