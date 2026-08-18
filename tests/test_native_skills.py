from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml

from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.skills.manager import create_project_skill, set_skill_enabled
from ai_layer.skills.native import (
    native_catalog_files,
    render_native_skill,
    sync_global_native_skills,
    sync_project_native_skills,
    validate_native_catalog,
)
from ai_layer.skills.native_descriptor import (
    NATIVE_PACKAGE_RESOURCE_NOTICE,
    native_package_resource_notice,
)
from ai_layer.skills.native_files import sync_native_root
from ai_layer.skills.service import load_skill, skill_section_content


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n", 2)[1]) or {}


def test_global_native_skills_publish_to_supported_host_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    get_settings.cache_clear()
    try:
        result = sync_global_native_skills(home=tmp_path / "user")
        assert result["routing_owner"] == "host-native"
        assert result["activation_payload"] == "full-authoritative-skill"
        assert result["canonical_skills"] == 44
        assert result["validation"]["ok"] is True
        shared = tmp_path / "user" / ".agents" / "skills" / "django" / "SKILL.md"
        antigravity = tmp_path / "user" / ".gemini" / "config" / "skills" / "django" / "SKILL.md"
        claude = tmp_path / "user" / ".claude" / "skills" / "django" / "SKILL.md"
        assert shared.is_file() and antigravity.is_file() and claude.is_file()
        assert shared.read_text(encoding="utf-8") == antigravity.read_text(encoding="utf-8")
        assert shared.read_text(encoding="utf-8") == claude.read_text(encoding="utf-8")
        text = shared.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        assert meta["name"] == "django"
        assert "description" in meta
        assert set(meta) == {"name", "description"}
        assert "## Core contract" in text
        assert "## Decision rules" in text
        assert "## Migrations" in text
        assert "skill_get" not in text
        assert "required" not in meta and "recommended" not in meta

        workflow_native = (
            tmp_path / "user" / ".agents" / "skills" / "ai-layer-workflow" / "SKILL.md"
        )
        assert workflow_native.is_file()
        workflow_text = workflow_native.read_text(encoding="utf-8")
        workflow_meta = _frontmatter(workflow_text)
        assert workflow_meta["name"] == "ai-layer-workflow"
        assert "Managed Tasks/Epics" in workflow_meta["description"]
        assert "always-on bootstrap" in workflow_meta["description"]
        assert "## Workflow" in workflow_text
        assert "## Project intelligence and durable memory" in workflow_text
    finally:
        get_settings.cache_clear()


def test_ai_layer_workflow_core_keeps_complete_entry_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    get_settings.cache_clear()
    try:
        skill = load_skill("ai-layer-workflow")
        assert skill is not None
        core, sections = skill_section_content(skill, "core")
        assert "## Apply when" in core
        assert "## Core contract" in core
        assert "## Decision rules" in core
        assert "skill core clipped" not in core
        assert "`project_status` is the first AI Layer state call" in core
        assert "AI Layer is an engineering control plane" in core
        assert "default is host-native execution" in core
        assert "do not create a Task merely to authorize editing" in core
        assert "`project_search" in core
        assert "Workflow" in sections
        assert "Evidence to inspect" in sections
        assert "Verification" in sections
        assert "Failure modes" in sections
        assert "Completion criteria" in sections
        assert len(core) < len(skill["content"])
    finally:
        get_settings.cache_clear()


def test_native_activation_contains_complete_authoritative_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    get_settings.cache_clear()
    try:
        skill = load_skill("django")
        assert skill is not None
        native = render_native_skill(skill)
        meta = _frontmatter(native)
        assert meta == {
            "name": "django",
            "description": skill["meta"]["description"],
        }
        assert skill["content"] in native
        assert "## Core contract" in native
        assert "## Decision rules" in native
        assert "## Migrations" in native
        assert "skill_get" not in native
        assert len(native.encode("utf-8")) > len(skill["content"].encode("utf-8"))
        content, _ = skill_section_content(skill, "Migrations")
        assert "historical" in content.casefold()
    finally:
        get_settings.cache_clear()


