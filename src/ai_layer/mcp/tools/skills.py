from __future__ import annotations

from ai_layer.application.transport import application_scope as session_scope
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import _list, _project, _text, core_tool, project_root_for_tool
from ai_layer.skills.manager import (
    create_project_skill,
    default_skill_catalog,
    import_skills,
    install_import,
    set_skill_enabled,
    skill_manager_info,
    skill_records,
)
from ai_layer.skills.manager import remove_skill as manager_remove_skill
from ai_layer.skills.manager import update_skill as manager_update_skill
from ai_layer.skills.service import list_skills as all_skills
from ai_layer.skills.service import load_skill, skill_section_content, skill_sections


def skill_list(project_root: str | None = None) -> list[dict]:
    """WHEN: diagnostics or explicit manual skill discovery only. INPUT: optional project_root. Normal Cursor/Codex/Antigravity tasks rely on host-native Agent Skills discovery, not memory_context routing."""
    root = project_root_for_tool(project_root, tool="skill_list")
    with mcp_audit(root, "skill_list", arg_keys=["project_root"] if project_root else []):
        with session_scope() as db:
            _project(db, root)
        records = {
            (str(item.get("scope")), str(item.get("slug"))): item
            for item in skill_records(project_root=root, include_disabled=True)
        }
        result = []
        for x in all_skills(root):
            scope = str(x.get("scope") or "global")
            record = records.get((scope, x["slug"]))
            result.append(
                {
                    "slug": x["slug"],
                    "scope": scope,
                    "description": x["meta"].get("description", ""),
                    "attached": scope == "project",
                    "reason": "Project-scoped custom skill." if scope == "project" else None,
                    "sections": list(skill_sections(x)),
                    "managed": bool(record),
                    "source_type": record.get("source_type") if record else None,
                    "risk": record.get("risk") if record else None,
                }
            )
        return result


def skill_search(query: str, project_root: str | None = None, limit: int = 12) -> list[dict]:
    """WHEN: explicit installed-skill discovery because a concrete expertise gap exists and the slug is unknown. INPUT: query and optional project_root. Searches local/global/project skill metadata only; it never downloads Internet skills."""
    root = project_root_for_tool(project_root, tool="skill_search")
    query = _text(query, tool="skill_search", field="query")
    terms = [x for x in query.casefold().replace("-", " ").split() if x]
    with mcp_audit(root, "skill_search", arg_keys=["query", "project_root", "limit"]) as audit:
        with session_scope() as db:
            _project(db, root)
        ranked = []
        for skill in all_skills(root):
            meta = skill.get("meta") or {}
            haystack = " ".join(
                [
                    skill.get("slug", ""),
                    str(meta.get("description") or ""),
                    " ".join(str(x) for x in meta.get("keywords") or []),
                    " ".join(skill_sections(skill).keys()),
                ]
            ).casefold()
            score = sum(
                3 if term in str(skill.get("slug", "")).casefold() else 1
                for term in terms
                if term in haystack
            )
            if score:
                ranked.append((score, skill))
        ranked.sort(key=lambda item: (-item[0], item[1]["slug"]))
        result = [
            {
                "slug": skill["slug"],
                "scope": skill.get("scope", "global"),
                "description": (skill.get("meta") or {}).get("description", ""),
                "sections": list(skill_sections(skill)),
                "score": score,
            }
            for score, skill in ranked[: max(1, min(int(limit), 30))]
        ]
        audit["metrics"] = {"hits": len(result), "limit": max(1, min(int(limit), 30))}
        return result


def skill_get(slug: str, project_root: str | None = None, section: str | None = None) -> dict:
    """WHEN: a host-native skill is selected, the user explicitly requests a skill, or a concrete expertise gap names the slug. INPUT: slug required; section optional (`core`, exact `##` heading, or `full`). Prefer one exact section; full content must be explicit and exceptional."""
    root = project_root_for_tool(project_root, tool="skill_get")
    slug = _text(slug, tool="skill_get", field="slug")
    requested_section = section.strip() if isinstance(section, str) and section.strip() else None
    keys = ["slug", "project_root"] + (["section"] if requested_section else [])
    with mcp_audit(root, "skill_get", arg_keys=keys) as audit:
        skill = load_skill(slug, project_root=root)
        if not skill:
            raise ValueError(
                f"skill_get: unknown skill `{slug}`. Use skill_list only if explicit discovery is needed."
            )
        content, sections = skill_section_content(skill, requested_section)
        audit["metrics"] = {"skill_slug": skill["slug"], "section": requested_section or "full"}
        return {
            "slug": skill["slug"],
            "meta": skill["meta"],
            "section": requested_section or "full",
            "available_sections": sections,
            "content": content,
            "package": skill.get("package"),
        }


