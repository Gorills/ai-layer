from __future__ import annotations

import json
import mimetypes
import os
import socket
import threading
import time
from collections import Counter, defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/ai_layer/dashboard/static"
BROWSER_ENABLED = os.getenv("AI_LAYER_BROWSER_TESTS") == "1"
NOW = "2026-08-20T06:00:00+00:00"

pytestmark = pytest.mark.skipif(
    not BROWSER_ENABLED,
    reason="set AI_LAYER_BROWSER_TESTS=1 in the dedicated browser acceptance job",
)


def _work(project_key: str = "alpha", key: str = "W-0001") -> dict:
    return {
        "id": f"{project_key}-{key}",
        "key": key,
        "goal": "Verify dashboard navigation",
        "kind": "diagnose",
        "status": "active",
        "live": False,
        "result_summary": "Waiting for operator review",
        "reviewed_paths": [],
        "changed_paths": [],
        "repository_delta": {},
        "checks": [{"name": "host report", "status": "reported", "summary": "reported"}],
        "map_disposition": {"status": "pending", "scope": [], "reason": "", "event_id": None},
        "map_pending": True,
        "observability_coverage": "lifecycle_only",
        "assurance": "agent_reported",
        "linked_task_id": None,
        "linked_epic_id": None,
        "linked_task_key": None,
        "linked_epic_key": None,
        "legacy_session_id": None,
        "started_at": NOW,
        "updated_at": NOW,
        "last_milestone_at": NOW,
        "completed_at": None,
        "runs": [],
        "project": {"key": project_key, "name": f"{project_key.title()} Project", "root": f"/tmp/{project_key}"},
    }


def _project(key: str) -> dict:
    work = _work(key, "W-0001" if key == "alpha" else "W-0002")
    return {
        "key": key,
        "name": f"{key.title()} Project",
        "root": f"/tmp/{key}",
        "mode": "standard",
        "project_state": "attention" if key == "alpha" else "healthy",
        "runtime_state": "idle",
        "work": {
            "active": [work] if key == "alpha" else [],
            "live": [],
            "attention": [work] if key == "alpha" else [],
            "recent": [],
        },
        "task": {"status": "completed"},
        "project_map": {
            "semantic_entries": 1,
            "semantic_current": 1,
            "semantic_stale": 0,
            "semantic_missing": 0,
            "semantic_current_coverage": 1.0,
        },
        "protocol_state": {"status": "healthy", "failures_5m": 0},
        "memory_refresh": {"status": "idle"},
        "mcp_bridges": [],
        "last_scan": {},
    }


def _overview() -> dict:
    return {
        "generated_at": NOW,
        "version": "browser-test",
        "summary": {
            "projects": 2,
            "active_work": 0,
            "active_tasks": 0,
            "active_agents": 0,
            "active_mcp_bridges": 0,
            "protocol_warnings": 0,
            "failures_5m": 0,
        },
        "database": {"connected": True},
        "core_runtime": {"status": "ready"},
        "service": {"background": True},
        "projects": [_project("alpha"), _project("beta")],
        "recent_activity": [],
    }


def _project_payload(key: str) -> dict:
    return {
        "generated_at": NOW,
        "project": _project(key),
        "metrics": {"events_24h": 2, "failures_24h": 0},
        "skill_state": {"configured_catalog": {}},
    }


def _pagination(total: int) -> dict:
    return {
        "page": 1,
        "page_size": 10,
        "total": total,
        "pages": 1 if total else 0,
        "has_previous": False,
        "has_next": False,
    }


def _work_list(project_key: str | None) -> dict:
    items = [_work("alpha")] if project_key in {None, "alpha"} else []
    return {
        "contract_version": 1,
        "generated_at": NOW,
        "items": items,
        "pagination": _pagination(len(items)),
        "projects": [
            {"key": "alpha", "name": "Alpha Project", "root": "/tmp/alpha", "mode": "standard", "provenance": "allow"},
            {"key": "beta", "name": "Beta Project", "root": "/tmp/beta", "mode": "standard", "provenance": "allow"},
        ],
        "filters": {"project_key": project_key, "status": None},
        "ordering": ["updated_at:desc", "id:desc"],
    }


def _work_detail(project_key: str, work_key: str) -> dict:
    return {
        "contract_version": 1,
        "project": {"key": project_key, "name": f"{project_key.title()} Project", "root": f"/tmp/{project_key}"},
        "work": _work(project_key, work_key),
        "timeline": [],
        "timeline_total": 0,
        "timeline_truncated": False,
        "timeline_ordering": ["occurred_at:asc", "id:asc"],
    }


