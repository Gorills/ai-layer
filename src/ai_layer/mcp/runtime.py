from __future__ import annotations
from ai_layer.core.mcp_runtime import CoreServiceUnavailable
from mcp.server import MCPServer
from pathlib import Path
from ai_layer.core.mcp_runtime import TOOL_TIMEOUTS
from ai_layer.application.transport import get_project as app_get_project
from ai_layer.core.mcp_process import begin_bridge_activity
from ai_layer.mcp.context import bind_project_root
from ai_layer.core.mcp_runtime import call_core_tool
from ai_layer.application.transport import task_current as db_current_task
from ai_layer.core.mcp_process import end_bridge_activity
import functools
import inspect
import os
from ai_layer.mcp.context import resolve_project_root
from ai_layer.core.mcp_runtime import runtime_state
from ai_layer.core.mcp_runtime import start_runtime_warmup
from ai_layer.core.request_context import tool_execution_context
from ai_layer.core.mcp_runtime import tool_runtime_class
from ai_layer.domain.errors import normalize_error
from ai_layer.domain.orchestrator import mcp_bootstrap_instructions

MCP_INSTRUCTIONS = mcp_bootstrap_instructions()

mcp = MCPServer("Local AI Development Layer", instructions=MCP_INSTRUCTIONS)

TOOL_HANDLERS: dict[str, object] = {}


@functools.lru_cache(maxsize=1)
def _configured_tool_catalog() -> tuple[dict, ...]:
    """AI Layer's registered MCP contracts; host-side schema inclusion remains unobservable."""
    catalog = []
    for tool_name, handler in sorted(TOOL_HANDLERS.items()):
        try:
            signature = str(inspect.signature(handler))
        except (TypeError, ValueError):
            signature = "<unavailable>"
        catalog.append(
            {
                "name": tool_name,
                "signature": signature,
                "description": inspect.getdoc(handler) or "",
            }
        )
    return tuple(catalog)


def _telemetry_project_root(func, name: str, args, kwargs) -> str | None:
    try:
        signature = inspect.signature(func)
        if "project_root" not in signature.parameters:
            return None
        bound = signature.bind_partial(*args, **kwargs)
        return resolve_project_root(bound.arguments.get("project_root"), tool=name)
    except Exception:
        return None


def _execute_local_tool(func, name: str, args, kwargs):
    tool_class = tool_runtime_class(name)
    with tool_execution_context(name, tool_class):
        if tool_class == "context" and (
            os.getenv("AI_LAYER_SERVICE_MODE") == "background"
            or os.getenv("AI_LAYER_MCP_BRIDGE") == "1"
        ):
            # Warmup belongs to process/service startup, never to the request's latency budget.
            start_runtime_warmup()
            state = runtime_state()
            if state.get("embeddings") != "warm":
                if state.get("status") == "degraded":
                    raise RuntimeError(
                        "AI_LAYER_CORE_DEGRADED: persistent runtime warmup failed: "
                        + str(state.get("warm_error") or "unknown warmup error")
                    )
                raise RuntimeError(
                    "AI_LAYER_EMBEDDINGS_WARMING: embedding runtime is not ready yet; retry shortly. "
                    "The persistent core warms it outside the interactive request path."
                )
        try:
            result = func(*args, **kwargs)
            try:
                from ai_layer.observability.context_trace import record_tool_delivery

                record_tool_delivery(
                    func,
                    name,
                    args,
                    kwargs,
                    result,
                    mcp_instructions=MCP_INSTRUCTIONS,
                    mcp_tool_catalog=_configured_tool_catalog()
                    if name == "memory_context"
                    else None,
                    resolved_project_root=_telemetry_project_root(func, name, args, kwargs),
                )
            except Exception:
                # Context telemetry is diagnostic only and must never make an MCP tool fail.
                pass
            return result
        except Exception as exc:
            try:
                from ai_layer.observability.context_trace import record_tool_failure

                record_tool_failure(
                    func,
                    name,
                    args,
                    kwargs,
                    exc,
                    resolved_project_root=_telemetry_project_root(func, name, args, kwargs),
                )
            except Exception:
                pass
            raise normalize_error(exc) from exc


def core_tool():
    """Register one schema for both direct Streamable HTTP and the thin stdio bridge."""

    def decorate(func):
        name = func.__name__
        TOOL_HANDLERS[name] = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if os.getenv("AI_LAYER_MCP_BRIDGE") != "1":
                return _execute_local_tool(func, name, args, kwargs)
            signature = inspect.signature(func)
            bound = signature.bind_partial(*args, **kwargs)
            arguments = dict(bound.arguments)
            from uuid import uuid4

            correlation_id = uuid4().hex
            begin_bridge_activity(name, correlation_id, TOOL_TIMEOUTS[tool_runtime_class(name)])
            try:
                try:
                    return call_core_tool(name, arguments)
                except CoreServiceUnavailable:
                    # Availability fallback for headless/non-systemd environments. This remains bounded:
                    # direct execution uses interactive DB deadlines and never runs a full freshness scan.
                    return _execute_local_tool(func, name, args, kwargs)
            finally:
                end_bridge_activity(correlation_id)

        return mcp.tool()(wrapper)

    return decorate


def execute_core_tool(name: str, arguments: dict):
    func = TOOL_HANDLERS.get(name)
    if func is None:
        raise ValueError(f"Unknown AI Layer MCP tool: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("MCP tool arguments must be an object")
    return _execute_local_tool(func, name, (), arguments)


def project_root_for_tool(project_root: str | None, *, tool: str) -> str:
    return resolve_project_root(project_root, tool=tool)


def _project(db, root: str):
    project = app_get_project(db, root)
    bind_project_root(project.root_path)
    return project


def _scoped(result: dict, root: str) -> dict:
    payload = dict(result)
    payload["project_root"] = str(Path(root).expanduser().resolve())
    task = payload.get("task")
    if isinstance(task, dict):
        task = dict(task)
        task["project_root"] = payload["project_root"]
        payload["task"] = task
    return payload


def _text(value: str | None, *, tool: str, field: str) -> str:
    result = (value or "").strip()
    if not result:
        raise ValueError(
            f'{tool}: `{field}` is required. Use {tool}({field}="<text>", project_root="<workspace>").'
        )
    return result


def _list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [str(item).strip() for item in value if str(item).strip()]


def _compact_open_transition(db, project, result: dict) -> dict:
    """Keep next-stage delegation output free of completed-worker self-assessments by default."""
    if result.get("status") not in {"active", "blocked"}:
        return result
    current = db_current_task(db, project, include_history=False)
    compact = dict(current.get("task") or result)
    for key in (
        "input_normalizations",
        "effective_review_verdict",
        "projection_warning",
        "sandbox_cleanup_warning",
        "idempotent",
    ):
        if key in result:
            compact[key] = result[key]
    return compact