def test_project_skill_materializes_namespaced_global_content_in_standard_mode(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("HOME", str(home))
    get_settings.cache_clear()
    try:
        register_project(project, project_id=str(uuid.uuid4()), name="repo")
        result = create_project_skill(
            project,
            slug="food-iiko-order-rules",
            description="iiko order, cart synchronization, webhook and payment invariants for this project only.",
            task_terms=["iiko-order", "cart-sync"],
            content="# iiko project rules\n\n## Core contract\n\nPreserve the existing order pipeline and cart synchronization invariants.\n",
        )
        assert result["native_sync"]["scope"] == "namespaced-global-zero-footprint"
        assert result["native_sync"]["repository_writes"] is False
        assert result["native_sync"]["activation_payload"] == "full-authoritative-skill"
        assert not (project / ".agents").exists()
        assert not (project / ".claude").exists()
        catalog = native_catalog_files(project, home=home)
        target = next(path for path in catalog["cursor"] if "food-iiko-order-rules" in str(path))
        target_text = target.read_text(encoding="utf-8")
        assert "Preserve the existing order pipeline" in target_text
        assert str(project.resolve()) in _frontmatter(target_text)["description"]
        assert NATIVE_PACKAGE_RESOURCE_NOTICE not in target_text
        assert "skill_get" not in target_text

        set_skill_enabled(
            "food-iiko-order-rules", scope="project", enabled=False, project_root=project
        )
        assert not target.exists()
    finally:
        get_settings.cache_clear()


def test_strict_private_project_skill_uses_namespaced_global_full_skill_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".ai-layer.yaml").write_text("mode: strict-private\n", encoding="utf-8")
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("HOME", str(home))
    get_settings.cache_clear()
    try:
        register_project(
            project,
            project_id=str(uuid.uuid4()),
            name="repo",
            mode="strict-private",
            provenance="forbid",
        )
        create_project_skill(
            project,
            slug="private-release",
            description="Project-only release, deployment, rollback and operator checks for the registered private repository.",
            content="# Private release\n\n## Release checks\n\nVerify deployment and rollback contracts.\n",
        )
        result = sync_project_native_skills(project, home=home)
        assert result["repository_writes"] is False
        assert result["activation_payload"] == "full-authoritative-skill"
        assert not (project / ".agents").exists()
        catalog = native_catalog_files(project, home=home)
        assert any("private-release" in str(path) for path in catalog["cursor"])
        assert any("private-release" in str(path) for path in catalog["antigravity"])
        native = next(path for path in catalog["cursor"] if "private-release" in str(path))
        native_text = native.read_text(encoding="utf-8")
        native_meta = _frontmatter(native_text)
        assert str(project.resolve()) in native_meta["description"]
        assert "Activate only for the registered project" in native_meta["description"]
        assert "Verify deployment and rollback contracts." in native_text
    finally:
        get_settings.cache_clear()


