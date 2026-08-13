from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from ai_layer.core.request_context import current_operation
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.observability.work_events import append_contextual_event


def _uuid(value: object):
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _result_context(result: object) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    work = result.get("work") if isinstance(result.get("work"), dict) else {}
    root_run = result.get("root_run") if isinstance(result.get("root_run"), dict) else {}
    return {
        "work_id": _uuid(work.get("id")),
        "run_id": _uuid(root_run.get("id")),
        "host": str(root_run.get("host") or "")[:64],
        "client": str(root_run.get("client") or "")[:64],
        "session_id": str(root_run.get("session_id") or "")[:128],
        "turn_id": str(root_run.get("turn_id") or "")[:128],
        "model": str(root_run.get("model") or "")[:128],
    }


def record_mcp_terminal(
    *,
    tool: str,
    project_root: str | None,
    duration_ms: float,
    result: object = None,
    error: BaseException | None = None,
) -> None:
    """Best-effort safe terminal journal entry for the common MCP execution path."""
    if not project_root:
        return
    operation = current_operation()
    if operation is None:
        return
    linked = _result_context(result)
    root = Path(project_root).expanduser().resolve()
    with session_scope() as db:
        project = get_project(db, root)
        append_contextual_event(
            db,
            event_type="OperationFailed" if error is not None else "OperationCompleted",
            project=project,
            aggregate_type="operation",
            aggregate_id=operation.correlation_id,
            work_id=linked.get("work_id"),
            run_id=linked.get("run_id"),
            host=linked.get("host", ""),
            client=linked.get("client", ""),
            session_id=linked.get("session_id", ""),
            turn_id=linked.get("turn_id", ""),
            model=linked.get("model", ""),
            payload={
                "tool": str(tool)[:128],
                "status": "failed" if error is not None else "completed",
                "duration_ms": round(max(0.0, float(duration_ms)), 2),
                "error_type": type(error).__name__ if error is not None else None,
            },
            importance="high" if error is not None else "normal",
        )
