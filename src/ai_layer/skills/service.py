from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import yaml

from ai_layer.core.config import get_settings
from ai_layer.skills.common import builtin_skill_dir
from ai_layer.skills.registry import (
    disabled_global_skill_slugs,
    find_skill_record,
    project_skill_dir,
)

SKILL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _skill_path(slug: str) -> Path:
    if not isinstance(slug, str) or not SKILL_SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid skill slug: {slug!r}")
    skills_dir = get_settings().skills_dir.expanduser().resolve()
    candidate = skills_dir / f"{slug}.md"
    if candidate.is_symlink():
        raise RuntimeError(f"Refusing symlinked skill file: {candidate}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(skills_dir)
    except ValueError as exc:
        raise RuntimeError(f"Skill path escapes configured skills directory: {candidate}") from exc
    return candidate


def _sha_text(text: str) -> str:
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


def _load_builtin_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "skills": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {"version": 1, "skills": {}}
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        return {"version": 1, "skills": {}}
    return data


def _write_builtin_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    _atomic_write_text(path, content)


def install_builtin_skills(force: bool = False) -> list[str]:
    """Update bundled skills without clobbering user-modified/custom skills.

    A file is auto-updated only when it is missing, force=True, or its current checksum matches the
    last managed checksum. Custom skill names are never touched.
    """
    settings = get_settings()
    settings.skills_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = settings.skills_dir / ".builtin-manifest.json"
    manifest = _load_builtin_manifest(manifest_path)
    installed: list[str] = []
    next_skills: dict[str, dict] = {}
    for item in builtin_skill_dir().iterdir():
        if not item.name.endswith(".md"):
            continue
        target = settings.skills_dir / item.name
        bundled = item.read_text(encoding="utf-8")
        bundled_hash = _sha_text(bundled)
        previous = manifest.get("skills", {}).get(item.name, {})
        managed_hash = previous.get("managed_hash") if isinstance(previous, dict) else None
        current = target.read_text(encoding="utf-8") if target.exists() else None
        current_hash = _sha_text(current) if current is not None else None
        should_write = (
            force or current is None or current_hash == managed_hash or current_hash == bundled_hash
        )
        if should_write:
            if current != bundled:
                _atomic_write_text(target, bundled)
            managed_hash = bundled_hash
        next_skills[item.name] = {"bundled_hash": bundled_hash, "managed_hash": managed_hash}
        installed.append(item.name.removesuffix(".md"))
    manifest["version"] = 1
    manifest["skills"] = next_skills
    _write_builtin_manifest(manifest_path, manifest)
    return sorted(installed)


def _parse_skill_text(*, slug: str, text: str, path: str) -> dict:
    meta: dict = {}
    content = text
    if text.startswith("---\n"):
        parts = text.split("---\n", 2)
        if len(parts) == 3:
            _, header, content = parts
            loaded = yaml.safe_load(header) or {}
            meta = loaded if isinstance(loaded, dict) else {}
    return {"slug": slug, "meta": meta, "content": content.strip(), "path": path}


SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")


def skill_sections(skill: dict) -> dict[str, str]:
    """Return level-2 skill sections without forcing the whole skill into model context."""
    content = str(skill.get("content") or "").strip()
    matches = list(SECTION_RE.finditer(content))
    if not matches:
        return {"full": content} if content else {}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections[match.group(1).strip()] = content[start:end].strip()
    return sections


def _match_section_name(sections: dict[str, str], wanted: str) -> str | None:
    wanted_cf = wanted.strip().casefold()
    for name in sections:
        if name.casefold() == wanted_cf:
            return name
    return None


def skill_core_content(skill: dict, *, max_chars: int = 2400) -> str:
    sections = skill_sections(skill)
    requested = list((skill.get("meta") or {}).get("entry_sections") or [])
    if not requested:
        requested = [
            name
            for name in ("Apply when", "Mandatory rules", "Core contract", "Decision rules")
            if name in sections
        ]
    if not requested:
        requested = list(sections)[:2]
    chunks: list[str] = []
    for wanted in requested:
        matched = _match_section_name(sections, str(wanted))
        if matched:
            chunks.append(sections[matched])
    content = "\n\n".join(chunks).strip() or str(skill.get("content") or "").strip()
    if max_chars <= 0:
        return ""
    if len(content) <= max_chars:
        return content
    suffix = "\n...[skill core clipped; use skill_get section]"
    if len(suffix) >= max_chars:
        return content[:max_chars]
    return content[: max_chars - len(suffix)].rstrip() + suffix


def skill_section_content(skill: dict, section: str | None = None) -> tuple[str, list[str]]:
    sections = skill_sections(skill)
    names = list(sections)
    if not section or section.casefold() == "full":
        return str(skill.get("content") or ""), names
    if section.casefold() == "core":
        return skill_core_content(skill), names
    matched = _match_section_name(sections, section)
    if matched is None:
        raise ValueError(
            f"Unknown section `{section}` for skill `{skill.get('slug')}`. Available: {names}"
        )
    return sections[matched], names


def parse_skill(path: Path) -> dict:
    return _parse_skill_text(slug=path.stem, text=path.read_text("utf-8"), path=str(path))


def _with_scope(skill: dict, scope: str, record: dict | None = None) -> dict:
    item = dict(skill)
    item["scope"] = scope
    if record:
        package_root = record.get("package_root")
        if package_root:
            item["package"] = {
                "root": str(package_root),
                "files": int(record.get("package_files") or 0),
                "bytes": int(record.get("package_bytes") or 0),
                "sha256": record.get("package_sha256"),
                "contract": (
                    "Resolve skill-relative references/data/scripts against this package root. "
                    "Package assets stay outside the repository and are not autoloaded into model context."
                ),
            }
    return item


def list_skills(project_root: str | Path | None = None) -> list[dict]:
    """List enabled global skills plus project-scoped skills for one durable project identity."""
    install_builtin_skills()
    disabled = disabled_global_skill_slugs()
    result: dict[str, dict] = {}
    for path in sorted(get_settings().skills_dir.glob("*.md")):
        if path.stem in disabled:
            continue
        record = find_skill_record(path.stem, scope="global")
        result[path.stem] = _with_scope(parse_skill(path), "global", record)
    if project_root is not None:
        directory = project_skill_dir(project_root)
        if directory.exists():
            for path in sorted(directory.glob("*.md")):
                record = find_skill_record(path.stem, scope="project", project_root=project_root)
                if not record or record.get("status", "enabled") != "enabled":
                    continue
                if path.stem in result:
                    # Manager rejects collisions on install; fail closed if machine state was edited manually.
                    raise RuntimeError(
                        f"Project skill collides with global skill slug: {path.stem}"
                    )
                result[path.stem] = _with_scope(parse_skill(path), "project", record)
    return [result[slug] for slug in sorted(result)]


def load_skill(slug: str, project_root: str | Path | None = None) -> dict | None:
    install_builtin_skills()
    if project_root is not None:
        record = find_skill_record(slug, scope="project", project_root=project_root)
        if record and record.get("status", "enabled") == "enabled":
            path = project_skill_dir(project_root) / f"{slug}.md"
            if path.is_symlink():
                raise RuntimeError(f"Refusing symlinked project skill file: {path}")
            if path.exists():
                return _with_scope(parse_skill(path), "project", record)
    if slug in disabled_global_skill_slugs():
        return None
    path = _skill_path(slug)
    record = find_skill_record(slug, scope="global")
    return _with_scope(parse_skill(path), "global", record) if path.exists() else None


def load_skills(slugs: list[str], project_root: str | Path | None = None) -> dict[str, dict]:
    """Load several selected skills with one managed-install check."""
    install_builtin_skills()
    result: dict[str, dict] = {}
    for slug in dict.fromkeys(slugs):
        skill = load_skill(slug, project_root=project_root)
        if skill is not None:
            result[slug] = skill
    return result


# Skill relevance is intentionally not implemented here. Cursor, Codex and Antigravity
# own relevance selection through their native Agent Skills mechanisms. AI Layer owns only
# canonical content, validation, synchronization and explicit selective retrieval.
