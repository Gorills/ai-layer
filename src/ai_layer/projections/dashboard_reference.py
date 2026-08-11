from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from ai_layer.core.config import get_settings
from ai_layer.core.service import get_project
from ai_layer.db.models import Knowledge
from ai_layer.db.session import session_scope
from ai_layer.memory.knowledge_contract import KNOWLEDGE_KIND, public_card
from ai_layer.memory.knowledge_store import knowledge_status
from ai_layer.policy.service import DEFAULT_POLICY
from ai_layer.projections.dashboard_common import (
    entries,
    entry_for_key,
    page_info,
    project_key,
    project_options,
)
from ai_layer.skills.common import builtin_skill_dir
from ai_layer.skills.registry import (
    disabled_global_skill_slugs,
    find_skill_record,
    project_skill_dir,
)
from ai_layer.skills.service import parse_skill, skill_core_content, skill_sections

_KNOWLEDGE_STATUSES = {"VERIFIED", "DRAFT", "STALE", "SUPERSEDED"}
_PROJECT_RULES_PLACEHOLDER = (
    "# Project-specific rules\n\n"
    "Add only rules that are specific to this repository. "
    "Global engineering policy is loaded separately."
)


def _parse_visible_skill(path: Path) -> dict | None:
    if path.is_symlink():
        return None
    try:
        return parse_skill(path)
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _read_skill_catalog(project_root: Path | None = None) -> list[dict]:
    settings = get_settings()
    disabled = disabled_global_skill_slugs()
    result: dict[str, dict] = {}

    bundled_dir = builtin_skill_dir()
    if bundled_dir.exists():
        for path in sorted(bundled_dir.glob("*.md")):
            if path.stem in disabled:
                continue
            skill = _parse_visible_skill(path)
            if skill is not None:
                result[path.stem] = {**skill, "scope": "global", "record": {}}

    if settings.skills_dir.exists():
        for path in sorted(settings.skills_dir.glob("*.md")):
            if path.stem in disabled:
                continue
            skill = _parse_visible_skill(path)
            if skill is None:
                continue
            record = find_skill_record(path.stem, scope="global")
            result[path.stem] = {
                **skill,
                "scope": "global",
                "record": record or {},
            }

    if project_root is not None:
        directory = project_skill_dir(project_root)
        if directory.exists():
            for path in sorted(directory.glob("*.md")):
                record = find_skill_record(
                    path.stem,
                    scope="project",
                    project_root=project_root,
                )
                if not record or record.get("status", "enabled") != "enabled":
                    continue
                skill = _parse_visible_skill(path)
                if skill is None:
                    continue
                result[path.stem] = {
                    **skill,
                    "scope": "project",
                    "record": record,
                }
    return [result[slug] for slug in sorted(result)]


def _skill_summary(skill: dict) -> dict:
    meta = skill.get("meta") or {}
    sections = list(skill_sections(skill))
    return {
        "slug": skill.get("slug"),
        "scope": skill.get("scope") or "global",
        "description": str(meta.get("description") or ""),
        "keywords": list(meta.get("keywords") or []),
        "sections": sections,
        "section_count": len(sections),
        "core_preview": skill_core_content(skill, max_chars=900),
        "risk": (skill.get("record") or {}).get("risk"),
        "source_type": (skill.get("record") or {}).get("source_type"),
    }


