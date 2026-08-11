from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

MANAGED_START = "<!-- BEGIN AI-LAYER MANAGED -->"
MANAGED_END = "<!-- END AI-LAYER MANAGED -->"
TOML_START = "# BEGIN AI-LAYER MANAGED MCP"
TOML_END = "# END AI-LAYER MANAGED MCP"
OWNED_FILE_MARKER = "<!-- AI-LAYER OWNED FILE -->"
MCP_OWNER_KEY = "AI_LAYER_MANAGED_BY"
MCP_OWNER_VALUE = "local-ai-development-layer"


def _managed_block(body: str) -> str:
    return f"{MANAGED_START}\n{body.rstrip()}\n{MANAGED_END}"


def _write_private_backup(path: Path, content: str) -> None:
    """Persist provider-config backups as owner-only because they can contain MCP credentials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        os.chmod(path, 0o600)
        return
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _atomic_write_text(path: Path, content: str, *, backup: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    backup_path = path.with_name(path.name + ".ai-layer.bak") if backup else None
    # v0.1.6 also repairs permissions of backups left by older releases even when the provider
    # config itself is already up to date and therefore does not need rewriting.
    if backup_path is not None and backup_path.exists():
        os.chmod(backup_path, 0o600)
    if old == content:
        return
    if backup_path is not None and old is not None and not backup_path.exists():
        # Preserve the first pre-AI-Layer backup as recovery evidence; later upgrades must not
        # silently replace it with an already-managed intermediate configuration.
        _write_private_backup(backup_path, old)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _upsert_managed_markdown(path: Path, body: str) -> None:
    block = _managed_block(body)
    if not path.exists():
        _atomic_write_text(path, block + "\n")
        return
    current = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.DOTALL)
    if pattern.search(current):
        updated = pattern.sub(block, current)
    else:
        sep = "\n" if current.endswith("\n") else "\n\n"
        updated = current + sep + block + "\n"
    _atomic_write_text(path, updated)



def _managed_server(server: dict) -> dict:
    managed = json.loads(json.dumps(server))
    env = managed.setdefault("env", {})
    if not isinstance(env, dict):
        raise RuntimeError("AI Layer MCP server env must be an object.")
    env[MCP_OWNER_KEY] = MCP_OWNER_VALUE
    return managed


def _server_is_owned(server: dict | None) -> bool:
    if not isinstance(server, dict):
        return False
    env = server.get("env")
    return isinstance(env, dict) and env.get(MCP_OWNER_KEY) == MCP_OWNER_VALUE


def _server_matches_legacy(existing: dict, desired: dict) -> bool:
    """Adopt only an exact pre-marker AI Layer entry; never infer ownership from the key alone."""
    if not isinstance(existing, dict):
        return False
    wanted = _managed_server(desired)
    existing_copy = json.loads(json.dumps(existing))
    wanted_env = dict(wanted.get("env") or {})
    wanted_env.pop(MCP_OWNER_KEY, None)
    existing_env = dict(existing_copy.get("env") or {}) if isinstance(existing_copy.get("env"), dict) else {}
    existing_copy["env"] = existing_env
    wanted["env"] = wanted_env
    return existing_copy == wanted


def _assert_json_mcp_merge_safe(path: Path, server: dict) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Cannot merge invalid JSON MCP config: {path}: {exc}") from exc
    existing = (data.get("mcpServers") or {}).get("ai-layer") if isinstance(data, dict) else None
    if existing is None:
        return
    if _server_is_owned(existing) or _server_matches_legacy(existing, server):
        return
    raise RuntimeError(
        f"Integration ownership conflict: {path} already contains user/unmanaged mcpServers.ai-layer. "
        "AI Layer will not overwrite it. Rename/remove that entry explicitly, then retry."
    )


def _legacy_owned_file(path: Path, content: str) -> bool:
    if path.name == "ai-layer.mdc":
        return "Mandatory Local AI Development Layer workflow" in content
    if path.name in {"SKILL.md", "ai-layer.md"}:
        return "# AI Layer bridge" in content and "memory_context" in content
    return False


def _assert_owned_file_safe(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink():
        raise RuntimeError(f"Integration ownership conflict: refusing symlinked managed file: {path}")
    content = path.read_text(encoding="utf-8")
    if OWNED_FILE_MARKER in content or _legacy_owned_file(path, content):
        return
    raise RuntimeError(
        f"Integration ownership conflict: {path} already exists and is not AI Layer-owned. "
        "The file was left untouched."
    )


def _write_owned_text(path: Path, content: str) -> None:
    _assert_owned_file_safe(path)
    if OWNED_FILE_MARKER not in content:
        content = OWNED_FILE_MARKER + "\n" + content
    _atomic_write_text(path, content)


def _assert_codex_merge_safe(path: Path) -> None:
    if not path.exists():
        return
    current = path.read_text(encoding="utf-8")
    if TOML_START in current and TOML_END in current:
        return
    if re.search(r"(?m)^\s*\[mcp_servers\.ai-layer(?:\.env)?\]\s*$", current):
        raise RuntimeError(
            f"Integration ownership conflict: {path} already has an unmanaged [mcp_servers.ai-layer] table. "
            "AI Layer will not append a duplicate TOML table."
        )


def _merge_mcp_json(path: Path, server: dict, *, backup: bool = False) -> None:
    _assert_json_mcp_merge_safe(path, server)
    current: dict = {}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    current.setdefault("mcpServers", {})["ai-layer"] = _managed_server(server)
    _atomic_write_text(
        path,
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        backup=backup,
    )


def _toml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _merge_codex_config(
    path: Path,
    project_root: Path | None = None,
    *,
    command: str | None = None,
    client: str = "codex",
    backup: bool = False,
) -> None:
    if not command:
        raise ValueError("command is required for managed Codex MCP configuration")
    _assert_codex_merge_safe(path)
    lines = [
        TOML_START,
        "[mcp_servers.ai-layer]",
        f"command = {_toml_quote(command)}",
        "args = []",
        "required = true",
        "startup_timeout_sec = 20",
    ]
    env_lines = [f"AI_LAYER_CLIENT = {_toml_quote(client)}"]
    if project_root is not None:
        env_lines.append(f"AI_LAYER_PROJECT_ROOT = {_toml_quote(str(project_root.resolve()))}")
    lines.extend(["", "[mcp_servers.ai-layer.env]", *env_lines])
    lines.append(TOML_END)
    block = "\n".join(lines)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(re.escape(TOML_START) + r".*?" + re.escape(TOML_END), re.DOTALL)
    if pattern.search(current):
        updated = pattern.sub(block, current)
    else:
        sep = "\n" if not current or current.endswith("\n") else "\n\n"
        updated = current + sep + block + "\n"
    _atomic_write_text(path, updated, backup=backup)

def _remove_managed_markdown(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    current = path.read_text(encoding="utf-8")
    pattern = re.compile(r"\n?" + re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END) + r"\n?", re.DOTALL)
    updated = pattern.sub("\n", current).strip("\n")
    if updated.strip():
        _atomic_write_text(path, updated + "\n")
    else:
        path.unlink(missing_ok=True)


def _remove_json_mcp(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        existing = servers.get("ai-layer")
        if _server_is_owned(existing):
            servers.pop("ai-layer", None)
        if not servers:
            data.pop("mcpServers", None)
    if data:
        _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    else:
        path.unlink(missing_ok=True)


def _remove_codex_mcp(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    current = path.read_text(encoding="utf-8")
    pattern = re.compile(r"\n?" + re.escape(TOML_START) + r".*?" + re.escape(TOML_END) + r"\n?", re.DOTALL)
    updated = pattern.sub("\n", current).strip("\n")
    if updated.strip():
        _atomic_write_text(path, updated + "\n")
    else:
        path.unlink(missing_ok=True)

