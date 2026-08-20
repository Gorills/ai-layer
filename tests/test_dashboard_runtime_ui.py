from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/ai_layer/dashboard/static"


def _read(*parts: str) -> str:
    return STATIC.joinpath(*parts).read_text(encoding="utf-8")


def test_dashboard_navigation_queues_latest_route_instead_of_dropping_it() -> None:
    app_js = _read("js", "app.js")

    assert "let loadPromise = null;" in app_js
    assert "let reloadRequested = false;" in app_js
    assert "if (loadPromise)" in app_js
    assert "reloadRequested = true;" in app_js
    assert "routeIsCurrent(current)" in app_js
    assert "if (loading) return;" not in app_js


def test_dashboard_transient_refresh_failure_preserves_rendered_content() -> None:
    app_js = _read("js", "app.js")

    assert "showRefreshWarning(error)" in app_js
    assert "clearRefreshWarning()" in app_js
    assert "Обновление недоступно" in app_js
    assert 'app.innerHTML = `<div class="alert">Ошибка API панели:' not in app_js


def test_dashboard_route_change_reuses_portfolio_cache_and_exposes_busy_feedback() -> None:
    app_js = _read("js", "app.js")
    app_css = _read("css", "app.css")

    hash_handler = next(
        line for line in app_js.splitlines() if 'addEventListener("hashchange"' in line
    )
    assert "resetOverview: true" not in hash_handler
    assert "setNavigationBusy(true)" in hash_handler
    assert "navigationLoading" in app_js
    assert 'body[data-navigation-loading="true"] .topbar' in app_css


def test_dashboard_work_completion_is_compact_and_acknowledges_native_submit() -> None:
    work_js = _read("js", "views", "work.js")
    app_js = _read("js", "app.js")
    app_css = _read("css", "app.css")

    assert 'data-work-complete="true"' in work_js
    assert 'data-work-complete-button="true"' in work_js
    assert "compact-button" in work_js
    assert ">Завершить</button>" in work_js
    assert 'form[data-work-complete="true"]' in app_js
    assert 'button.textContent = "Завершаю…"' in app_js
    assert ".compact-button" in app_css
    assert "white-space: nowrap" in app_css


def test_dashboard_get_requests_have_a_bounded_transport_timeout() -> None:
    api_js = _read("js", "api.js")

    assert "REQUEST_TIMEOUT_MS" in api_js
    assert "AbortController" in api_js
    assert "controller.abort()" in api_js
    assert "signal: controller.signal" in api_js
