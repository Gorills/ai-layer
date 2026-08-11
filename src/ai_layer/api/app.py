from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from ai_layer import __version__
from ai_layer.application.context import (
    get_memory_context,
    project_details,
    search_decisions,
    search_memory,
)
from ai_layer.application.recovery import recovery_status, worker_recovery_lifespan
from ai_layer.application.runtime import database_health
from ai_layer.core.background_service import service_runtime_payload
from ai_layer.core.mcp_runtime import (
    CORE_TOKEN_HEADER,
    start_runtime_warmup,
    validate_core_token,
)
from ai_layer.core.mcp_runtime import (
    runtime_state as core_runtime_state,
)
from ai_layer.dashboard.api import router as dashboard_api_router
from ai_layer.dashboard.web import router as dashboard_web_router
from ai_layer.dashboard.web import static_files
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError, normalize_error


class SearchRequest(BaseModel):
    project_root: str
    query: str
    limit: int = Field(default=8, ge=1, le=30)


class ToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ContextRequest(BaseModel):
    project_root: str
    task: str | None = None
    query: str | None = None
    limit: int = Field(default=4, ge=1, le=12)

    def resolved_task(self) -> str:
        value = (self.task or self.query or "").strip()
        if not value:
            raise ValueError("memory context requires `task` (preferred) or legacy `query`")
        return value


def _health_payload(*, include_database: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "version": __version__,
        "service": service_runtime_payload(),
        "runtime": core_runtime_state(),
        "worker_recovery": recovery_status(),
    }
    if include_database:
        payload["database"] = database_health()
    return payload


def _http_error(exc: BaseException, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=normalize_error(exc).to_dict())


def _mcp_transport(mcp_server: Any) -> tuple[Any | None, Any | None]:
    mcp_http_app = None
    session_manager = None
    streamable = getattr(mcp_server, "streamable_http_app", None)
    if callable(streamable):
        try:
            # MCP SDK 2.x creates the Streamable HTTP session manager lazily here.
            mcp_http_app = streamable(
                streamable_http_path="/", stateless_http=True, json_response=True
            )
        except TypeError:
            # Keep health/dashboard/stdio usable with an incompatible host SDK.
            mcp_http_app = None
    if mcp_http_app is not None:
        try:
            session_manager = mcp_server.session_manager
        except (AttributeError, RuntimeError):
            session_manager = None
    return mcp_http_app, session_manager


def create_app() -> FastAPI:
    # Import after core modules so tests can still provide a minimal MCP SDK shim.
    from ai_layer.mcp.server import execute_core_tool
    from ai_layer.mcp.server import mcp as mcp_server

    mcp_http_app, session_manager = _mcp_transport(mcp_server)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        start_runtime_warmup()
        async with worker_recovery_lifespan():
            if session_manager is not None and hasattr(session_manager, "run"):
                async with session_manager.run():
                    yield
            else:
                yield

    app = FastAPI(title="Local AI Development Layer", version=__version__, lifespan=lifespan)
    app.include_router(dashboard_api_router)
    app.include_router(dashboard_web_router)
    app.mount("/dashboard-assets", static_files(), name="dashboard-assets")
    if mcp_http_app is not None:
        # Direct Streamable HTTP transport for capable hosts; stdio remains a compatibility bridge.
        app.mount("/mcp", mcp_http_app, name="mcp")

    @app.get("/health/live")
    def health_live():
        return _health_payload(include_database=False)

    @app.get("/health")
    def health():
        return {
            **_health_payload(include_database=True),
            "mcp_http": "/mcp/" if mcp_http_app is not None else None,
        }

    @app.post("/internal/mcp/tools/{tool}")
    def internal_mcp_tool(
        tool: str,
        req: ToolCallRequest,
        core_token: str | None = Header(default=None, alias=CORE_TOKEN_HEADER),
        bridge_version: str | None = Header(default=None, alias="X-AI-Layer-Bridge-Version"),
    ):
        if not validate_core_token(core_token):
            raise _http_error(
                StructuredError(
                    code=ErrorCode.REQUEST_UNAUTHORIZED,
                    category=ErrorCategory.TRANSPORT,
                    message="Invalid AI Layer core token.",
                    retryable=False,
                    required_action="Use the machine-local core token owned by the active runtime.",
                ),
                status_code=403,
            )
        if bridge_version and bridge_version != __version__:
            raise _http_error(
                StructuredError(
                    code=ErrorCode.VERSION_MISMATCH,
                    category=ErrorCategory.TRANSPORT,
                    message=f"AI Layer bridge/core version mismatch: bridge={bridge_version}, core={__version__}",
                    retryable=False,
                    required_action="Restart/reconcile AI Layer so bridge and core use the same immutable release.",
                ),
                status_code=409,
            )
        try:
            return {"ok": True, "result": execute_core_tool(tool, req.arguments)}
        except Exception as exc:
            return {"ok": False, "error": normalize_error(exc).to_dict()}

    @app.get("/projects/info")
    def info(project_root: str):
        try:
            return project_details(project_root)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/memory/search")
    def search(req: SearchRequest):
        try:
            return search_memory(req.project_root, req.query, req.limit)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/memory/context")
    def context(req: ContextRequest):
        try:
            return get_memory_context(req.project_root, req.resolved_task(), req.limit)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/decisions/search")
    def decisions(req: SearchRequest):
        try:
            return search_decisions(req.project_root, req.query, req.limit)
        except Exception as exc:
            raise _http_error(exc) from exc

    return app


app = create_app()
