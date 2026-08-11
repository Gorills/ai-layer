from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace


def test_core_token_is_private_and_stable(monkeypatch, tmp_path: Path):
    from ai_layer.core import mcp_runtime

    monkeypatch.setattr(
        mcp_runtime,
        "get_settings",
        lambda: SimpleNamespace(machine_runtime_dir=tmp_path / "runtime"),
    )
    first = mcp_runtime.ensure_core_token()
    second = mcp_runtime.ensure_core_token()
    path = tmp_path / "runtime" / "core.token"

    assert first == second
    assert len(first) >= 32
    assert path.exists()
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_core_tool_client_uses_persistent_service_and_deadline(monkeypatch):
    from ai_layer.core import background_service, mcp_runtime

    seen = {}
    monkeypatch.setattr(background_service, "probe_service", lambda timeout=0.25: {"running": True})
    monkeypatch.setattr(
        mcp_runtime,
        "_rpc_request",
        lambda tool, arguments, timeout: (
            seen.update(tool=tool, arguments=arguments, timeout=timeout) or {"ok": True}
        ),
    )

    result = mcp_runtime.call_core_tool("task_next", {"project_root": "/tmp/project"})
    assert result == {"ok": True}
    assert seen["tool"] == "task_next"
    assert seen["timeout"] == mcp_runtime.TOOL_TIMEOUTS["fast"]


def test_ready_runtime_does_not_rewarm_on_every_context_call(monkeypatch):
    from ai_layer.core import mcp_runtime

    monkeypatch.setattr(mcp_runtime, "ensure_core_token", lambda: "token")
    monkeypatch.setattr(mcp_runtime, "_WARM_THREAD", None)
    monkeypatch.setattr(mcp_runtime, "_WARM_LAST_STARTED", 0.0)
    with mcp_runtime._STATE_LOCK:
        previous = dict(mcp_runtime._RUNTIME_STATE)
        mcp_runtime._RUNTIME_STATE.update(status="ready", embeddings="warm")
    started = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            started.append(True)

        def is_alive(self):
            return False

        def start(self):
            pass

    monkeypatch.setattr(mcp_runtime.threading, "Thread", FakeThread)
    try:
        mcp_runtime.start_runtime_warmup()
        assert started == []
    finally:
        with mcp_runtime._STATE_LOCK:
            mcp_runtime._RUNTIME_STATE.clear()
            mcp_runtime._RUNTIME_STATE.update(previous)


def test_bridge_wrapper_proxies_without_executing_local_handler(monkeypatch):
    from ai_layer.mcp import server
    from ai_layer.mcp import runtime as mcp_runtime

    monkeypatch.setenv("AI_LAYER_MCP_BRIDGE", "1")
    monkeypatch.setattr(mcp_runtime, "begin_bridge_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_runtime, "end_bridge_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mcp_runtime,
        "call_core_tool",
        lambda name, arguments: {"tool": name, "arguments": arguments},
    )

    result = server.project_info(project_root="/tmp/example")
    assert result["tool"] == "project_info"
    assert result["arguments"]["project_root"] == "/tmp/example"


def test_interactive_freshness_never_runs_full_refresh(monkeypatch):
    from ai_layer.memory import refresh_runtime

    project = SimpleNamespace(root_path="/tmp/project")
    monkeypatch.setattr(
        refresh_runtime,
        "probe_memory_freshness",
        lambda project: {
            "status": "stale",
            "snapshot_available": True,
            "changed_paths": ["app.py"],
        },
    )
    monkeypatch.setattr(refresh_runtime, "schedule_refresh", lambda project: {"status": "queued"})
    monkeypatch.setattr(
        refresh_runtime,
        "ensure_memory_fresh",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("full refresh must not run inline")
        ),
    )

    result = refresh_runtime.interactive_freshness(project)
    assert result["status"] == "refreshing"
    assert result["background_refresh"] is True
    assert result["changed_paths"] == ["app.py"]
    assert "last stable" in result["read_contract"]


def test_refresh_queue_is_single_flight(monkeypatch):
    from ai_layer.memory import refresh_runtime

    queued = []

    class FakeQueue:
        def put(self, value):
            queued.append(value)

    monkeypatch.setattr(refresh_runtime, "_ensure_worker", lambda: None)
    monkeypatch.setattr(refresh_runtime, "_QUEUE", FakeQueue())
    refresh_runtime._IN_FLIGHT.clear()
    refresh_runtime._JOBS.clear()
    project = SimpleNamespace(root_path="/tmp/single-flight")

    refresh_runtime.schedule_refresh(project)
    refresh_runtime.schedule_refresh(project)
    assert queued == ["/tmp/single-flight"]


def test_refresh_worker_is_daemon(monkeypatch):
    from ai_layer.memory import refresh_runtime

    monkeypatch.setattr(refresh_runtime, "_WORKER", None)
    refresh_runtime._ensure_worker()
    assert refresh_runtime._WORKER is not None
    assert refresh_runtime._WORKER.daemon is True


