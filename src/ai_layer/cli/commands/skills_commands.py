from __future__ import annotations
from ai_layer.cli.root import agent_app, skill_app, echo
from pathlib import Path
from ai_layer.agents.policy import policy_path as agent_policy_path
from ai_layer.agents.policy import configure_policy as configure_agent_policy
from ai_layer.skills.manager import default_skill_catalog
from ai_layer.core.config import get_settings
from ai_layer.skills.manager import import_skills
from ai_layer.skills.manager import inbox_sources
from ai_layer.agents.policy import install_cursor_profiles
from ai_layer.skills.manager import install_import
from ai_layer.skills.service import list_skills as list_available_skills
from ai_layer.agents.policy import load_policy as load_agent_policy
from ai_layer.skills.manager import remove_skill as manager_remove_skill
from ai_layer.skills.manager import update_skill as manager_update_skill
from ai_layer.core.paths import normalize_root
from ai_layer.skills.manager import set_skill_enabled
from ai_layer.skills.manager import skill_manager_info
from ai_layer.skills.manager import skill_records
from ai_layer.skills.service import skill_sections
import typer
from ai_layer.skills.manager import validate_skill_text

def _skill_scope_root(scope: str, project: str | None) -> tuple[str, str | None]:
    wanted = (scope or "global").strip().casefold()
    if wanted not in {"global", "project"}:
        raise typer.BadParameter("--scope must be global or project")
    root = str(normalize_root(project or ".")) if wanted == "project" else None
    return wanted, root

def skill_list_cli(
    project: str | None = typer.Option(None, "--project", help="Include project-scoped skills for this registered project."),
):
    """List available skills and registry provenance."""
    root = str(normalize_root(project)) if project else None
    records = {(str(x.get("scope")), str(x.get("slug"))): x for x in skill_records(project_root=root, include_disabled=True)}
    items = []
    for skill in list_available_skills(root):
        scope = str(skill.get("scope") or "global")
        record = records.get((scope, skill["slug"]))
        items.append({
            "slug": skill["slug"],
            "scope": scope,
            "description": skill.get("meta", {}).get("description", ""),
            "sections": list(skill_sections(skill)),
            "managed": bool(record),
            "status": record.get("status") if record else "enabled",
            "source_type": record.get("source_type") if record else "builtin-or-local",
            "risk": record.get("risk") if record else None,
        })
    disabled = [x for x in records.values() if x.get("status") == "disabled"]
    echo({"skills": items, "disabled_managed": disabled, "project_root": root})

def skill_info_cli(
    slug: str = typer.Argument(...),
    project: str | None = typer.Option(None, "--project", help="Resolve project-scoped skill identity."),
):
    """Show registry provenance/status for one custom skill."""
    root = str(normalize_root(project)) if project else None
    record = skill_manager_info(slug, project_root=root)
    skill = next((x for x in list_available_skills(root) if x["slug"] == slug), None)
    if not record and not skill:
        raise typer.BadParameter(f"Unknown skill: {slug}")
    echo({"slug": slug, "registry": record, "skill": {"scope": skill.get("scope"), "meta": skill.get("meta"), "sections": list(skill_sections(skill))} if skill else None})

def skill_validate_cli(
    source: str = typer.Argument(..., help="Markdown skill path, or '-' for stdin."),
):
    """Normalize/validate one Markdown skill without installing it."""
    if source == "-":
        text = typer.get_text_stream("stdin").read()
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_file() or path.suffix.casefold() != ".md":
            raise typer.BadParameter("validate expects one .md file or stdin '-'")
        text = path.read_text(encoding="utf-8")
    result = validate_skill_text(text)
    result.pop("normalized", None)
    result.pop("meta", None)
    echo(result)

def skill_add_cli(
    source: str = typer.Argument(..., help=".md, directory, .zip, https URL, or '-' for stdin."),
    scope: str = typer.Option("global", "--scope", help="global or project"),
    project: str | None = typer.Option(None, "--project", help="Registered project root for project scope."),
    slug: str | None = typer.Option(None, "--slug", help="Override slug for a single-document import."),
    description: str | None = typer.Option(None, "--description"),
    task_term: list[str] = typer.Option([], "--task-term", help="Repeatable task-routing term."),
    always: bool = typer.Option(False, "--always", help="Make this project/global skill always a routing candidate."),
    source_member: str | None = typer.Option(
        None,
        "--source-member",
        help="Select one SKILL.md path from a multi-skill directory/archive/repository package.",
    ),
    approve: bool = typer.Option(False, "--approve", help="Install after validation instead of leaving quarantined."),
    replace: bool = typer.Option(False, "--replace", help="Replace the same registry-managed slug in this scope."),
    allow_high_risk: bool = typer.Option(False, "--allow-high-risk", help="Explicitly install a high-risk skill after review."),
):
    """Import one or many skills through validation/quarantine; optionally install immediately."""
    wanted_scope, root = _skill_scope_root(scope, project)
    content = typer.get_text_stream("stdin").read() if source == "-" else None
    previews = import_skills(
        None if source == "-" else source,
        content=content,
        scope=wanted_scope,
        project_root=root,
        slug=slug,
        description=description,
        task_terms=task_term,
        always=always,
        source_member=source_member,
        source_type_override="stdin" if source == "-" else None,
    )
    if not approve:
        echo({"status": "quarantined", "imports": previews, "next": "Review risk/issues, then rerun with --approve or install via MCP skill_install."})
        return
    installed = [
        install_import(
            item["import_id"],
            approve=True,
            replace=replace,
            allow_high_risk=allow_high_risk,
            project_root=root,
        )
        for item in previews
    ]
    echo({"status": "installed", "skills": installed})