def skill_project_create(
    slug: str,
    content: str,
    project_root: str | None = None,
    description: str | None = None,
    task_terms: list[str] | str | None = None,
    always: bool = False,
    replace: bool = False,
) -> dict:
    """WHEN: the USER explicitly asks the IDE agent to create/update reusable expertise for this exact project. INPUT: slug + Markdown content; optional description/task_terms/always/replace. task_terms only enrich manual search; always is compatibility-only and does not override host-native activation. Stores machine-local project skill outside the repository, bound to durable project identity. DO NOT use to silently persist ordinary task instructions."""
    root = project_root_for_tool(project_root, tool="skill_project_create")
    slug = _text(slug, tool="skill_project_create", field="slug")
    content = _text(content, tool="skill_project_create", field="content")
    terms = _list(task_terms)
    with mcp_audit(
        root,
        "skill_project_create",
        arg_keys=[
            "slug",
            "content",
            "project_root",
            "description",
            "task_terms",
            "always",
            "replace",
        ],
    ) as audit:
        with session_scope() as db:
            _project(db, root)
        result = create_project_skill(
            root,
            slug=slug,
            content=content,
            description=description,
            task_terms=terms,
            always=always,
            replace=replace,
        )
        audit["metrics"] = {
            "skill_slug": result.get("slug"),
            "scope": "project",
            "risk": result.get("risk"),
        }
        return {**result, "project_root": root, "available_now": True}


def skill_import(
    source: str | None = None,
    content: str | None = None,
    scope: str = "project",
    project_root: str | None = None,
    slug: str | None = None,
    description: str | None = None,
    task_terms: list[str] | str | None = None,
    always: bool = False,
    source_member: str | None = None,
) -> dict:
    """WHEN: the USER explicitly asks to add a downloaded/local/URL/catalog/inline skill. INPUT: source path/https URL/catalog:<slug> OR content; optional source_member selects one SKILL.md from a multi-skill package. Scope defaults to project. This only validates/quarantines and returns import_id(s); call skill_install after the user-authorized import. Project identity never comes from cwd."""
    root = project_root_for_tool(project_root, tool="skill_import")
    if not source and not content:
        raise ValueError("skill_import: provide `source` or `content`")
    wanted_scope = (scope or "project").strip().casefold()
    with mcp_audit(
        root,
        "skill_import",
        arg_keys=[
            "source",
            "content",
            "scope",
            "project_root",
            "slug",
            "description",
            "task_terms",
            "always",
            "source_member",
        ],
    ) as audit:
        with session_scope() as db:
            _project(db, root)
        previews = import_skills(
            source,
            content=content,
            scope=wanted_scope,
            project_root=root if wanted_scope == "project" else None,
            slug=slug,
            description=description,
            task_terms=_list(task_terms),
            always=always,
            source_member=source_member,
        )
        audit["metrics"] = {
            "imports": len(previews),
            "scope": wanted_scope,
            "risks": [x.get("risk") for x in previews],
        }
        return {
            "scope": wanted_scope,
            "project_root": root,
            "status": "quarantined",
            "imports": previews,
            "next": "Review validation/risk and call skill_install(import_id=..., approve=true).",
        }


def skill_catalog() -> dict:
    """WHEN: the user asks which curated external skills AI Layer can install. Read-only; never downloads or installs anything."""
    return {
        "skills": default_skill_catalog(),
        "install_flow": "skill_import(source='catalog:<slug>', scope='global'|'project') -> review -> skill_install(approve=true)",
    }


def skill_install(
    import_id: str,
    approve: bool,
    project_root: str | None = None,
    replace: bool = False,
    allow_high_risk: bool = False,
) -> dict:
    """WHEN: install a previously validated skill_import after explicit user authorization. INPUT: import_id and approve=true; replace/allow_high_risk require explicit intent. Project-scoped imports are identity-checked against the durable registered project."""
    root = project_root_for_tool(project_root, tool="skill_install")
    import_id = _text(import_id, tool="skill_install", field="import_id")
    with mcp_audit(
        root,
        "skill_install",
        arg_keys=["import_id", "approve", "project_root", "replace", "allow_high_risk"],
    ) as audit:
        with session_scope() as db:
            _project(db, root)
        result = install_import(
            import_id,
            approve=bool(approve),
            replace=replace,
            allow_high_risk=allow_high_risk,
            project_root=root,
        )
        audit["metrics"] = {
            "skill_slug": result.get("slug"),
            "scope": result.get("scope"),
            "risk": result.get("risk"),
        }
        return {**result, "available_now": True, "project_root": root}


