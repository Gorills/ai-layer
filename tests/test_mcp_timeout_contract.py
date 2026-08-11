from __future__ import annotations

import urllib.error

import pytest


def test_context_deadline_has_headroom_over_postgres_statement_timeout():
    from ai_layer.core import mcp_runtime
    from ai_layer.db import session

    assert mcp_runtime.TOOL_TIMEOUTS["context"] >= 15.0
    assert mcp_runtime.TOOL_TIMEOUTS["context"] > (
        session.INTERACTIVE_STATEMENT_TIMEOUT_MS / 1000
    ) + 5.0


def test_memory_context_timeout_is_retryable_read(monkeypatch):
    from ai_layer.core import mcp_runtime
    from ai_layer.domain.errors import ErrorCode

    monkeypatch.setattr(mcp_runtime, "ensure_core_token", lambda: "token")
    monkeypatch.setattr(
        mcp_runtime.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("slow")),
    )

    with pytest.raises(mcp_runtime.CoreRequestTimeout) as caught:
        mcp_runtime._rpc_request("memory_context", {"task": "inspect"}, 0.1)

    error = caught.value
    assert error.code == ErrorCode.CORE_TIMEOUT_RETRYABLE
    assert error.retryable is True
    assert "read-only/replay-safe" in str(error.required_action)
    assert "mutating tool" not in error.message


def test_mutating_timeout_remains_ambiguous(monkeypatch):
    from ai_layer.core import mcp_runtime
    from ai_layer.domain.errors import ErrorCode

    monkeypatch.setattr(mcp_runtime, "ensure_core_token", lambda: "token")
    monkeypatch.setattr(
        mcp_runtime.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("slow")),
    )

    with pytest.raises(mcp_runtime.CoreRequestTimeout) as caught:
        mcp_runtime._rpc_request("task_create", {"goal": "x"}, 0.1)

    error = caught.value
    assert error.code == ErrorCode.CORE_TIMEOUT_AMBIGUOUS
    assert error.retryable is False
    assert "Do not replay a mutating tool blindly" in error.message


def test_replay_safe_connection_loss_is_retryable(monkeypatch):
    from ai_layer.core import mcp_runtime
    from ai_layer.domain.errors import ErrorCode

    monkeypatch.setattr(mcp_runtime, "ensure_core_token", lambda: "token")
    monkeypatch.setattr(
        mcp_runtime.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError(ConnectionResetError("reset"))
        ),
    )

    with pytest.raises(mcp_runtime.CoreRequestTimeout) as caught:
        mcp_runtime._rpc_request("task_next", {}, 0.1)

    error = caught.value
    assert error.code == ErrorCode.CORE_TIMEOUT_RETRYABLE
    assert error.retryable is True


def test_mutating_connection_loss_stays_delivery_ambiguous(monkeypatch):
    from ai_layer.core import mcp_runtime
    from ai_layer.domain.errors import ErrorCode

    monkeypatch.setattr(mcp_runtime, "ensure_core_token", lambda: "token")
    monkeypatch.setattr(
        mcp_runtime.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError(ConnectionResetError("reset"))
        ),
    )

    with pytest.raises(mcp_runtime.CoreRequestTimeout) as caught:
        mcp_runtime._rpc_request("task_stage_delegate", {"worker_id": "w"}, 0.1)

    error = caught.value
    assert error.code == ErrorCode.CORE_DELIVERY_AMBIGUOUS
    assert error.retryable is False
