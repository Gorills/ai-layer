from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise SystemExit(f"{label}: marker not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_tasks() -> None:
    path = ROOT / "src/ai_layer/application/tasks.py"
    replace_once(
        path,
        "def read_state(project_root: str | Path) -> dict:",
        "def read_state(project_root: str | Path, *, include_history: bool = True) -> dict:",
        "task projection signature",
    )
    replace_once(
        path,
        "state = current_task(db, project, include_history=True)",
        "state = current_task(db, project, include_history=include_history)",
        "task projection history flag",
    )
    text = path.read_text(encoding="utf-8")
    old = '''            projected_next_action = state.get("next_action") or (
                (current_payload or latest_payload or {}).get("next_action")
            )
            return {
                "current": current_payload,
                "latest": latest_payload,
                "next_action": projected_next_action,
                "source": "database-projection",
            }'''
    new = '''            projected_next_action = state.get("next_action") or (
                (current_payload or latest_payload or {}).get("next_action")
            )
            if current_payload is None and (projected_next_action or {}).get("action") == "create_task":
                projected_next_action = {
                    **projected_next_action,
                    "tool": "task_create",
                    "required": ["goal"],
                    "optional": [
                        "acceptance_criteria",
                        "constraints",
                        "workflow",
                        "risk",
                        "cost_policy",
                    ],
                }
            return {
                "current": current_payload,
                "latest": latest_payload,
                "next_action": projected_next_action,
                "source": "database",
            }'''
    if old in text:
        text = text.replace(old, new, 1)
    elif '"source": "database",' not in text or '"tool": "task_create"' not in text:
        raise SystemExit("task projection compatibility block not found")
    path.write_text(text, encoding="utf-8")


def patch_snapshot() -> None:
    path = ROOT / "src/ai_layer/observability/snapshot.py"
    replace_once(
        path,
        """def _project_snapshot(\n    root: Path,\n    *,\n    include_handoff_text: bool = False,\n    registered: dict | None = None,\n) -> dict:""",
        """def _project_snapshot(\n    root: Path,\n    *,\n    include_handoff_text: bool = False,\n    include_task_history: bool = True,\n    registered: dict | None = None,\n) -> dict:""",
        "project snapshot signature",
    )
    replace_once(
        path,
        "task_state = read_task_state(root)",
        "task_state = read_task_state(root, include_history=include_task_history)",
        "snapshot task read",
    )
    replace_once(
        path,
        '        "task_active": bool(task_state.get("current")),\n        # Kept as low-level compatibility telemetry only; real Task state lives above.',
        '        "task_active": bool(task_state.get("current")),\n        "task_state": task_state,\n        # Kept as low-level compatibility telemetry only; real Task state lives above.',
        "snapshot task state payload",
    )
    replace_once(
        path,
        """def observability_snapshot(\n    project_root: str | Path | None = None,\n    *,\n    all_projects: bool = False,\n    include_handoff_text: bool = False,\n) -> dict:""",
        """def observability_snapshot(\n    project_root: str | Path | None = None,\n    *,\n    all_projects: bool = False,\n    include_handoff_text: bool = False,\n    include_task_history: bool = True,\n) -> dict:""",
        "observability snapshot signature",
    )
    replace_once(
        path,
        """            include_handoff_text=include_handoff_text,\n            registered=registered_for_root.get(str(root.resolve())),""",
        """            include_handoff_text=include_handoff_text,\n            include_task_history=include_task_history,\n            registered=registered_for_root.get(str(root.resolve())),""",
        "observability project snapshot call",
    )


def patch_dashboard_projection() -> None:
    path = ROOT / "src/ai_layer/projections/dashboard.py"
    text = path.read_text(encoding="utf-8")
    if "import time\n" not in text:
        text = text.replace("import hashlib\n", "import hashlib\nimport time\n", 1)
    text = text.replace("from ai_layer.application.tasks import read_state as read_task_state\n", "", 1)

    cache_marker = "from ai_layer.skills.native import native_catalog_files\n\n\n"
    cache_block = """from ai_layer.skills.native import native_catalog_files\n\n_NATIVE_CATALOG_COUNT_TTL_SECONDS = 30.0\n_NATIVE_CATALOG_COUNT_CACHE: dict[str, tuple[float, dict[str, int]]] = {}\n\n\ndef _native_catalog_counts(root: Path) -> dict[str, int]:\n    key = str(root.expanduser().resolve())\n    now = time.monotonic()\n    cached = _NATIVE_CATALOG_COUNT_CACHE.get(key)\n    if cached is not None and now - cached[0] < _NATIVE_CATALOG_COUNT_TTL_SECONDS:\n        return dict(cached[1])\n    catalogs = native_catalog_files(root)\n    counts = {host: len(paths) for host, paths in catalogs.items()}\n    _NATIVE_CATALOG_COUNT_CACHE[key] = (now, dict(counts))\n    return counts\n\n\n"""
    if "_NATIVE_CATALOG_COUNT_CACHE" not in text:
        if cache_marker not in text:
            raise SystemExit("dashboard native catalog import marker not found")
        text = text.replace(cache_marker, cache_block, 1)

    text = text.replace(
        "    catalogs = native_catalog_files(root)\n    return {",
        "    catalog_counts = _native_catalog_counts(root)\n    return {",
        1,
    )
    text = text.replace(
        '        "configured_catalog": {host: len(paths) for host, paths in catalogs.items()},',
        '        "configured_catalog": catalog_counts,',
        1,
    )
    text = text.replace(
        "snapshot = observability_snapshot(all_projects=True, include_handoff_text=False)",
        "snapshot = observability_snapshot(\n        all_projects=True, include_handoff_text=False, include_task_history=False\n    )",
        1,
    )
    count = text.count("task_state = read_task_state(root)")
    if count not in {0, 2}:
        raise SystemExit(f"unexpected duplicate dashboard Task reads: {count}")
    text = text.replace(
        "task_state = read_task_state(root)",
        'task_state = project.get("task_state") or {}',
    )
    if "read_task_state" in text:
        raise SystemExit("dashboard projection still references read_task_state")
    path.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    path = ROOT / "tests/test_epic_dashboard.py"
    text = path.read_text(encoding="utf-8")
    old = '''    monkeypatch.setattr(\n        epic_projection.epic_uc,\n        "list_for_project",\n        lambda resolved, include_archived=True: [\n            {\n                "key": "E-0001",\n                "title": "Durable Epic",\n                "status": "running",\n                "current_spec_version": 2,\n                "approved_spec_version": 1,\n                "execution_spec_version": 2,\n                "plan": [],\n            }\n        ],\n    )'''
    new = '''    monkeypatch.setattr(\n        epic_projection,\n        "_list_epic_summaries",\n        lambda resolved: [\n            {\n                "key": "E-0001",\n                "title": "Durable Epic",\n                "status": "running",\n                "current_spec_version": 2,\n                "approved_spec_version": 1,\n                "execution_spec_version": 2,\n                "plan_version": 1,\n            }\n        ],\n    )'''
    if old in text:
        text = text.replace(old, new, 1)
    elif "_list_epic_summaries" not in text:
        raise SystemExit("Epic Dashboard summary test marker not found")
    path.write_text(text, encoding="utf-8")

    path = ROOT / "tests/test_dashboard.py"
    text = path.read_text(encoding="utf-8")
    if "test_dashboard_task_projection_never_calls_authoritative_navigator" not in text:
        text += r'''


def test_dashboard_task_projection_never_calls_authoritative_navigator(monkeypatch, tmp_path: Path):
    from contextlib import contextmanager

    import ai_layer.application.tasks as task_app

    @contextmanager
    def fake_scope():
        yield object()

    monkeypatch.setattr(task_app, "session_scope", fake_scope)
    monkeypatch.setattr(task_app, "_project", lambda db, root: object())
    monkeypatch.setattr(
        task_app,
        "current_task",
        lambda db, project, include_history=True: {
            "active": True,
            "state": "active",
            "task": {
                "key": "T-0001",
                "status": "active",
                "next_action": {"action": "delegate_stage"},
            },
        },
    )
    monkeypatch.setattr(
        task_app,
        "next_task_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Dashboard projection must not enter task_next repository guards")
        ),
    )

    state = task_app.read_state(tmp_path, include_history=False)

    assert state["source"] == "database"
    assert state["current"]["key"] == "T-0001"
    assert state["next_action"]["action"] == "delegate_stage"


def test_dashboard_native_catalog_counts_are_cached_between_polls(monkeypatch, tmp_path: Path):
    import ai_layer.projections.dashboard as dashboard_service

    root = tmp_path / "project"
    root.mkdir()
    calls = 0

    def catalog(project_root):
        nonlocal calls
        calls += 1
        return {"cursor": [Path("a")], "codex": [Path("a")], "antigravity": [Path("b")]}

    dashboard_service._NATIVE_CATALOG_COUNT_CACHE.clear()
    monkeypatch.setattr(dashboard_service, "native_catalog_files", catalog)
    first = dashboard_service._task_skill_state(root, None, [])
    second = dashboard_service._task_skill_state(root, None, [])
    dashboard_service._NATIVE_CATALOG_COUNT_CACHE.clear()

    assert calls == 1
    assert first["configured_catalog"] == second["configured_catalog"]
    assert first["configured_catalog"]["cursor"] == 1


def test_dashboard_frontend_uses_adaptive_visibility_aware_polling():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "src/ai_layer/dashboard/static/js/app.js").read_text(encoding="utf-8")

    assert "setInterval(load, 2000)" not in app_js
    assert "ACTIVE_POLL_MS = 3000" in app_js
    assert "IDLE_POLL_MS = 12000" in app_js
    assert "document.hidden" in app_js
    assert "visibilitychange" in app_js
    assert "setTimeout" in app_js
    assert "semanticFingerprint" in app_js
'''
    else:
        text = text.replace('assert state["source"] == "database-projection"', 'assert state["source"] == "database"')
    path.write_text(text, encoding="utf-8")

    path = ROOT / "tests/test_tasks.py"
    text = path.read_text(encoding="utf-8")
    old_name = "def test_dashboard_state_uses_authoritative_task_next_navigation(tmp_path: Path, monkeypatch):"
    if old_name in text:
        start = text.index(old_name)
        next_name = "\ndef test_dashboard_state_exposes_create_task_navigation_when_only_historical_task_remains("
        end = text.index(next_name, start)
        replacement = '''def test_dashboard_state_is_projection_only_and_task_next_owns_repository_guards(\n    tmp_path: Path, monkeypatch\n):\n    from contextlib import contextmanager\n\n    from ai_layer.application import tasks as application_tasks\n\n    db, project, root = _db_project(tmp_path)\n    try:\n        tasks.create_task(\n            db, project, goal="Dashboard projection nav", acceptance_criteria=[], constraints=[]\n        )\n        (root / "app.py").write_text("VALUE = 99\\n", encoding="utf-8")\n\n        @contextmanager\n        def fake_scope():\n            yield db\n\n        monkeypatch.setattr(application_tasks, "session_scope", fake_scope)\n        dashboard = read_task_state(root)\n        assert dashboard["source"] == "database"\n        assert dashboard["next_action"]["action"] == "delegate_stage"\n        assert dashboard["current"]["next_action"] == dashboard["next_action"]\n\n        authoritative = tasks.next_task_action(db, project)\n        assert authoritative["next_action"]["action"] == "unmanaged_stage_mutation"\n        assert authoritative["next_action"]["code"] == "UNMANAGED_STAGE_MUTATION"\n    finally:\n        db.close()\n\n'''
        text = text[:start] + replacement + text[end + 1 :]
    elif "test_dashboard_state_is_projection_only_and_task_next_owns_repository_guards" not in text:
        raise SystemExit("old Dashboard authoritative-navigation test not found")
    path.write_text(text, encoding="utf-8")


def patch_release_metadata() -> None:
    replace_once(
        ROOT / "pyproject.toml",
        'version = "0.12.1"',
        'version = "0.12.2"',
        "pyproject version",
    )
    replace_once(
        ROOT / "src/ai_layer/__init__.py",
        '__version__ = "0.12.1"',
        '__version__ = "0.12.2"',
        "package version",
    )
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    if "## 0.12.2 — Dashboard background-load fix" not in text:
        header = "# Changelog\n\n"
        if not text.startswith(header):
            raise SystemExit("Changelog header not found")
        section = """## 0.12.2 — Dashboard background-load fix\n\n- Removed the Dashboard projection dependency on authoritative `task_next` navigation, so passive refreshes no longer trigger repository drift/provenance scans or repository hashing.\n- Reused Task state already captured by observability snapshots and made overview Task history lightweight, eliminating duplicate per-project Task reads.\n- Replaced the project Epic list N+1/full-history expansion with a lightweight summary query containing only list-view fields.\n- Cached native skill catalog counts between project-detail polls instead of rereading every descriptor on each refresh.\n- Replaced unconditional 2-second polling with visibility-aware adaptive polling: 3 seconds while work is active, 12 seconds while idle, and no polling for hidden tabs.\n- Avoided full Dashboard DOM reconstruction when only volatile generated-at/uptime/idle counters changed.\n- No Task/Epic transition semantics, provenance guard, schema, privacy mode or verification behavior changed.\n\n"""
        text = header + section + text[len(header) :]
        path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_tasks()
    patch_snapshot()
    patch_dashboard_projection()
    patch_tests()
    patch_release_metadata()


if __name__ == "__main__":
    main()
