from __future__ import annotations

import json
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import get_registered_project
from ai_layer.skills.common import _atomic_json
from ai_layer.skills.constants import REGISTRY_VERSION, SLUG_RE, VALID_SCOPES


def _registry_lock() -> Path:
    return get_settings().home / ".skill-registry.lock"


def _default_registry() -> dict:
    return {"version": REGISTRY_VERSION, "skills": []}


def load_skill_registry() -> dict:
    path = get_settings().skill_registry_file
    if not path.exists():
        return _default_registry()
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked skill registry: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Skill registry is corrupt: {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise RuntimeError(f"Skill registry has invalid shape: {path}")
    data.setdefault("version", REGISTRY_VERSION)
    return data


def _write_registry(data: dict) -> None:
    data["version"] = REGISTRY_VERSION
    get_settings().home.mkdir(parents=True, exist_ok=True)
    _atomic_json(get_settings().skill_registry_file, data)


def _project_identity(project_root: str | Path) -> tuple[str, str]:
    root = str(Path(project_root).expanduser().resolve())
    item = get_registered_project(root)
    if not item or not str(item.get("project_id") or "").strip():
        raise RuntimeError(
            f"Project is not registered with durable identity: {root}. Run `ai-layer init` first."
        )
    return root, str(item["project_id"])


def project_skill_dir(project_root: str | Path) -> Path:
    _, project_id = _project_identity(project_root)
    base = get_settings().project_skills_dir
    if base.is_symlink():
        raise RuntimeError(f"Refusing symlinked project skill root: {base}")
    path = base / project_id
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked project skill directory: {path}")
    return path


def _skill_target(
    *, scope: str, slug: str, project_root: str | Path | None
) -> tuple[Path, str | None, str | None]:
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported skill scope: {scope!r}. Expected global or project.")
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid skill slug: {slug!r}")
    if scope == "global":
        target = get_settings().skills_dir / f"{slug}.md"
        return target, None, None
    if project_root is None:
        raise ValueError("project_root is required for project-scoped skills")
    root, project_id = _project_identity(project_root)
    return project_skill_dir(root) / f"{slug}.md", root, project_id


def _record_key(record: dict) -> tuple[str, str | None, str]:
    return (
        str(record.get("scope")),
        str(record.get("project_id")) if record.get("project_id") else None,
        str(record.get("slug")),
    )


def skill_records(
    *, project_root: str | Path | None = None, include_disabled: bool = True
) -> list[dict]:
    wanted_project_id: str | None = None
    if project_root is not None:
        _, wanted_project_id = _project_identity(project_root)
    records = []
    for raw in load_skill_registry().get("skills", []):
        if not isinstance(raw, dict):
            continue
        scope = str(raw.get("scope") or "")
        if (
            scope == "project"
            and wanted_project_id is not None
            and str(raw.get("project_id")) != wanted_project_id
        ):
            continue
        if scope == "project" and wanted_project_id is None:
            continue
        if not include_disabled and raw.get("status", "enabled") != "enabled":
            continue
        records.append(dict(raw))
    return sorted(records, key=lambda item: (str(item.get("scope")), str(item.get("slug"))))


def find_skill_record(
    slug: str, *, scope: str | None = None, project_root: str | Path | None = None
) -> dict | None:
    for record in skill_records(project_root=project_root, include_disabled=True):
        if record.get("slug") == slug and (scope is None or record.get("scope") == scope):
            return record
    return None


def project_skill_slugs(project_root: str | Path, *, enabled_only: bool = True) -> list[str]:
    # Project skills are optional machine-side enrichment. A stale/missing registry must not make
    # ordinary memory_context fail for an otherwise valid DB Project; it simply means there are no
    # safely bound project skills until project registration is repaired.
    try:
        records = skill_records(project_root=project_root, include_disabled=not enabled_only)
    except RuntimeError:
        return []
    return sorted(
        str(record["slug"])
        for record in records
        if record.get("scope") == "project"
        and (not enabled_only or record.get("status", "enabled") == "enabled")
    )


def disabled_global_skill_slugs() -> set[str]:
    return {
        str(record["slug"])
        for record in load_skill_registry().get("skills", [])
        if isinstance(record, dict)
        and record.get("scope") == "global"
        and record.get("status") == "disabled"
    }
