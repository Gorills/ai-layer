from __future__ import annotations

import hashlib
import math
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from ai_layer.core.config import get_settings
from ai_layer.core.paths import project_provenance, project_state_path
from ai_layer.core.registry import list_registered_projects
from ai_layer.core.service import get_project
from ai_layer.db.models import Knowledge, Task, VerificationRun
from ai_layer.db.session import session_scope
from ai_layer.memory.knowledge_contract import KNOWLEDGE_KIND, public_card
from ai_layer.memory.knowledge_store import knowledge_status
from ai_layer.observability.events import aggregate_events
from ai_layer.policy.service import DEFAULT_POLICY
from ai_layer.skills.registry import (
    disabled_global_skill_slugs,
    find_skill_record,
    project_skill_dir,
)
from ai_layer.skills.service import parse_skill, skill_core_content, skill_sections
from ai_layer.tasks.views import task_to_dict

_TASK_STATUSES = {"active", "blocked", "completed", "cancelled"}
_KNOWLEDGE_STATUSES = {"VERIFIED", "DRAFT", "STALE", "SUPERSEDED"}


def _project_key(entry: dict) -> str:
    project_id = str(entry.get("project_id") or "").strip()
    if project_id:
        return project_id
    root = str(entry.get("root") or "")
    return "root-" + hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def _entries() -> list[dict]:
    return [dict(item) for item in list_registered_projects(existing_only=True)]


def entry_for_key(key: str) -> dict | None:
    return next((entry for entry in _entries() if _project_key(entry) == key), None)


def project_options() -> list[dict]:
    return [
        {
            "key": _project_key(entry),
            "name": entry.get("name") or Path(str(entry.get("root") or "")).name,
            "root": str(entry.get("root") or ""),
            "mode": entry.get("mode") or "standard",
            "provenance": entry.get("provenance") or "allow",
        }
        for entry in _entries()
    ]


def _page(total: int, page: int, page_size: int) -> dict:
    size = max(1, min(int(page_size or 10), 50))
    pages = math.ceil(total / size) if total else 0
    current = max(1, int(page or 1))
    if pages:
        current = min(current, pages)
    return {
        "page": current,
        "page_size": size,
        "total": int(total),
        "pages": pages,
        "has_previous": current > 1,
        "has_next": pages > 0 and current < pages,
    }


def _selected_entries(project_key: str | None) -> list[dict]:
    if not project_key:
        return _entries()
    entry = entry_for_key(project_key)
    return [entry] if entry is not None else []