def _epic_list(project_key: str | None) -> dict:
    items = []
    if project_key in {None, "alpha"}:
        items = [
            {
                "key": "E-0001",
                "title": "Dashboard reliability",
                "status": "running",
                "project": {"key": "alpha", "name": "Alpha Project"},
                "current_spec_version": 1,
                "plan_version": 1,
                "progress": {"total": 1, "completed": 0},
                "updated_at": NOW,
            }
        ]
    return {
        "generated_at": NOW,
        "items": items,
        "pagination": _pagination(len(items)),
        "projects": [
            {"key": "alpha", "name": "Alpha Project"},
            {"key": "beta", "name": "Beta Project"},
        ],
        "filters": {"project_key": project_key, "status": None},
    }


def _epic_detail(project_key: str, epic_key: str) -> dict:
    return {
        "project_key": project_key,
        "epic": {
            "key": epic_key,
            "title": "Dashboard reliability",
            "status": "running",
            "approved_spec_version": 1,
            "execution_spec_version": 1,
            "current_spec_version": 1,
            "plan_version": 1,
            "created_at": NOW,
            "updated_at": NOW,
            "plan": [],
            "audits": [],
            "spec_quality": {"ready_for_human_review": True, "missing_recommended_sections": []},
        },
    }


def _tasks(project_key: str | None) -> dict:
    return {
        "generated_at": NOW,
        "items": [],
        "pagination": _pagination(0),
        "projects": [{"key": "alpha", "name": "Alpha Project"}, {"key": "beta", "name": "Beta Project"}],
        "filters": {"project_key": project_key, "status": None},
    }


class DashboardServerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts: Counter[str] = Counter()
        self.delays: dict[str, list[float]] = defaultdict(list)
        self.drops: Counter[str] = Counter()

    def delay_next(self, path: str, seconds: float) -> None:
        with self.lock:
            self.delays[path].append(seconds)

    def drop_next(self, path: str) -> None:
        with self.lock:
            self.drops[path] += 1

    def before(self, path: str) -> tuple[float, bool]:
        with self.lock:
            self.counts[path] += 1
            delay = self.delays[path].pop(0) if self.delays[path] else 0.0
            drop = self.drops[path] > 0
            if drop:
                self.drops[path] -= 1
        return delay, drop

    def count(self, path: str) -> int:
        with self.lock:
            return self.counts[path]


