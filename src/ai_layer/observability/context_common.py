from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import get_registered_project
from ai_layer.core.redaction import redact_secrets

TRACE_TAIL_BYTES = 12 * 1024 * 1024


def estimate_tokens(value) -> int:
    """Tokenizer-independent estimate; UTF-8 bytes/4 is intentionally approximate."""
    if isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    return int(math.ceil(len(raw) / 4.0)) if raw else 0


def profile_value(value) -> dict:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
    raw = text.encode("utf-8")
    return {
        "chars": len(text),
        "utf8_bytes": len(raw),
        "estimated_tokens": estimate_tokens(text),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def redact_value(value):
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact_secrets(str(value))


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_identity(project_root: str | Path) -> tuple[str, dict] | None:
    root = str(Path(project_root).expanduser().resolve())
    try:
        item = get_registered_project(root)
    except RuntimeError:
        return None
    if not item:
        return None
    project_id = str(item.get("project_id") or "").strip()
    if not project_id:
        project_id = "legacy-" + hashlib.sha256(root.encode("utf-8")).hexdigest()[:20]
    return project_id, item


def trace_dir(project_root: str | Path) -> Path:
    identity = project_identity(project_root)
    if identity is None:
        raise RuntimeError(
            f"Project is not registered: {Path(project_root).expanduser().resolve()}"
        )
    project_id, _ = identity
    base = get_settings().projects_state_dir
    if base.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
    return base / project_id / "diagnostics" / "context-monitor"


def trace_path(project_root: str | Path) -> Path:
    return trace_dir(project_root) / "trace.jsonl"


def report_path(project_root: str | Path) -> Path:
    return trace_dir(project_root) / "context-report-latest.json"


def tail_events(path: Path, limit: int = 500) -> list[dict]:
    if not path.exists() or path.is_symlink():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TRACE_TAIL_BYTES:
                handle.seek(-TRACE_TAIL_BYTES, 2)
                handle.readline()
            raw = handle.read()
    except OSError:
        return []
    events = []
    for line in raw.decode("utf-8", errors="replace").splitlines()[-max(1, limit) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events
