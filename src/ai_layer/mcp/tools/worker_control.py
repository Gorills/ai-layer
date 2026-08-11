from __future__ import annotations

from ai_layer.application.transport import application_scope as session_scope
from ai_layer.application.transport import task_worker_disconnected as db_worker_disconnected
from ai_layer.application.transport import task_worker_heartbeat as db_worker_heartbeat
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import _project, _scoped, _text, core_tool, project_root_for_tool


def task_worker_heartbeat(
    worker_id: str,
    project_root: str | None = None,
    lease_seconds: int | None = None,
) -> dict:
    """HOST CONTROL: renew the durable lease for the currently bound worker without changing task state."""
    root = project_root_for_tool(project_root, tool="task_worker_heartbeat")
    worker = _text(worker_id, tool="task_worker_heartbeat", field="worker_id")
    with mcp_audit(
        root,
        "task_worker_heartbeat",
        arg_keys=["worker_id", "lease_seconds", "project_root"],
    ) as audit:
        with session_scope() as scope:
            project = _project(scope, root)
            result = db_worker_heartbeat(
                scope,
                project,
                worker_id=worker,
                lease_seconds=lease_seconds,
            )
            stage = result.get("active_stage") or {}
            audit["metrics"] = {
                "task": result.get("key"),
                "stage": stage.get("kind"),
                "worker_id": stage.get("worker_id"),
                "lease_expires_at": stage.get("worker_lease_expires_at"),
            }
            return _scoped(result, root)


def task_worker_disconnected(reason: str, project_root: str | None = None) -> dict:
    """ORCHESTRATOR RECOVERY: report that the currently bound worker disconnected unexpectedly."""
    root = project_root_for_tool(project_root, tool="task_worker_disconnected")
    reason = _text(reason, tool="task_worker_disconnected", field="reason")
    with mcp_audit(root, "task_worker_disconnected", arg_keys=["reason", "project_root"]) as audit:
        with session_scope() as scope:
            project = _project(scope, root)
            result = db_worker_disconnected(scope, project, reason=reason)
            audit["metrics"] = {"state": result.get("status"), "task": result.get("key")}
            return _scoped(result, root)


task_worker_heartbeat = core_tool()(task_worker_heartbeat)
task_worker_disconnected = core_tool()(task_worker_disconnected)