def skill_update(
    slug: str,
    scope: str = "project",
    project_root: str | None = None,
    allow_high_risk: bool = False,
) -> dict:
    """WHEN: the USER explicitly asks to refresh a registry-managed skill from its saved local-file/HTTPS source. INPUT: slug/scope. Agent-authored/inline/directory skills must be re-imported explicitly instead of guessed."""
    root = project_root_for_tool(project_root, tool="skill_update")
    slug = _text(slug, tool="skill_update", field="slug")
    wanted_scope = (scope or "project").strip().casefold()
    with mcp_audit(
        root, "skill_update", arg_keys=["slug", "scope", "project_root", "allow_high_risk"]
    ) as audit:
        with session_scope() as db:
            _project(db, root)
        result = manager_update_skill(
            slug,
            scope=wanted_scope,
            project_root=root if wanted_scope == "project" else None,
            allow_high_risk=allow_high_risk,
        )
        audit["metrics"] = {"skill_slug": slug, "scope": wanted_scope, "risk": result.get("risk")}
        return {**result, "available_now": True, "project_root": root}


def skill_set_enabled(
    slug: str,
    enabled: bool,
    scope: str = "project",
    project_root: str | None = None,
) -> dict:
    """WHEN: the USER explicitly enables/disables a registry-managed custom skill. INPUT: slug, enabled, scope. Does not delete the skill."""
    root = project_root_for_tool(project_root, tool="skill_set_enabled")
    slug = _text(slug, tool="skill_set_enabled", field="slug")
    wanted_scope = (scope or "project").strip().casefold()
    with mcp_audit(
        root, "skill_set_enabled", arg_keys=["slug", "enabled", "scope", "project_root"]
    ) as audit:
        with session_scope() as db:
            _project(db, root)
        result = set_skill_enabled(
            slug,
            scope=wanted_scope,
            enabled=bool(enabled),
            project_root=root if wanted_scope == "project" else None,
        )
        audit["metrics"] = {"skill_slug": slug, "scope": wanted_scope, "enabled": bool(enabled)}
        return {**result, "available_now": True, "project_root": root}


def skill_remove(slug: str, scope: str = "project", project_root: str | None = None) -> dict:
    """WHEN: the USER explicitly removes a registry-managed custom skill. INPUT: slug and scope. Built-in/unmanaged skill files are never deleted by this tool."""
    root = project_root_for_tool(project_root, tool="skill_remove")
    slug = _text(slug, tool="skill_remove", field="slug")
    wanted_scope = (scope or "project").strip().casefold()
    with mcp_audit(root, "skill_remove", arg_keys=["slug", "scope", "project_root"]) as audit:
        with session_scope() as db:
            _project(db, root)
        result = manager_remove_skill(
            slug, scope=wanted_scope, project_root=root if wanted_scope == "project" else None
        )
        audit["metrics"] = {"skill_slug": slug, "scope": wanted_scope}
        return {**result, "project_root": root}


def skill_info(slug: str, project_root: str | None = None) -> dict:
    """WHEN: inspect provenance/status for one custom skill. INPUT: slug, optional project_root. For content use skill_get."""
    root = project_root_for_tool(project_root, tool="skill_info")
    slug = _text(slug, tool="skill_info", field="slug")
    with mcp_audit(root, "skill_info", arg_keys=["slug", "project_root"]):
        with session_scope() as db:
            _project(db, root)
        record = skill_manager_info(slug, project_root=root)
        skill = load_skill(slug, project_root=root)
        if record is None and skill is None:
            raise ValueError(f"skill_info: unknown skill `{slug}`")
        return {
            "slug": slug,
            "project_root": root,
            "registry": record,
            "scope": (skill or {}).get("scope", "global") if skill else (record or {}).get("scope"),
            "description": ((skill or {}).get("meta") or {}).get("description", ""),
            "sections": list(skill_sections(skill)) if skill else [],
        }


# MCP schema/handler registration remains local to this capability adapter.
skill_list = core_tool()(skill_list)
skill_search = core_tool()(skill_search)
skill_get = core_tool()(skill_get)
skill_project_create = core_tool()(skill_project_create)
skill_import = core_tool()(skill_import)
skill_catalog = core_tool()(skill_catalog)
skill_install = core_tool()(skill_install)
skill_update = core_tool()(skill_update)
skill_set_enabled = core_tool()(skill_set_enabled)
skill_remove = core_tool()(skill_remove)
skill_info = core_tool()(skill_info)
