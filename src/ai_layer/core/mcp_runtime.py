from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ai_layer import __version__
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.core.config import get_settings

CORE_HOST = "127.0.0.1"
CORE_PORT = 8765
CORE_BASE_URL = f"http://{CORE_HOST}:{CORE_PORT}"
CORE_RPC_PREFIX = "/internal/mcp/tools"
CORE_MCP_HTTP_URL = f"{CORE_BASE_URL}/mcp/"
CORE_TOKEN_HEADER = "X-AI-Layer-Core-Token"

FAST_TOOLS = {
    "project_info", "task_current", "task_next", "task_stage_delegate",
    "task_discovery_complete", "task_implementation_complete", "task_review_complete", "task_fix_complete",
    "task_stage_complete", "task_worker_disconnected", "task_worker_heartbeat", "task_resume", "task_cancel", "task_create", "task_adopt",
    "skill_list", "skill_search", "skill_get", "skill_set_enabled", "skill_remove",
    "skill_info", "session_list", "session_restore", "session_save", "knowledge_list",
    "review_sandbox_prepare", "review_sandbox_cleanup",
}
CONTEXT_TOOLS = {"memory_context", "memory_search", "decision_search"}
LONG_TOOLS = {
    "review_check_run", "verification_run", "skill_project_create", "skill_import", "skill_install", "skill_update", "knowledge_draft_upsert",
}
TOOL_TIMEOUTS = {"fast": 5.0, "context": 6.0, "long": 120.0}

_STATE_LOCK = threading.Lock()
_RUNTIME_STATE: dict[str, Any] = {
    "status": "starting",
    "database": "unknown",
    "embeddings": "cold",
    "warm_started_at": None,
    "warm_completed_at": None,
    "warm_error": None,
}
_WARM_THREAD: threading.Thread | None = None
_WARM_LAST_STARTED = 0.0
WARM_RETRY_SECONDS = 5.0
_HEALTH_OK_UNTIL = 0.0
_HEALTH_LOCK = threading.Lock()
HEALTH_CACHE_SECONDS = 2.0


def tool_runtime_class(tool: str) -> str:
    if tool in CONTEXT_TOOLS:
        return "context"
    if tool in LONG_TOOLS:
        return "long"
    return "fast"


def core_token_path() -> Path:
    return get_settings().machine_runtime_dir / "core.token"