def skill_catalog_cli():
    """List curated default external skill sources without downloading them."""
    echo({"skills": default_skill_catalog(), "install": "ai-layer skill add catalog:<slug> --approve"})

def skill_enable_cli(
    slug: str = typer.Argument(...),
    scope: str = typer.Option("global", "--scope"),
    project: str | None = typer.Option(None, "--project"),
):
    """Enable a registry-managed custom skill."""
    wanted_scope, root = _skill_scope_root(scope, project)
    echo(set_skill_enabled(slug, scope=wanted_scope, enabled=True, project_root=root))

def skill_disable_cli(
    slug: str = typer.Argument(...),
    scope: str = typer.Option("global", "--scope"),
    project: str | None = typer.Option(None, "--project"),
):
    """Disable a registry-managed custom skill without deleting it."""
    wanted_scope, root = _skill_scope_root(scope, project)
    echo(set_skill_enabled(slug, scope=wanted_scope, enabled=False, project_root=root))

def skill_remove_cli(
    slug: str = typer.Argument(...),
    scope: str = typer.Option("global", "--scope"),
    project: str | None = typer.Option(None, "--project"),
):
    """Remove a registry-managed custom skill; built-ins/unmanaged files are protected."""
    wanted_scope, root = _skill_scope_root(scope, project)
    echo(manager_remove_skill(slug, scope=wanted_scope, project_root=root))

def skill_update_cli(
    slug: str = typer.Argument(...),
    scope: str = typer.Option("global", "--scope"),
    project: str | None = typer.Option(None, "--project"),
    allow_high_risk: bool = typer.Option(False, "--allow-high-risk"),
):
    """Refresh a registry-managed skill from its original local-file/HTTPS source."""
    wanted_scope, root = _skill_scope_root(scope, project)
    echo(manager_update_skill(slug, scope=wanted_scope, project_root=root, allow_high_risk=allow_high_risk))

def skill_inbox_cli(
    scope: str = typer.Option("global", "--scope"),
    project: str | None = typer.Option(None, "--project"),
    approve: bool = typer.Option(False, "--approve"),
    allow_high_risk: bool = typer.Option(False, "--allow-high-risk"),
):
    """Inspect/import .md/.zip/directories dropped into ~/.ai-layer/skill-inbox."""
    wanted_scope, root = _skill_scope_root(scope, project)
    sources = inbox_sources()
    previews = []
    for source in sources:
        previews.extend(import_skills(str(source), scope=wanted_scope, project_root=root))
    if not approve:
        echo({"inbox": str(get_settings().skill_inbox_dir), "sources": [str(x) for x in sources], "status": "quarantined", "imports": previews})
        return
    installed = [install_import(x["import_id"], approve=True, allow_high_risk=allow_high_risk, project_root=root) for x in previews]
    echo({"inbox": str(get_settings().skill_inbox_dir), "status": "installed", "skills": installed})

def agent_policy_show():
    """Show machine-side cost/model routing used by task_next."""
    echo({
        "path": str(agent_policy_path()),
        "policy": load_agent_policy(),
        "assurance": "AI Layer requests these profiles/models; the MCP host may not expose authenticated actual-model metadata.",
    })

def agent_policy_configure(
    economy_model: str | None = typer.Option(None, "--economy-model"),
    balanced_model: str | None = typer.Option(None, "--balanced-model"),
    strong_model: str | None = typer.Option(None, "--strong-model"),
    default_cost_policy: str | None = typer.Option(None, "--default-cost-policy"),
    install_cursor: bool = typer.Option(True, "--install-cursor/--no-install-cursor"),
):
    """Update machine-side model mapping and refresh AI Layer-managed Cursor subagent profiles."""
    try:
        result = configure_agent_policy(
            economy_model=economy_model,
            balanced_model=balanced_model,
            strong_model=strong_model,
            default_cost_policy=default_cost_policy,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if install_cursor:
        result["cursor_profiles"] = install_cursor_profiles(Path.home())
    echo(result)


# Public CLI contract registrations.
skill_app.command("list")(skill_list_cli)
skill_app.command("info")(skill_info_cli)
skill_app.command("validate")(skill_validate_cli)
skill_app.command("add")(skill_add_cli)
skill_app.command("catalog")(skill_catalog_cli)
skill_app.command("enable")(skill_enable_cli)
skill_app.command("disable")(skill_disable_cli)
skill_app.command("remove")(skill_remove_cli)
skill_app.command("update")(skill_update_cli)
skill_app.command("inbox")(skill_inbox_cli)
agent_app.command("policy")(agent_policy_show)
agent_app.command("configure")(agent_policy_configure)