def skills_payload(
    *,
    project_key_value: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    root = None
    if project_key_value:
        entry = entry_for_key(project_key_value)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
    skills = _read_skill_catalog(root)
    pagination = page_info(len(skills), page, page_size)
    start = (pagination["page"] - 1) * pagination["page_size"]
    end = start + pagination["page_size"]
    return {
        "items": [_skill_summary(skill) for skill in skills[start:end]],
        "pagination": pagination,
        "projects": project_options(),
        "project_key": project_key_value,
    }


def skill_detail_payload(project_key_value: str | None, slug: str) -> dict | None:
    root = None
    if project_key_value:
        entry = entry_for_key(project_key_value)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
    skill = next(
        (item for item in _read_skill_catalog(root) if item.get("slug") == slug),
        None,
    )
    if skill is None:
        return None
    return {
        **_skill_summary(skill),
        "core": skill_core_content(skill),
        "content": str(skill.get("content") or ""),
        "path": str(skill.get("path") or ""),
    }


def _read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return (
            path.read_text(encoding="utf-8")
            if path.is_file() and not path.is_symlink()
            else ""
        )
    except (OSError, UnicodeDecodeError):
        return ""


def _project_rules_path(entry: dict) -> Path | None:
    root = Path(str(entry.get("root") or "")).expanduser().resolve()
    mode = str(entry.get("mode") or "standard")
    if mode not in {"external", "strict-private"}:
        meta = root / ".ai-layer"
        target = meta / "rules.md"
        if meta.is_symlink() or target.is_symlink():
            return None
        return target

    project_id = str(entry.get("project_id") or "").strip()
    project_id_path = Path(project_id)
    if (
        not project_id
        or project_id in {".", ".."}
        or len(project_id_path.parts) != 1
        or project_id_path.name != project_id
    ):
        return None
    base = get_settings().home / "projects"
    project_dir = base / project_id
    target = project_dir / "rules.md"
    if base.is_symlink() or project_dir.is_symlink() or target.is_symlink():
        return None
    return target


def _project_rules_text(entry: dict) -> str:
    text = _read_text(_project_rules_path(entry)).strip()
    return "" if text == _PROJECT_RULES_PLACEHOLDER else text


def _rule_count(text: str) -> int:
    count = 0
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            count += 1
            continue
        prefix = stripped.split(".", 1)[0]
        if prefix.isdigit() and stripped[len(prefix) :].startswith(". "):
            count += 1
    return count


def rules_payload(project_key_value: str | None = None) -> dict | None:
    settings = get_settings()
    global_path = settings.policies_dir / "global.md"
    global_text = _read_text(global_path) or DEFAULT_POLICY
    selected = None
    if project_key_value:
        entry = entry_for_key(project_key_value)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
        project_text = _project_rules_text(entry)
        provenance = str(entry.get("provenance") or "allow")
        selected = {
            "key": project_key_value,
            "name": entry.get("name") or root.name,
            "root": str(root),
            "content": project_text,
            "rule_count": _rule_count(project_text),
            "has_custom_rules": bool(project_text),
            "privacy": provenance,
            "strict_private": provenance == "forbid",
        }
    summaries = []
    for entry in entries():
        root = Path(str(entry["root"])).expanduser().resolve()
        text = _project_rules_text(entry)
        provenance = str(entry.get("provenance") or "allow")
        summaries.append(
            {
                "key": project_key(entry),
                "name": entry.get("name") or root.name,
                "rule_count": _rule_count(text),
                "has_custom_rules": bool(text),
                "strict_private": provenance == "forbid",
            }
        )
    return {
        "global": {
            "content": global_text,
            "rule_count": _rule_count(global_text),
            "customized": global_path.is_file() and global_text != DEFAULT_POLICY,
        },
        "project": selected,
        "projects": summaries,
    }


def knowledge_payload(
    project_key_value: str,
    *,
    status: str | None = "VERIFIED",
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    entry = entry_for_key(project_key_value)
    if entry is None:
        return None
    wanted = str(status or "").strip().upper()
    if wanted == "ALL":
        wanted = ""
    if wanted and wanted not in _KNOWLEDGE_STATUSES:
        wanted = "VERIFIED"
    with session_scope() as db:
        project = get_project(db, Path(str(entry["root"])))
        if project is None:
            return None
        rows = list(
            db.scalars(
                select(Knowledge)
                .where(
                    Knowledge.project_id == project.id,
                    Knowledge.kind == KNOWLEDGE_KIND,
                )
                .order_by(Knowledge.updated_at.desc(), Knowledge.id)
            ).all()
        )
        if wanted:
            rows = [
                row
                for row in rows
                if str((row.meta or {}).get("status") or "DRAFT").upper() == wanted
            ]
        pagination = page_info(len(rows), page, page_size)
        start = (pagination["page"] - 1) * pagination["page_size"]
        end = start + pagination["page_size"]
        items = []
        for row in rows[start:end]:
            item = public_card(row)
            item["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
            items.append(item)
        return {
            "project": {
                "key": project_key_value,
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            },
            "summary": knowledge_status(db, project),
            "items": items,
            "pagination": pagination,
            "status": wanted or "ALL",
            "projects": project_options(),
        }


def knowledge_detail_payload(project_key_value: str, knowledge_id: str) -> dict | None:
    entry = entry_for_key(project_key_value)
    if entry is None:
        return None
    try:
        item_id = UUID(str(knowledge_id))
    except ValueError:
        return None
    with session_scope() as db:
        project = get_project(db, Path(str(entry["root"])))
        if project is None:
            return None
        row = db.scalar(
            select(Knowledge)
            .where(
                Knowledge.id == item_id,
                Knowledge.project_id == project.id,
                Knowledge.kind == KNOWLEDGE_KIND,
            )
            .limit(1)
        )
        if row is None:
            return None
        payload = public_card(row, include_content=True)
        payload["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
        return {
            "project": {
                "key": project_key_value,
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            },
            "card": payload,
        }