def test_postgres_engine_has_fail_fast_connect_and_pool_deadlines():
    from ai_layer.db import session

    options = session._engine_options("postgresql+psycopg://u:p@127.0.0.1:5432/db")
    assert options["connect_args"]["connect_timeout"] == 2
    assert options["pool_timeout"] == 2


def test_interactive_git_probe_has_total_budget(monkeypatch, tmp_path: Path):
    from ai_layer.memory import identity

    timeouts = []

    class Proc:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout = stdout
            self.returncode = returncode

    def fake_run(command, **kwargs):
        timeouts.append(float(kwargs["timeout"]))
        if "--is-inside-work-tree" in command:
            return Proc(stdout="true\n")
        if "HEAD" in command:
            return Proc(stdout="abc\n")
        return Proc(stdout=b"")

    monkeypatch.setattr(identity.shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(identity.subprocess, "run", fake_run)
    result = identity.repository_probe(tmp_path, budget_seconds=0.75)

    assert result["kind"] == "git-v1"
    assert all(timeout <= 0.75 for timeout in timeouts)


def test_systemd_runtime_restarts_always():
    from ai_layer.core import background_service

    text = background_service._unit_content()
    assert "Restart=always" in text
    assert "RestartSec=1" in text


def test_ambiguous_core_timeout_is_not_replayed_locally(monkeypatch):
    from ai_layer.core.mcp_runtime import CoreRequestTimeout
    from ai_layer.mcp import server
    from ai_layer.mcp import runtime as mcp_runtime
    from ai_layer.mcp.tools import project_context as project_tools

    monkeypatch.setenv("AI_LAYER_MCP_BRIDGE", "1")
    monkeypatch.setattr(mcp_runtime, "begin_bridge_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_runtime, "end_bridge_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mcp_runtime,
        "call_core_tool",
        lambda *args, **kwargs: (_ for _ in ()).throw(CoreRequestTimeout("ambiguous timeout")),
    )
    monkeypatch.setattr(
        project_tools,
        "get_project_info",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not replay locally")),
    )

    import pytest

    with pytest.raises(CoreRequestTimeout, match="ambiguous timeout"):
        server.project_info(project_root="/tmp/example")


def test_connection_loss_after_dispatch_is_ambiguous(monkeypatch):
    import urllib.error
    import pytest
    from ai_layer.core import mcp_runtime

    monkeypatch.setattr(mcp_runtime, "ensure_core_token", lambda: "token")
    monkeypatch.setattr(
        mcp_runtime.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError(ConnectionResetError("reset"))
        ),
    )
    with pytest.raises(mcp_runtime.CoreRequestTimeout, match="DELIVERY_AMBIGUOUS"):
        mcp_runtime._rpc_request("task_stage_delegate", {"worker_id": "w"}, 1.0)


def test_internal_core_rpc_requires_token_and_dispatches(monkeypatch):
    from fastapi.testclient import TestClient
    from ai_layer.api import app as api_module
    from ai_layer.mcp import server

    monkeypatch.setattr(api_module, "start_runtime_warmup", lambda: None)
    monkeypatch.setattr(api_module, "validate_core_token", lambda token: token == "good-token")
    monkeypatch.setattr(
        server, "execute_core_tool", lambda name, arguments: {"name": name, "arguments": arguments}
    )
    app = api_module.create_app()
    with TestClient(app) as client:
        denied = client.post("/internal/mcp/tools/task_next", json={"arguments": {}})
        assert denied.status_code == 403
        allowed = client.post(
            "/internal/mcp/tools/task_next",
            json={"arguments": {"project_root": "/tmp/p"}},
            headers={
                "X-AI-Layer-Core-Token": "good-token",
                "X-AI-Layer-Bridge-Version": api_module.__version__,
            },
        )
    assert allowed.status_code == 200
    assert allowed.json()["result"]["name"] == "task_next"


def test_create_app_initializes_streamable_http_before_session_manager(monkeypatch):
    """MCP SDK 2.x session_manager is lazy and raises before streamable_http_app()."""
    from fastapi import FastAPI
    from ai_layer.api import app as api_module
    from ai_layer.mcp import server

    events: list[str] = []

    class LazyMcpServer:
        def __init__(self):
            self.initialized = False
            self._manager = object()

        @property
        def session_manager(self):
            events.append("session_manager")
            if not self.initialized:
                raise RuntimeError(
                    "Session manager can only be accessed after calling streamable_http_app()."
                )
            return self._manager

        def streamable_http_app(self, **kwargs):
            events.append("streamable_http_app")
            self.initialized = True
            return FastAPI()

    fake_mcp = LazyMcpServer()
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(api_module, "start_runtime_warmup", lambda: None)

    app = api_module.create_app()

    assert app is not None
    assert events[:2] == ["streamable_http_app", "session_manager"]
