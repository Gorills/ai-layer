from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.paths import project_provenance, project_state_path
from ai_layer.domain.static_policy import (
    MAX_FINAL_WORDS,
    SIMPLE_FINAL_WORDS,
    static_policy_markdown,
)

# Shared response metadata for interfaces that expose concise-output guidance. Keep the contract
# explicit and stable; do not optimize it around the legacy memory_context transport.
RESPONSE_CONTRACT = {
    "mode": "concise_mandatory",
    "max_words": MAX_FINAL_WORDS,
    "simple_max_words": SIMPLE_FINAL_WORDS,
    "exception": "user_requested_detail_or_material_risk",
}

# DEFAULT_POLICY is rendered from the same always-on engineering rules used by native hosts.
# Dynamic policy surfaces therefore omit the bundled copy and return only user/project additions.
DEFAULT_POLICY = "# Global AI Engineering Policy\n\n" + static_policy_markdown()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def ensure_global_policy(force: bool = False) -> Path:
    settings = get_settings()
    settings.policies_dir.mkdir(parents=True, exist_ok=True)
    path = settings.policies_dir / "global.md"
    manifest_path = settings.policies_dir / ".managed.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            manifest = {}
    current = path.read_text(encoding="utf-8") if path.exists() else None
    current_hash = _sha(current) if current is not None else None
    managed_hash = manifest.get("managed_hash")
    bundled_hash = _sha(DEFAULT_POLICY)
    should_write = (
        force or current is None or current_hash == managed_hash or current_hash == bundled_hash
    )
    if should_write:
        if current != DEFAULT_POLICY:
            _atomic_write_text(path, DEFAULT_POLICY)
        managed_hash = bundled_hash
    manifest_content = (
        json.dumps(
            {"version": 2, "bundled_hash": bundled_hash, "managed_hash": managed_hash}, indent=2
        )
        + "\n"
    )
    if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != manifest_content:
        _atomic_write_text(manifest_path, manifest_content)
    return path


def render_dynamic_policy_parts(parts: list[tuple[str, str]]) -> str:
    return "\n\n".join(text.strip() for _, text in parts if text.strip())


def dynamic_policy_parts(
    project_root: str | Path, *, read_only: bool = False
) -> list[tuple[str, str]]:
    """Ordered dynamic policy fragments: custom global, project, privacy, read-only."""
    global_path = ensure_global_policy()
    parts: list[tuple[str, str]] = []
    try:
        global_text = global_path.read_text("utf-8")
    except OSError:
        global_text = DEFAULT_POLICY
    if _sha(global_text) != _sha(DEFAULT_POLICY):
        parts.append(("global", "# Custom Global Policy\n\n" + global_text.strip()))

    project_path = project_state_path(project_root, "rules.md")
    if project_path.exists():
        try:
            project_text = project_path.read_text("utf-8").strip()
        except OSError:
            project_text = ""
        placeholder = "# Project-specific rules\n\nAdd only rules that are specific to this repository. Global engineering policy is loaded separately."
        if project_text and project_text != placeholder:
            parts.append(("project", "# Project Rules\n\n" + project_text))

    if project_provenance(project_root) == "forbid":
        parts.append(
            (
                "privacy",
                """# Strict Private Repository Policy

- Do not create AI Layer artifacts or AI-development provenance inside the repository.
- Never bypass the privacy guard or rewrite user Git state merely to satisfy AI Layer.""",
            )
        )
    if read_only:
        parts.append(
            (
                "readonly",
                """# Read-only stage

- Do not modify repository files or execute commands that can mutate repository state.
- Inspection and verification must remain read-only.""",
            )
        )
    return parts


def dynamic_policy(project_root: str | Path, *, read_only: bool = False) -> str:
    """Return only policy not already delivered by the always-on native bootstrap.

    Bundled defaults are intentionally omitted from dynamic Project Intelligence/compatibility
    payloads. A user-modified global policy, repository-specific rules, and strict-private
    constraints remain dynamic authoritative inputs.
    """
    return render_dynamic_policy_parts(dynamic_policy_parts(project_root, read_only=read_only))
