from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from ai_layer.core.config import get_settings
from ai_layer.projections.dashboard_work_state import enrich_overview

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/ai_layer/dashboard/static"


def _read(*parts: str) -> str:
    return STATIC.joinpath(*parts).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    marker = f"export function {name}"
    start = source.index(marker)
    rest = source[start + len(marker) :]
    nxt = rest.find("\nexport function ")
    return source[start:] if nxt < 0 else source[start : start + len(marker) + nxt]


def test_dashboard_exposes_work_list_and_detail_browser_routes() -> None:
    app_js = _read("js", "app.js")
    api_js = _read("js", "api.js")
    index_html = _read("index.html")
    work_js = _read("js", "views", "work.js")

    assert 'current.kind === "work"' in app_js
    assert 'current.kind === "work-item"' in app_js
    assert "renderWorkList" in app_js
    assert "renderWorkDetail" in app_js
    assert "api.work(" in app_js
    assert "api.workDetail(" in app_js
    assert 'request("/work"' in api_js
    assert "`/work/${encodeURIComponent(projectKey)}/${encodeURIComponent(workKey)}`" in api_js
    assert 'data-route="work"' in index_html
    assert 'href="#/work"' in index_html
    assert "Работа" in index_html
    assert "renderWorkList" in work_js
    assert "renderWorkDetail" in work_js
    assert 'hashUrl("work"' in work_js
    assert "work/${encodeURIComponent(projectKey)}/${encodeURIComponent(workKey)}" in work_js


def test_overview_portfolio_slices_bind_live_attention_recent_not_active() -> None:
    overview_js = _read("js", "views", "overview.js")
    work_js = _read("js", "views", "work.js")
    collector = _function(work_js, "collectPortfolioWork")

    assert "collectPortfolioWork" in overview_js
    assert "Нужно внимание" in overview_js
    assert "Недавно завершено" in overview_js
    assert "Сейчас" in overview_js
    assert "bucket.live" in collector
    assert "item.live" in collector
    assert "bucket.attention" in collector
    assert "bucket.recent" in collector
    assert "bucket.active" not in collector
    assert "work.active" not in overview_js
    assert "work?.active" not in overview_js
    assert "mcp_bridges" not in collector
    assert "active_mcp_bridges" not in collector


def test_work_ui_uses_backend_live_flag_for_stale_not_weaker_heartbeat_rule() -> None:
    work_js = _read("js", "views", "work.js")
    display = _function(work_js, "workDisplayState")
    attention = _function(work_js, "workAttentionReason")

    assert "work?.live" in display
    assert 'work?.status === "active"' in display
    assert 'return "stale"' in display
    assert "WORK_RUN_STALE_SECONDS" not in work_js
    assert "heartbeat" not in display.casefold()
    assert 'status === "blocked"' in attention
    assert "map_disposition" in attention
    assert '"pending"' in attention
    assert '"deferred"' in attention


def test_work_ui_escapes_untrusted_fields_and_keeps_fetch_no_store() -> None:
    work_js = _read("js", "views", "work.js")
    overview_js = _read("js", "views", "overview.js")
    api_js = _read("js", "api.js")
    app_js = _read("js", "app.js")

    for blob in (work_js, overview_js):
        assert "escapeHtml(work.goal" in blob or "escapeHtml(title)" in blob
        assert "escapeHtml(work.key" in blob or "escapeHtml(title)" in blob
        assert "innerHTML =" not in blob
    assert "warning.textContent" in app_js
    assert 'cache: "no-store"' in api_js
    assert "eval(" not in work_js
    assert "document.write" not in work_js


def test_overview_enrichment_payload_is_the_portfolio_source_of_truth(monkeypatch) -> None:
    stale = {
        "active": [{"key": "W-0001", "status": "active", "live": False}],
        "live": [],
        "attention": [{"key": "W-0001", "status": "active", "live": False}],
        "recent": [{"key": "W-0002", "status": "completed", "live": False}],
    }
    live = {
        "active": [{"key": "W-0003", "status": "active", "live": True}],
        "live": [{"key": "W-0003", "status": "active", "live": True}],
        "attention": [],
        "recent": [],
    }

    def fake_state(root: str, *, limit: int = 4) -> dict:
        return stale if "stale" in root else live

    monkeypatch.setattr("ai_layer.projections.dashboard_work_state.work_uc.state", fake_state)
    monkeypatch.setattr(
        "ai_layer.projections.dashboard_work_state._map_state",
        lambda *_args, **_kwargs: {},
    )
    overview = enrich_overview(
        {
            "projects": [
                {
                    "root": "/tmp/stale-proj",
                    "key": "stale",
                    "name": "Stale",
                    "task": {},
                    "agents": [],
                },
                {
                    "root": "/tmp/live-proj",
                    "key": "live",
                    "name": "Live",
                    "task": {},
                    "agents": [],
                },
            ],
            "summary": {},
        }
    )

    by_key = {project["key"]: project["work"] for project in overview["projects"]}
    assert by_key["stale"]["live"] == []
    assert by_key["stale"]["attention"][0]["key"] == "W-0001"
    assert by_key["stale"]["recent"][0]["key"] == "W-0002"
    assert by_key["live"]["live"][0]["key"] == "W-0003"
    now_keys = [item["key"] for project in overview["projects"] for item in project["work"]["live"]]
    attention_keys = [
        item["key"] for project in overview["projects"] for item in project["work"]["attention"]
    ]
    assert "W-0001" not in now_keys
    assert "W-0003" in now_keys
    assert "W-0001" in attention_keys


