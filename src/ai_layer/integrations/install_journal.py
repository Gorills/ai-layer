from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ai_layer import __version__
from ai_layer.core.config import get_settings
from ai_layer.integrations.config_files import _atomic_write_text

JOURNAL_SCHEMA = 1
INSTALL_OPERATION = "global-install"
REMOVE_OPERATION = "global-remove"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

INSTALL_PHASES = (
    "preflight",
    "mcp_cursor",
    "mcp_antigravity",
    "mcp_codex",
    "mcp_claude",
    "bootstrap",
    "cursor_profiles",
    "native_skills",
)
REMOVE_PHASES = (
    "mcp_cursor",
    "mcp_antigravity",
    "mcp_codex",
    "bootstrap",
    "cursor_plugin",
    "cursor_profiles",
    "native_skills",
    "mcp_claude",
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def journal_file():
    home = get_settings().home
    if home.exists() and (home.is_symlink() or not home.is_dir()):
        raise RuntimeError(f"Refusing AI Layer install journal path: {home}")
    home.mkdir(parents=True, exist_ok=True)
    path = home / "install-journal.json"
    if path.is_symlink() or path.parent.is_symlink():
        raise RuntimeError(f"Refusing AI Layer path redirected by symlink: {path}")
    return path


def read_journal() -> dict[str, Any]:
    path = get_settings().home / "install-journal.json"
    if not path.exists() or path.is_symlink() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_journal(payload: dict[str, Any]) -> dict[str, Any]:
    _atomic_write_text(journal_file(), json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def begin_journal(operation: str, *, phases: tuple[str, ...]) -> dict[str, Any]:
    existing = read_journal()
    resumable = (
        existing.get("schema") == JOURNAL_SCHEMA
        and existing.get("operation") == operation
        and existing.get("version") == __version__
        and existing.get("status") in {STATUS_IN_PROGRESS, STATUS_FAILED}
    )
    completed = (
        [str(item) for item in existing.get("completed_phases") or [] if str(item) in phases]
        if resumable
        else []
    )
    return _write_journal(
        {
            "schema": JOURNAL_SCHEMA,
            "operation": operation,
            "status": STATUS_IN_PROGRESS,
            "version": __version__,
            "started_at": str(existing.get("started_at") or _utcnow()) if resumable else _utcnow(),
            "updated_at": _utcnow(),
            "phases": list(phases),
            "completed_phases": completed,
            "optional_degraded": (
                dict(existing.get("optional_degraded") or {}) if resumable else {}
            ),
        }
    )


def record_phase(phase: str, *, degraded: str | None = None) -> dict[str, Any]:
    payload = read_journal()
    completed = [str(item) for item in payload.get("completed_phases") or []]
    if phase not in completed:
        completed.append(phase)
    payload["completed_phases"] = completed
    payload["updated_at"] = _utcnow()
    payload["status"] = STATUS_IN_PROGRESS
    if degraded:
        notes = dict(payload.get("optional_degraded") or {})
        notes[phase] = degraded
        payload["optional_degraded"] = notes
    return _write_journal(payload)


def complete_journal() -> dict[str, Any]:
    payload = read_journal()
    payload["status"] = STATUS_COMPLETE
    payload["updated_at"] = _utcnow()
    payload["completed_at"] = _utcnow()
    return _write_journal(payload)


def fail_journal(error: str) -> dict[str, Any]:
    payload = read_journal()
    if not payload:
        return payload
    payload["status"] = STATUS_FAILED
    payload["updated_at"] = _utcnow()
    payload["error"] = error[:1000]
    return _write_journal(payload)


def journal_is_complete(payload: dict[str, Any] | None = None, *, operation: str) -> bool:
    data = read_journal() if payload is None else payload
    expected = [str(item) for item in data.get("phases") or []]
    completed = {str(item) for item in data.get("completed_phases") or []}
    return (
        data.get("schema") == JOURNAL_SCHEMA
        and data.get("operation") == operation
        and data.get("status") == STATUS_COMPLETE
        and data.get("version") == __version__
        and bool(expected)
        and set(expected) <= completed
    )