def ensure_core_token() -> str:
    path = core_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer core token: {path}")
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
        raise RuntimeError(f"AI Layer core token is malformed: {path}")
    token = secrets.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return ensure_core_token()
    try:
        os.write(fd, (token + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return token


def validate_core_token(value: str | None) -> bool:
    try:
        expected = ensure_core_token()
    except Exception:
        return False
    return bool(value) and secrets.compare_digest(value, expected)


def _set_runtime_state(**updates: Any) -> None:
    with _STATE_LOCK:
        _RUNTIME_STATE.update(updates)


def runtime_state() -> dict[str, Any]:
    with _STATE_LOCK:
        result = dict(_RUNTIME_STATE)
    result.update({
        "version": __version__,
        "mcp_http_url": CORE_MCP_HTTP_URL,
        "rpc_url": CORE_BASE_URL,
    })
    return result


def _warm_runtime() -> None:
    started = time.time()
    _set_runtime_state(status="warming", warm_started_at=started, warm_error=None)
    try:
        from ai_layer.db.session import database_status, get_engine
        get_engine()
        db = database_status()
        if not db.get("connected"):
            raise RuntimeError(db.get("error") or "database unavailable")
        _set_runtime_state(database="ready")
        from ai_layer.memory.embeddings import get_embedder
        get_embedder().embed(["ai-layer-runtime-warmup"])
        _set_runtime_state(
            embeddings="warm",
            status="ready",
            warm_completed_at=time.time(),
            warm_error=None,
        )
    except Exception as exc:
        _set_runtime_state(
            status="degraded",
            warm_completed_at=time.time(),
            warm_error=f"{type(exc).__name__}: {exc}"[:400],
            embeddings="failed" if runtime_state().get("embeddings") != "warm" else "warm",
        )


def start_runtime_warmup() -> None:
    global _WARM_THREAD, _WARM_LAST_STARTED
    ensure_core_token()
    now = time.monotonic()
    with _STATE_LOCK:
        if _RUNTIME_STATE.get("status") == "ready" and _RUNTIME_STATE.get("embeddings") == "warm":
            return
        if _WARM_THREAD is not None and _WARM_THREAD.is_alive():
            return
        if _WARM_LAST_STARTED and now - _WARM_LAST_STARTED < WARM_RETRY_SECONDS:
            return
        _WARM_LAST_STARTED = now
        _WARM_THREAD = threading.Thread(target=_warm_runtime, name="ai-layer-warmup", daemon=True)
        _WARM_THREAD.start()


class CoreServiceUnavailable(StructuredError):
    def __init__(self, message: str):
        super().__init__(
            code=ErrorCode.CORE_UNAVAILABLE,
            category=ErrorCategory.TRANSPORT,
            message=message,
            retryable=True,
            required_action="Restore/restart the persistent AI Layer core and retry.",
        )


class CoreRequestTimeout(StructuredError):
    def __init__(self, message: str, *, code: ErrorCode = ErrorCode.CORE_TIMEOUT_AMBIGUOUS):
        super().__init__(
            code=code,
            category=ErrorCategory.TRANSPORT,
            message=message,
            retryable=False,
            required_action="Read durable task state before deciding whether replay is safe.",
        )


class CoreProtocolError(StructuredError):
    def __init__(self, message: str):
        super().__init__(
            code=ErrorCode.CORE_PROTOCOL_ERROR,
            category=ErrorCategory.TRANSPORT,
            message=message,
            retryable=False,
            required_action="Verify bridge/core version and run AI Layer diagnostics before retrying.",
        )


def _rpc_request(tool: str, arguments: dict[str, Any], timeout: float) -> Any:
    token = ensure_core_token()
    body = json.dumps({"arguments": arguments}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{CORE_BASE_URL}{CORE_RPC_PREFIX}/{tool}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            CORE_TOKEN_HEADER: token,
            "X-AI-Layer-Bridge-Version": __version__,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback only
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            detail = str(exc)
        raise CoreProtocolError(
            f"Core rejected bridge request for `{tool}` with HTTP {exc.code}: {detail}"
        ) from exc
    except TimeoutError as exc:
        raise CoreRequestTimeout(
            f"`{tool}` exceeded {timeout:g}s after dispatch. Do not replay a mutating tool blindly; "
            "call task_next/current state to recover."
        ) from exc
    except urllib.error.URLError as exc:
        # Once urlopen() has been attempted, delivery is ambiguous: a connection reset can happen
        # after the core accepted the request. Never turn this into a local replay opportunity.
        reason = getattr(exc, "reason", None)
        detail = f"{type(reason).__name__}: {reason}" if reason is not None else str(exc)
        raise CoreRequestTimeout(
            f"`{tool}` lost its core RPC connection after dispatch ({detail}). Do not replay a mutating tool "
            "blindly; call task_next/current state to recover.",
            code=ErrorCode.CORE_DELIVERY_AMBIGUOUS,
        ) from exc
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise CoreProtocolError(f"Invalid core response for `{tool}`: {exc}") from exc
    if not isinstance(payload, dict):
        raise CoreProtocolError("Core returned a non-object response")
    if not payload.get("ok"):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            raise StructuredError.from_dict(error_payload)
        # Compatibility with pre-0.9 internal responses during an interrupted local upgrade.
        message = str(error_payload or "AI Layer core tool failed")
        raise CoreProtocolError(f"Legacy core error response for `{tool}`: {message}")
    return payload.get("result")


def call_core_tool(tool: str, arguments: dict[str, Any]) -> Any:
    global _HEALTH_OK_UNTIL
    tool_class = tool_runtime_class(tool)
    timeout = TOOL_TIMEOUTS[tool_class]
    from ai_layer.core.background_service import probe_service, start_user_service

    now = time.monotonic()
    with _HEALTH_LOCK:
        recently_healthy = now < _HEALTH_OK_UNTIL
    if not recently_healthy:
        health = probe_service(timeout=0.25)
        if not health.get("running"):
            started = start_user_service()
            if not started.get("ok"):
                raise CoreServiceUnavailable(
                    "Persistent core is not reachable and automatic restart failed: "
                    + str(started.get("error") or started.get("reason") or "unknown service error")
                )
        with _HEALTH_LOCK:
            _HEALTH_OK_UNTIL = time.monotonic() + HEALTH_CACHE_SECONDS
    try:
        result = _rpc_request(tool, arguments, timeout)
    except (CoreServiceUnavailable, CoreRequestTimeout, CoreProtocolError):
        # Force a fresh liveness probe on the next call. Only pre-dispatch unavailability
        # is eligible for local fallback in the stdio bridge.
        with _HEALTH_LOCK:
            _HEALTH_OK_UNTIL = 0.0
        raise
    with _HEALTH_LOCK:
        _HEALTH_OK_UNTIL = time.monotonic() + HEALTH_CACHE_SECONDS
    return result