def test_dashboard_serves_work_frontend_module(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()

    from ai_layer.api.app import create_app

    client = TestClient(create_app())
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert 'data-route="work"' in page.text
    assert "Cache-Control" in page.headers
    assert "no-store" in page.headers["Cache-Control"]
    assert "script-src 'self'" in page.headers.get("Content-Security-Policy", "")
    work_js = client.get("/dashboard-assets/js/views/work.js")
    assert work_js.status_code == 200
    assert "renderWorkList" in work_js.text
    assert "collectPortfolioWork" in work_js.text


def test_project_table_current_work_skips_completed_map_attention() -> None:
    work_js = _read("js", "views", "work.js")
    overview_js = _read("js", "views", "overview.js")
    primary = _function(work_js, "primaryProjectWork")
    stack = _function(work_js, "workStack")

    assert "primaryProjectWork" in overview_js
    assert "(work.attention || [])[0]" not in primary
    assert 'item.status === "active" || item.status === "blocked"' in primary
    assert "(work.recent || [])[0]" in primary
    assert "item.live" in primary
    assert "Показаны" in stack
    assert "table-caption" in stack
    assert 'href="#/work">Все →' in overview_js


def test_work_portfolio_helpers_execute_slice_membership(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        raise AssertionError("node is required to execute Dashboard Work UI helpers")
    script = tmp_path / "work_ui_check.mjs"
    work_url = (STATIC / "js/views/work.js").resolve().as_uri()
    overview_url = (STATIC / "js/views/overview.js").resolve().as_uri()
    script.write_text(
        f"""
import {{ collectPortfolioWork, primaryProjectWork, workDisplayState, workStack }} from '{work_url}';
import {{ renderOverview }} from '{overview_url}';
const mapPending = {{
  key: 'W-0001', status: 'completed', live: false,
  map_disposition: {{ status: 'pending' }}, goal: 'Old map',
  updated_at: '2026-08-01T00:00:00Z', completed_at: '2026-08-01T00:00:00Z',
}};
const newerDone = {{
  key: 'W-0002', status: 'completed', live: false, goal: 'Newer',
  updated_at: '2026-08-10T00:00:00Z', completed_at: '2026-08-10T00:00:00Z',
}};
const stale = {{ key: 'W-STALE', status: 'active', live: false, goal: 'Stale' }};
const live = {{ key: 'W-LIVE', status: 'active', live: true, goal: 'Live' }};
const project = {{
  key: 'p1', name: 'P',
  work: {{ live: [], attention: [mapPending], recent: [newerDone, mapPending] }},
}};
if (primaryProjectWork(project).key !== 'W-0002') throw new Error('map-pending stole current work');
if (primaryProjectWork({{ work: {{ live: [live], attention: [stale], recent: [] }} }}).key !== 'W-LIVE') {{
  throw new Error('live lost');
}}
if (primaryProjectWork({{ work: {{ live: [], attention: [stale], recent: [newerDone] }} }}).key !== 'W-STALE') {{
  throw new Error('open stale should beat recent');
}}
const slices = collectPortfolioWork([
  {{ key: 's', name: 'S', work: {{ live: [stale], attention: [stale], recent: [] }} }},
  {{ key: 'l', name: 'L', work: {{ live: [live], attention: [], recent: [newerDone] }} }},
]);
if (slices.now.map((item) => item.work.key).join() !== 'W-LIVE') throw new Error('now');
if (slices.attention.map((item) => item.work.key).join() !== 'W-STALE') throw new Error('attention');
if (workDisplayState(stale) !== 'stale' || workDisplayState(live) !== 'active') throw new Error('display');
const html = renderOverview({{
  summary: {{ projects: 1, active_work: 1, attention_tasks: 0, active_mcp_bridges: 0 }},
  database: {{ connected: true }}, core_runtime: {{ status: 'ready' }}, service: {{}},
  projects: [
    {{ key: 'l', name: 'L', project_state: 'working', work: {{ live: [live], attention: [], recent: [] }}, mcp_bridges: [] }},
    {{ key: 's', name: 'S', project_state: 'attention', work: {{ live: [], attention: [stale], recent: [] }}, mcp_bridges: [{{ activity_state: 'WORKING' }}] }},
  ],
  recent_activity: [],
}});
const hero = html.match(/<div class="focus-title">([\\s\\S]*?)<\\/div>/)[1];
if (!hero.includes('W-LIVE') || hero.includes('W-STALE')) throw new Error('hero ' + hero);
const caption = workStack(new Array(2).fill({{ project: {{ key: 'p', name: 'P' }}, work: live }}), 'empty', null, {{ total: 9 }});
if (!caption.includes('Показаны 2 из 9')) throw new Error('caption');
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", script],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
