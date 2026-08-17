from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Protocol


class CodexStatusPolicy(Protocol):
    @property
    def toml_start(self) -> str: ...

    @property
    def toml_end(self) -> str: ...


def active_codex_home(home: Path) -> Path:
    configured = str(os.environ.get("CODEX_HOME") or "").strip()
    return Path(configured).expanduser().resolve() if configured else home / ".codex"


def nonempty_file(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError):
        return False


def codex_mcp_status(path: Path, policy: CodexStatusPolicy) -> dict:
    if not path.exists():
        return {"present": False, "ready": False, "reason": "missing"}
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {"present": True, "ready": False, "reason": "invalid_or_unreadable"}
    servers = data.get("mcp_servers")
    server = servers.get("ai-layer") if isinstance(servers, dict) else None
    if not isinstance(server, dict):
        return {"present": False, "ready": False, "reason": "missing"}
    managed = policy.toml_start in text and policy.toml_end in text
    if not managed:
        return {"present": True, "ready": False, "reason": "ownership_conflict"}
    if not server.get("command"):
        return {"present": True, "ready": False, "reason": "missing_command"}
    if server.get("enabled") is False:
        return {"present": True, "ready": False, "reason": "mcp_disabled"}
    return {"present": True, "ready": True, "reason": None}
