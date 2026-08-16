from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_layer.core.redaction import (
    bound_text,
    redact_secret_argv,
    redact_text_with_secrets,
    secret_values_from_argv,
)

DEFAULT_VIEW_EXCERPT_CHARS = 500
_TRUNCATION_MARKER = "\n...[verification output truncated]...\n"


def verification_status(*, exit_code: int | None, timed_out: bool) -> str:
    if timed_out:
        return "timed_out"
    if exit_code == 0:
        return "passed"
    return "failed"


def public_verification_view(record: dict[str, Any]) -> dict[str, Any]:
    """Default API/UI projection: redacted argv plus a short non-secret excerpt."""
    raw_command = [str(part) for part in (record.get("command") or [])]
    command = redact_secret_argv(raw_command)
    timed_out = bool(record.get("timed_out"))
    exit_code = record.get("exit_code")
    status = verification_status(
        exit_code=exit_code if isinstance(exit_code, int) else None,
        timed_out=timed_out,
    )
    name = Path(command[0]).name if command else "verification"
    summary = redact_text_with_secrets(
        str(record.get("output_summary") or ""),
        secret_values_from_argv(raw_command),
    )
    payload = dict(record)
    payload.update(
        {
            "name": name[:240],
            "status": status,
            "command": command,
            "timed_out": timed_out,
            "passed": status == "passed",
            "output_summary": bound_text(
                summary, DEFAULT_VIEW_EXCERPT_CHARS, marker=_TRUNCATION_MARKER
            ),
        }
    )
    return payload


def public_verification_row(row: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": str(row.id),
        "assurance": row.assurance,
        "command": list(row.command or []),
        "started_at": row.started_at.isoformat(),
        "completed_at": row.completed_at.isoformat(),
        "exit_code": row.exit_code,
        "timed_out": bool(row.timed_out),
        "output_summary": row.output_summary or "",
        "evidence_ref": row.evidence_ref,
    }
    if extra:
        payload.update(extra)
    return public_verification_view(payload)
