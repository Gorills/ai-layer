from __future__ import annotations

import uuid

import yaml

from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.skills.manager import create_project_skill, set_skill_enabled
from ai_layer.skills.native import (
    native_catalog_files,
    render_native_descriptor,
    sync_global_native_skills,
    sync_project_native_skills,
    validate_native_catalog,
)
from ai_layer.skills.service import load_skill, skill_section_content


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n", 2)[1]) or {}


def test_global_native_descriptors_share_agents_root_for_cursor_and_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    get_settings.cache_clear()
    try:
        result = sync_global_native_skills(home=tmp_path / "user")
        assert result["routing_owner"] == "host-native"
        assert result["canonical_skills"] == 42
        assert result["validation"]["ok"] is True
        shared = tmp_path / "user" / ".agents" / "skills" / "django" / "SKILL.md"
        antigravity = tmp_path / "user" / ".gemini" / "config" / "skills" / "django" / "SKILL.md"
        assert shared.is_file() and antigravity.is_file()
        assert shared.read_text(encoding="utf-8") == antigravity.read_text(encoding="utf-8")
        meta = _frontmatter(shared.read_text(encoding="utf-8"))
        assert meta["name"] == "django"
        assert "description" in meta
        assert set(meta) == {"name", "description"}
        assert "skill_get" in shared.read_text(encoding="utf-8")
        assert "required" not in meta and "recommended" not in meta
    finally:
        get_settings.cache_clear()


def test_descriptor_is_thin_and_points_to_selective_authoritative_retrieval(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "state"))
    get_settings.cache_clear()
    try:
        skill = load_skill("django")
        assert skill is not None
        descriptor = render_native_descriptor(skill)
        assert len(descriptor.encode("utf-8")) < 1800
        assert 'section="<exact section>"' in descriptor
        assert 'section="full"' in descriptor
        assert "## Migrations" not in descriptor
        content, _ = skill_section_content(skill, "Migrations")
        assert "historical" in content.casefold()
    finally:
        get_settings.cache_clear()


def test_project_skill_materializes_once_in_standard_workspace(tmp_path, monkeypatch):
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
        target = project / ".agents" / "skills" / "food-iiko-order-rules" / "SKILL.md"
        assert target.is_file()
        assert not (project / ".cursor" / "skills" / "ai-layer" / "SKILL.md").exists()
        assert not (project / ".claude" / "skills" / "ai-layer" / "SKILL.md").exists()

        set_skill_enabled(
            "food-iiko-order-rules", scope="project", enabled=False, project_root=project
        )
        assert not target.exists()
    finally:
        get_settings.cache_clear()


def test_strict_private_project_skill_uses_namespaced_global_descriptor_only(tmp_path, monkeypatch):
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
        assert not (project / ".agents").exists()
        catalog = native_catalog_files(project, home=home)
        assert any("private-release" in str(path) for path in catalog["cursor"])
        assert any("private-release" in str(path) for path in catalog["antigravity"])
        descriptor = next(path for path in catalog["cursor"] if "private-release" in str(path))
        descriptor_meta = _frontmatter(descriptor.read_text(encoding="utf-8"))
        assert str(project.resolve()) in descriptor_meta["description"]
        assert "Activate only for the registered project" in descriptor_meta["description"]
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

        assert result["canonical_skills"] == 43
        assert result["published_skills"] == 42
        assert result["blocked_skills"] == 1
        assert result["validation"]["ok"] is False
        assert result["validation"]["publication"]["blocked"][0]["slug"] == "legacy-custom"
        assert legacy.is_file()
        assert not (home / ".agents" / "skills" / "legacy-custom" / "SKILL.md").exists()
        assert (home / ".agents" / "skills" / "django" / "SKILL.md").is_file()
    finally:
        get_settings.cache_clear()
