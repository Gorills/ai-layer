from __future__ import annotations

import uuid

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
        assert "managed Tasks/Epics" in workflow_meta["description"]
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


def test_project_skill_materializes_full_content_once_in_standard_workspace(tmp_path, monkeypatch):
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
        assert result["native_sync"]["scope"] == "workspace"
        assert result["native_sync"]["activation_payload"] == "full-authoritative-skill"
        target = project / ".agents" / "skills" / "food-iiko-order-rules" / "SKILL.md"
        assert target.is_file()
        target_text = target.read_text(encoding="utf-8")
        assert "Preserve the existing order pipeline" in target_text
        assert not (project / ".cursor" / "skills" / "ai-layer" / "SKILL.md").exists()
        assert not (project / ".claude" / "skills" / "ai-layer" / "SKILL.md").exists()

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
