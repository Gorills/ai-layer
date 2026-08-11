from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_layer import __version__
from ai_layer.core.filelock import directory_lock
from ai_layer.core.mcp_process import current_mcp_session_id
from ai_layer.observability.context_common import (
    estimate_tokens as estimate_tokens,
)
from ai_layer.observability.context_common import (
    profile_value as _profile,
)
from ai_layer.observability.context_common import (
    project_identity,
    trace_path,
    utcnow_iso,
)
from ai_layer.observability.context_common import (
    redact_value as _redact,
)
from ai_layer.observability.context_config import configured_context_snapshot

TRACE_SCHEMA_VERSION = 1
MAX_TRACE_BYTES = 16 * 1024 * 1024
DETAILED_TOOLS = {
    "memory_context",
    "memory_search",
    "decision_search",
    "skill_get",
    "project_info",
    "session_restore",
    "task_current",
    "task_next",
    "task_create",
    "task_adopt",
    "task_stage_delegate",
    "knowledge_list",
    "knowledge_draft_upsert",
}
REPORT_REFRESH_TOOLS = {
    "memory_context",
    "skill_get",
    "task_discovery_complete",
    "task_implementation_complete",
    "task_review_complete",
    "task_fix_complete",
    "task_cancel",
    "session_save",
    "knowledge_draft_upsert",
}


def _memory_context_breakdown(payload: dict) -> dict:
    components = {}
    for key in (
        "policy",
        "response_contract",
        "task_runtime",
        "completion_requirements",
        "tool_guidance",
        "task_brief",
        "knowledge_state",
        "scanner_evidence",
        "project_intelligence",
        "task_evidence",
        "recent_change_evidence",
        "memory",
        "skill_access",
    ):
        if key in payload:
            components[key] = _profile(payload[key])
    return {
        "components": components,
        "automatic_domain_skill_injection": False,
        "automatic_skill_profile": _profile(""),
    }


def _append(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    lock = path.parent / ".trace-write.lock"
    with directory_lock(lock, timeout_seconds=2, stale_after_seconds=60):
        try:
            oversized = path.exists() and path.stat().st_size >= MAX_TRACE_BYTES
        except OSError:
            oversized = False
        if oversized:
            previous = path.with_name("trace.previous.jsonl")
            previous.unlink(missing_ok=True)
            os.replace(path, previous)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)


def _tool_arguments(func, args: tuple, kwargs: dict) -> dict:
    import inspect

    try:
        bound = inspect.signature(func).bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        return dict(kwargs)
    return dict(bound.arguments)


def _safe_project_root(
    arguments: dict,
    result: Any,
    resolved_project_root: str | None = None,
) -> str | None:
    if isinstance(result, dict) and result.get("project_root"):
        return str(result["project_root"])
    if resolved_project_root:
        return str(Path(resolved_project_root).expanduser().resolve())
    value = arguments.get("project_root")
    if isinstance(value, str) and value.strip():
        return str(Path(value).expanduser().resolve())
    env_root = (os.getenv("AI_LAYER_PROJECT_ROOT") or "").strip()
    if env_root:
        return str(Path(env_root).expanduser().resolve())
    return None


def record_tool_delivery(
    func,
    tool: str,
    args: tuple,
    kwargs: dict,
    result: Any,
    *,
    mcp_instructions: str | None = None,
    mcp_tool_catalog: tuple[dict, ...] | None = None,
    resolved_project_root: str | None = None,
) -> None:
    arguments = _tool_arguments(func, args, kwargs)
    root = _safe_project_root(arguments, result, resolved_project_root)
    if not root or project_identity(root) is None:
        return
    redacted_args = _redact(arguments)
    redacted_result = _redact(result)
    event = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "id": uuid4().hex,
        "ts": utcnow_iso(),
        "server_version": __version__,
        "project_root": root,
        "mcp_session_id": current_mcp_session_id(),
        "client": os.getenv("AI_LAYER_CLIENT") or "unknown",
        "reported_host_model": os.getenv("AI_LAYER_MODEL"),
        "kind": "tool_delivery",
        "tool": tool,
        "ok": True,
        "arguments_profile": _profile(redacted_args),
        "result_profile": _profile(redacted_result),
    }
    if tool in DETAILED_TOOLS:
        event["arguments"] = redacted_args
        event["result"] = redacted_result
    else:
        preview = json.dumps(redacted_result, ensure_ascii=False, sort_keys=True, default=str)
        if len(preview) > 4000:
            preview = preview[:4000] + "...[preview truncated]"
        event["result_preview"] = preview
    if tool == "memory_context" and isinstance(redacted_result, dict):
        event["breakdown"] = _memory_context_breakdown(redacted_result)
        event["configured_context"] = configured_context_snapshot(
            root, mcp_instructions, mcp_tool_catalog
        )
    if tool == "skill_get" and isinstance(redacted_result, dict):
        section = str(redacted_result.get("section") or "full")
        event["skill_fetch"] = {
            "slug": redacted_result.get("slug"),
            "section": section,
            "full_skill": section.casefold() == "full",
            "content": _profile(str(redacted_result.get("content") or "")),
            "selection_visibility": "HOST_HIDDEN",
            "selection_source": "host_native_or_manual_not_observable",
        }
    _append(trace_path(root), event)
    if tool in REPORT_REFRESH_TOOLS:
        _refresh_latest_report(root)


def record_tool_failure(
    func,
    tool: str,
    args: tuple,
    kwargs: dict,
    exc: BaseException,
    *,
    resolved_project_root: str | None = None,
) -> None:
    arguments = _tool_arguments(func, args, kwargs)
    root = _safe_project_root(arguments, None, resolved_project_root)
    if not root or project_identity(root) is None:
        return
    redacted_args = _redact(arguments)
    event = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "id": uuid4().hex,
        "ts": utcnow_iso(),
        "server_version": __version__,
        "project_root": root,
        "mcp_session_id": current_mcp_session_id(),
        "client": os.getenv("AI_LAYER_CLIENT") or "unknown",
        "kind": "tool_delivery",
        "tool": tool,
        "ok": False,
        "error_type": type(exc).__name__,
        "arguments_profile": _profile(redacted_args),
    }
    if tool in DETAILED_TOOLS:
        event["arguments"] = redacted_args
    _append(trace_path(root), event)
    if tool in REPORT_REFRESH_TOOLS:
        try:
            _refresh_latest_report(root)
        except Exception:
            pass


def _refresh_latest_report(project_root: str | Path) -> None:
    from ai_layer.observability.context_report import write_latest_report

    write_latest_report(project_root)