class DashboardHandler(BaseHTTPRequestHandler):
    server: "DashboardHTTPServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _write(self, data: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict) -> None:
        self._write(json.dumps(payload).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/dashboard":
            self._write((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/dashboard-assets/"):
            relative = path.removeprefix("/dashboard-assets/")
            target = (STATIC / relative).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._write(target.read_bytes(), content_type)
            return
        if not path.startswith("/api/v1/dashboard/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        delay, drop = self.server.state.before(path)
        if delay:
            time.sleep(delay)
        if drop:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return

        query = parse_qs(parsed.query)
        if path == "/api/v1/dashboard/overview":
            self._json(_overview())
            return
        if path.startswith("/api/v1/dashboard/projects/") and "/epics/" not in path:
            key = path.rsplit("/", 1)[-1]
            self._json(_project_payload(key))
            return
        if path == "/api/v1/dashboard/work":
            self._json(_work_list(query.get("project_key", [None])[0]))
            return
        if path.startswith("/api/v1/dashboard/work/"):
            _, project_key, work_key = path.rsplit("/", 2)
            self._json(_work_detail(project_key, work_key))
            return
        if path == "/api/v1/dashboard/tasks":
            self._json(_tasks(query.get("project_key", [None])[0]))
            return
        if path == "/api/v1/dashboard/epics":
            self._json(_epic_list(query.get("project_key", [None])[0]))
            return
        if "/epics/" in path and path.startswith("/api/v1/dashboard/projects/"):
            parts = path.split("/")
            project_key = parts[-3]
            epic_key = parts[-1]
            self._json(_epic_detail(project_key, epic_key))
            return
        self.send_error(HTTPStatus.NOT_FOUND)


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(self, state: DashboardServerState):
        super().__init__(("127.0.0.1", 0), DashboardHandler)
        self.state = state


@pytest.fixture
def dashboard_server():
    state = DashboardServerState()
    server = DashboardHTTPServer(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield state, f"http://{host}:{port}/dashboard#/overview"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _wait_for_count(state: DashboardServerState, path: str, minimum: int, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state.count(path) >= minimum:
            return
        time.sleep(0.01)
    raise AssertionError(f"request {path} did not reach count {minimum}")


def _browser():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def test_navigation_during_inflight_refresh_reaches_latest_project_without_stale_error(
    dashboard_server,
) -> None:
    state, url = dashboard_server
    with _browser() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.locator(".portfolio-project-card", has_text="Alpha Project").wait_for()

        state.delay_next("/api/v1/dashboard/overview", 0.8)
        page.locator("#refresh-button").click()
        _wait_for_count(state, "/api/v1/dashboard/overview", 2)
        page.locator(".portfolio-project-card", has_text="Alpha Project").click()

        page.locator("#page-title").filter(has_text="Alpha Project").wait_for(timeout=5000)
        assert page.locator("[data-refresh-warning]").count() == 0
        assert page.locator(".open-work-panel").get_by_text("Verify dashboard navigation").is_visible()
        browser.close()


def test_project_navigation_exposes_busy_feedback_switches_scope_and_supports_history(
    dashboard_server,
) -> None:
    state, url = dashboard_server
    with _browser() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.locator(".portfolio-project-card", has_text="Alpha Project").wait_for()

        state.delay_next("/api/v1/dashboard/projects/alpha", 0.6)
        page.locator(".portfolio-project-card", has_text="Alpha Project").click()
        page.locator("body").wait_for()
        assert page.locator("body").get_attribute("data-navigation-loading") == "true"
        assert page.locator("#app").get_attribute("aria-busy") == "true"
        page.locator("#page-title").filter(has_text="Alpha Project").wait_for(timeout=5000)

        page.locator('.open-work-panel a[href*="#/work/alpha/W-0001"]').click()
        page.locator("#page-title").filter(has_text="W-0001").wait_for(timeout=5000)
        page.go_back()
        page.locator("#page-title").filter(has_text="Alpha Project").wait_for(timeout=5000)
        page.go_forward()
        page.locator("#page-title").filter(has_text="W-0001").wait_for(timeout=5000)
        page.go_back()
        page.locator("#page-title").filter(has_text="Alpha Project").wait_for(timeout=5000)

        state.delay_next("/api/v1/dashboard/projects/beta", 0.4)
        page.locator("#project-scope").select_option("beta")
        assert page.locator("body").get_attribute("data-navigation-loading") == "true"
        page.locator("#page-title").filter(has_text="Beta Project").wait_for(timeout=5000)
        assert page.locator("#project-scope").input_value() == "beta"
        browser.close()


def test_transient_network_failure_preserves_project_and_recovers_on_next_refresh(
    dashboard_server,
) -> None:
    state, url = dashboard_server
    with _browser() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.locator(".portfolio-project-card", has_text="Alpha Project").click()
        page.locator("#page-title").filter(has_text="Alpha Project").wait_for(timeout=5000)
        original_work = page.locator(".open-work-panel").get_by_text("Verify dashboard navigation")
        assert original_work.is_visible()

        state.drop_next("/api/v1/dashboard/overview")
        page.locator("#refresh-button").click()
        warning = page.locator("[data-refresh-warning]")
        warning.wait_for(timeout=5000)
        assert "Не удалось обновить данные" in warning.inner_text()
        assert page.locator("#page-title").inner_text() == "Alpha Project"
        assert original_work.is_visible()
        assert page.locator("#connection-label").inner_text() == "Обновление недоступно"

        page.locator("#refresh-button").click()
        warning.wait_for(state="detached", timeout=5000)
        assert page.locator("#page-title").inner_text() == "Alpha Project"
        assert page.locator("#connection-label").inner_text() == "Система активна"
        browser.close()


def test_project_work_hub_opens_epic_without_losing_project_context(dashboard_server) -> None:
    _state, url = dashboard_server
    with _browser() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.locator(".portfolio-project-card", has_text="Alpha Project").click()
        page.locator("#page-title").filter(has_text="Alpha Project").wait_for(timeout=5000)

        page.get_by_role("link", name="Работа", exact=True).click()
        page.get_by_text("Вся работа проекта в одном месте").wait_for(timeout=5000)
        page.locator('a[href="#/epic/alpha/E-0001"]').click()
        page.locator("#page-title").filter(has_text="E-0001").wait_for(timeout=5000)
        assert page.get_by_text("Dashboard reliability", exact=True).is_visible()
        assert page.locator("#project-scope").input_value() == "alpha"
        browser.close()