def tasks_payload(
    *,
    project_key: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    entries = _selected_entries(project_key)
    if project_key and not entries:
        return None
    wanted_status = str(status or "").strip().casefold()
    if wanted_status and wanted_status not in _TASK_STATUSES:
        wanted_status = ""

    with session_scope() as db:
        project_map: dict[object, dict] = {}
        project_ids = []
        for entry in entries:
            project = get_project(db, Path(str(entry["root"])))
            if project is None:
                continue
            project_ids.append(project.id)
            project_map[project.id] = {
                "key": _project_key(entry),
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            }
        if not project_ids:
            return {
                "items": [],
                "pagination": _page(0, page, page_size),
                "projects": project_options(),
                "filters": {"project_key": project_key, "status": wanted_status or None},
            }

        conditions = [Task.project_id.in_(project_ids)]
        if wanted_status:
            conditions.append(Task.status == wanted_status)
        total = int(
            db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0
        )
        pagination = _page(total, page, page_size)
        rows = list(
            db.scalars(
                select(Task)
                .where(*conditions)
                .order_by(Task.updated_at.desc(), Task.created_at.desc())
                .offset((pagination["page"] - 1) * pagination["page_size"])
                .limit(pagination["page_size"])
            ).all()
        )
        items = []
        for task in rows:
            payload = task_to_dict(db, task, include_history=False)
            items.append(
                {
                    **payload,
                    "project": project_map.get(task.project_id, {}),
                }
            )
        return {
            "items": items,
            "pagination": pagination,
            "projects": project_options(),
            "filters": {"project_key": project_key, "status": wanted_status or None},
        }


def task_detail_payload(project_key: str, task_key: str) -> dict | None:
    entry = entry_for_key(project_key)
    if entry is None:
        return None
    raw = str(task_key or "").strip().upper()
    if not raw.startswith("T-"):
        return None
    try:
        sequence = int(raw[2:])
    except ValueError:
        return None

    with session_scope() as db:
        project = get_project(db, Path(str(entry["root"])))
        if project is None:
            return None
        task = db.scalar(
            select(Task).where(Task.project_id == project.id, Task.sequence == sequence).limit(1)
        )
        if task is None:
            return None
        verification_rows = list(
            db.scalars(
                select(VerificationRun)
                .where(VerificationRun.task_id == task.id)
                .order_by(VerificationRun.created_at.desc())
                .limit(50)
            ).all()
        )
        verifications = [
            {
                "id": str(row.id),
                "stage_id": str(row.stage_id) if row.stage_id else None,
                "assurance": row.assurance,
                "command": list(row.command or []),
                "started_at": row.started_at.isoformat(),
                "completed_at": row.completed_at.isoformat(),
                "exit_code": row.exit_code,
                "timed_out": bool(row.timed_out),
                "output_summary": row.output_summary,
                "evidence_ref": row.evidence_ref,
            }
            for row in verification_rows
        ]
        return {
            "project": {
                "key": project_key,
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            },
            "task": task_to_dict(db, task, include_history=True),
            "verification": verifications,
        }


def _read_skill_catalog(project_root: Path | None = None) -> list[dict]:
    settings = get_settings()
    disabled = disabled_global_skill_slugs()
    result: dict[str, dict] = {}
    if settings.skills_dir.exists():
        for path in sorted(settings.skills_dir.glob("*.md")):
            if path.is_symlink() or path.stem in disabled:
                continue
            try:
                skill = parse_skill(path)
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            record = find_skill_record(path.stem, scope="global")
            result[path.stem] = {**skill, "scope": "global", "record": record or {}}
    if project_root is not None:
        directory = project_skill_dir(project_root)
        if directory.exists():
            for path in sorted(directory.glob("*.md")):
                if path.is_symlink():
                    continue
                record = find_skill_record(
                    path.stem, scope="project", project_root=project_root
                )
                if not record or record.get("status", "enabled") != "enabled":
                    continue
                try:
                    skill = parse_skill(path)
                except (OSError, UnicodeDecodeError, ValueError):
                    continue
                result[path.stem] = {**skill, "scope": "project", "record": record}
    return [result[slug] for slug in sorted(result)]


def _skill_summary(skill: dict) -> dict:
    meta = skill.get("meta") or {}
    sections = list(skill_sections(skill))
    core = skill_core_content(skill, max_chars=900)
    return {
        "slug": skill.get("slug"),
        "scope": skill.get("scope") or "global",
        "description": str(meta.get("description") or ""),
        "keywords": list(meta.get("keywords") or []),
        "sections": sections,
        "section_count": len(sections),
        "core_preview": core,
        "risk": (skill.get("record") or {}).get("risk"),
        "source_type": (skill.get("record") or {}).get("source_type"),
    }


def skills_payload(
    *,
    project_key: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    root = None
    if project_key:
        entry = entry_for_key(project_key)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
    skills = _read_skill_catalog(root)
    pagination = _page(len(skills), page, page_size)
    start = (pagination["page"] - 1) * pagination["page_size"]
    end = start + pagination["page_size"]
    return {
        "items": [_skill_summary(skill) for skill in skills[start:end]],
        "pagination": pagination,
        "projects": project_options(),
        "project_key": project_key,
    }


def skill_detail_payload(project_key: str | None, slug: str) -> dict | None:
    root = None
    if project_key:
        entry = entry_for_key(project_key)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
    skill = next(
        (item for item in _read_skill_catalog(root) if item.get("slug") == slug),
        None,
    )
    if skill is None:
        return None
    summary = _skill_summary(skill)
    return {
        **summary,
        "core": skill_core_content(skill),
        "content": str(skill.get("content") or ""),
        "path": str(skill.get("path") or ""),
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() and not path.is_symlink() else ""
    except (OSError, UnicodeDecodeError):
        return ""


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


def rules_payload(project_key: str | None = None) -> dict | None:
    settings = get_settings()
    global_path = settings.policies_dir / "global.md"
    global_text = _read_text(global_path) or DEFAULT_POLICY
    selected = None
    if project_key:
        entry = entry_for_key(project_key)
        if entry is None:
            return None
        root = Path(str(entry["root"])).expanduser().resolve()
        project_text = _read_text(project_state_path(root, "rules.md"))
        selected = {
            "key": project_key,
            "name": entry.get("name") or root.name,
            "root": str(root),
            "content": project_text,
            "rule_count": _rule_count(project_text),
            "has_custom_rules": bool(project_text.strip()),
            "privacy": project_provenance(root),
            "strict_private": project_provenance(root) == "forbid",
        }
    summaries = []
    for entry in _entries():
        root = Path(str(entry["root"])).expanduser().resolve()
        text = _read_text(project_state_path(root, "rules.md"))
        summaries.append(
            {
                "key": _project_key(entry),
                "name": entry.get("name") or root.name,
                "rule_count": _rule_count(text),
                "has_custom_rules": bool(text.strip()),
                "strict_private": project_provenance(root) == "forbid",
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
    project_key: str,
    *,
    status: str | None = "VERIFIED",
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    entry = entry_for_key(project_key)
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
                .where(Knowledge.project_id == project.id, Knowledge.kind == KNOWLEDGE_KIND)
                .order_by(Knowledge.updated_at.desc(), Knowledge.id)
            ).all()
        )
        if wanted:
            rows = [
                row
                for row in rows
                if str((row.meta or {}).get("status") or "DRAFT").upper() == wanted
            ]
        pagination = _page(len(rows), page, page_size)
        start = (pagination["page"] - 1) * pagination["page_size"]
        end = start + pagination["page_size"]
        items = []
        for row in rows[start:end]:
            item = public_card(row)
            item["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
            items.append(item)
        return {
            "project": {
                "key": project_key,
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            },
            "summary": knowledge_status(db, project),
            "items": items,
            "pagination": pagination,
            "status": wanted or "ALL",
            "projects": project_options(),
        }


def knowledge_detail_payload(project_key: str, knowledge_id: str) -> dict | None:
    entry = entry_for_key(project_key)
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
                "key": project_key,
                "name": entry.get("name") or project.name,
                "root": str(entry["root"]),
            },
            "card": payload,
        }


def activity_payload(
    *,
    project_key: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict | None:
    entries = _selected_entries(project_key)
    if project_key and not entries:
        return None
    items = []
    for entry in entries:
        root = Path(str(entry["root"])).expanduser().resolve()
        metrics = aggregate_events(root, since_seconds=7 * 24 * 3600, recent_limit=250)
        for event in metrics.get("recent_terminal") or []:
            items.append(
                {
                    "ts": event.get("ts"),
                    "project_key": _project_key(entry),
                    "project_name": entry.get("name") or root.name,
                    "client": event.get("client") or "unknown",
                    "category": event.get("category") or "unknown",
                    "operation": event.get("operation") or "unknown",
                    "status": event.get("status") or "unknown",
                    "duration_ms": event.get("duration_ms"),
                    "error_type": event.get("error_type"),
                    "metrics": event.get("metrics") or {},
                }
            )
    items.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    pagination = _page(len(items), page, page_size)
    start = (pagination["page"] - 1) * pagination["page_size"]
    end = start + pagination["page_size"]
    return {
        "items": items[start:end],
        "pagination": pagination,
        "projects": project_options(),
        "project_key": project_key,
        "retention": "7-day dashboard window; underlying event retention is configured separately",
    }