def test_native_catalog_quality_gate_rejects_generic_description(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    get_settings.cache_clear()
    try:
        skill = load_skill("django")
        assert skill is not None
        broken = dict(skill)
        broken["meta"] = {**skill["meta"], "description": "Useful for software development."}
        result = validate_native_catalog([broken])
        assert result["ok"] is False
        assert any(
            "generic" in issue["problem"] or "short" in issue["problem"]
            for issue in result["issues"]
        )
    finally:
        get_settings.cache_clear()


def test_upgrade_skips_legacy_invalid_custom_skill_without_blocking_native_catalog(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    state = home / ".ai-layer"
    monkeypatch.setenv("AI_LAYER_HOME", str(state))
    monkeypatch.setenv("HOME", str(home))
    get_settings.cache_clear()
    try:
        skills_dir = get_settings().skills_dir
        skills_dir.mkdir(parents=True, exist_ok=True)
        legacy = skills_dir / "legacy-custom.md"
        legacy.write_text(
            "---\nslug: legacy-custom\ndescription: Useful for software development.\n---\n"
            "# Legacy custom\n\n## Core\n\nKeep this canonical legacy content available.\n",
            encoding="utf-8",
        )

        result = sync_global_native_skills(home=home)

        assert result["canonical_skills"] == 45
        assert result["published_skills"] == 44
        assert result["blocked_skills"] == 1
        assert result["validation"]["ok"] is False
        assert result["validation"]["publication"]["blocked"][0]["slug"] == "legacy-custom"
        assert legacy.is_file()
        assert not (home / ".agents" / "skills" / "legacy-custom" / "SKILL.md").exists()
        assert (home / ".agents" / "skills" / "django" / "SKILL.md").is_file()
        assert (home / ".agents" / "skills" / "ai-layer-workflow" / "SKILL.md").is_file()
    finally:
        get_settings.cache_clear()


def _owned_native_skill(canonical: str, *, scope: str = "global", project: str = "-") -> str:
    return (
        f"<!-- AI-LAYER NATIVE SKILL v2 scope={scope} project={project} canonical={canonical} -->\n"
        f"# {canonical}\n"
    )


def test_sync_native_root_refuses_symlinked_root(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    skills = tmp_path / "skills"
    skills.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink"):
        sync_native_root(
            tmp_path, "skills", desired={"demo": _owned_native_skill("demo")}, scope="global"
        )

    assert list(outside.rglob("*")) == []
    assert not (outside / "demo" / "SKILL.md").exists()


def test_sync_native_root_refuses_symlinked_parent(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".claude").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink"):
        sync_native_root(
            tmp_path,
            ".claude",
            "skills",
            desired={"demo": _owned_native_skill("demo")},
            scope="global",
        )

    assert list(outside.rglob("*")) == []
    assert not (outside / "skills").exists()


def test_project_native_sync_does_not_touch_repository_host_roots(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "repo"
    outside = tmp_path / "outside"
    home.mkdir()
    project.mkdir()
    outside.mkdir()
    skills = project / ".claude" / "skills"
    skills.parent.mkdir()
    skills.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("HOME", str(home))
    get_settings.cache_clear()
    try:
        result = sync_project_native_skills(project, home=home)
        assert result["repository_writes"] is False
        assert result["scope"] == "namespaced-global-zero-footprint"
        assert list(outside.rglob("*")) == []
        assert skills.is_symlink()
    finally:
        get_settings.cache_clear()


def test_global_native_sync_refuses_symlinked_parent(tmp_path: Path, monkeypatch):
    home = tmp_path / "user"
    outside = tmp_path / "outside"
    home.mkdir()
    outside.mkdir()
    (home / ".agents").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(home))
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="symlink"):
            sync_global_native_skills(home=home)
        assert list(outside.rglob("*")) == []
        assert not (outside / "skills").exists()
    finally:
        get_settings.cache_clear()


def test_sync_native_root_writes_owned_skill_and_removes_stale(tmp_path: Path):
    keep = _owned_native_skill("keep")
    stale = _owned_native_skill("stale")
    result = sync_native_root(
        tmp_path, "skills", desired={"keep": keep, "stale": stale}, scope="global"
    )
    keep_path = tmp_path / "skills" / "keep" / "SKILL.md"
    stale_dir = tmp_path / "skills" / "stale"
    assert keep_path.is_file()
    assert not keep_path.is_symlink()
    assert keep_path.read_text(encoding="utf-8") == keep
    assert stale_dir.is_dir()
    assert not (tmp_path / "skills" / "keep" / "scripts").exists()
    assert result["written"]

    result = sync_native_root(tmp_path, "skills", desired={"keep": keep}, scope="global")
    assert keep_path.is_file()
    assert not stale_dir.exists()
    assert result["removed"]


def test_sync_native_root_refuses_symlinked_skill_directory(tmp_path: Path):
    outside = tmp_path / "outside"
    skills = tmp_path / "skills"
    outside.mkdir()
    skills.mkdir()
    (skills / "demo").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink"):
        sync_native_root(
            tmp_path, "skills", desired={"demo": _owned_native_skill("demo")}, scope="global"
        )

    assert list(outside.rglob("*")) == []
    assert not (outside / "SKILL.md").exists()


def test_sync_native_root_refuses_unowned_skill_md(tmp_path: Path):
    target = tmp_path / "skills" / "django" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("# user-owned skill\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="ownership conflict"):
        sync_native_root(
            tmp_path,
            "skills",
            desired={"django": _owned_native_skill("django")},
            scope="global",
        )

    assert target.read_text(encoding="utf-8") == "# user-owned skill\n"
    assert list(target.parent.iterdir()) == [target]


def _install_packaged_search_skill(tmp_path: Path) -> dict:
    import zipfile

    from ai_layer.skills.manager import import_skills, install_import

    archive = tmp_path / "packaged-skill.zip"
    skill = """---
name: ui-ux-pro-max
description: UI/UX interface design systems, dashboard layouts, typography, color selection, accessibility and component guidance.
---
# UI/UX Pro Max

## When to Apply

Use for dashboard and interface design.

## Running search

Run scripts/search.py against package data.
"""
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("repo/.claude/skills/ui-ux-pro-max/SKILL.md", skill)
        zf.writestr("repo/.claude/skills/ui-ux-pro-max/scripts/search.py", "print('search')\n")
        zf.writestr("repo/.claude/skills/ui-ux-pro-max/references/guide.md", "# guide\n")
        zf.writestr("repo/.claude/skills/ui-ux-pro-max/assets/note.txt", "note\n")
    preview = import_skills(str(archive), scope="global", source_member="ui-ux-pro-max/SKILL.md")[0]
    return install_import(preview["import_id"], approve=True)


def test_native_render_omits_package_notice_without_store_root():
    skill = {
        "slug": "django",
        "meta": {
            "description": (
                "Django models, ORM queries, transactions, migrations, request "
                "boundaries and production-safe application structure."
            )
        },
        "content": "# Django\n\n## Core contract\n\nKeep request boundaries explicit.\n",
    }
    native = render_native_skill(skill)
    assert native_package_resource_notice(skill) == ""
    assert NATIVE_PACKAGE_RESOURCE_NOTICE not in native
    assert "skill_get" not in native


def test_native_render_injects_package_store_notice_without_copying_root():
    package_root = "/machine/skill-packages/global/ui-ux-pro-max"
    skill = {
        "slug": "ui-ux-pro-max",
        "meta": {
            "description": (
                "UI/UX interface design systems, dashboard layouts, typography, "
                "color selection, accessibility and component guidance."
            )
        },
        "content": "# UI/UX\n\n## Running search\n\nRun scripts/search.py against package data.\n",
        "package": {"root": package_root, "relative_resource_dirs": ["scripts"]},
    }
    native = render_native_skill(skill)
    assert native_package_resource_notice(skill) == NATIVE_PACKAGE_RESOURCE_NOTICE
    assert NATIVE_PACKAGE_RESOURCE_NOTICE in native
    assert "Run scripts/search.py against package data." in native
    assert package_root not in native
    assert set(_frontmatter(native)) == {"name", "description"}


def test_native_render_omits_package_notice_without_resource_dirs():
    skill = {
        "slug": "ui-ux-pro-max",
        "meta": {
            "description": (
                "UI/UX interface design systems, dashboard layouts, typography, "
                "color selection, accessibility and component guidance."
            )
        },
        "content": "# UI/UX\n\n## Core contract\n\nKeep guidance in this file.\n",
        "package": {
            "root": "/machine/skill-packages/global/ui-ux-pro-max",
            "relative_resource_dirs": [],
        },
    }
    native = render_native_skill(skill)
    assert native_package_resource_notice(skill) == ""
    assert NATIVE_PACKAGE_RESOURCE_NOTICE not in native
    assert "skill_get" not in native


def test_packaged_skill_native_sync_resolves_resources_from_store(tmp_path, monkeypatch):
    home = tmp_path / "home"
    user = tmp_path / "user"
    home.mkdir()
    user.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("HOME", str(user))
    get_settings.cache_clear()
    try:
        installed = _install_packaged_search_skill(tmp_path)
        package_root = Path(installed["package_root"])
        loaded = load_skill("ui-ux-pro-max")
        assert loaded is not None
        assert loaded["package"]["root"] == str(package_root)
        assert loaded["package"]["contract"] in NATIVE_PACKAGE_RESOURCE_NOTICE
        assert loaded["package"]["relative_resource_dirs"] == ["scripts", "references", "assets"]
        assert (package_root / "scripts" / "search.py").is_file()
        assert (package_root / "references" / "guide.md").is_file()
        assert (package_root / "assets" / "note.txt").is_file()

        native_dir = user / ".agents" / "skills" / "ui-ux-pro-max"
        native_skill = native_dir / "SKILL.md"
        assert native_skill.is_file()
        assert not native_skill.is_symlink()
        assert sorted(path.name for path in native_dir.iterdir()) == ["SKILL.md"]
        assert not (native_dir / "scripts").exists()
        assert not (native_dir / "references").exists()
        assert not (native_dir / "assets").exists()

        text = native_skill.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        assert set(meta) == {"name", "description"}
        assert NATIVE_PACKAGE_RESOURCE_NOTICE in text
        assert "Run scripts/search.py against package data." in text
        assert str(package_root) not in text
        assert (user / ".claude" / "skills" / "ui-ux-pro-max" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == text
        assert not (user / ".claude" / "skills" / "ui-ux-pro-max" / "scripts").exists()
    finally:
        get_settings.cache_clear()


def test_packaged_skill_native_sync_refuses_unowned_skill_md(tmp_path, monkeypatch):
    home = tmp_path / "home"
    user = tmp_path / "user"
    home.mkdir()
    user.mkdir()
    target = user / ".agents" / "skills" / "ui-ux-pro-max" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("# user-owned skill\n", encoding="utf-8")
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("HOME", str(user))
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ownership conflict"):
            _install_packaged_search_skill(tmp_path)
        assert target.read_text(encoding="utf-8") == "# user-owned skill\n"
        assert list(target.parent.iterdir()) == [target]
        assert not (target.parent / "scripts").exists()
        assert not (target.parent / "references").exists()
        assert not (target.parent / "assets").exists()
    finally:
        get_settings.cache_clear()
