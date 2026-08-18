from __future__ import annotations

import re
from pathlib import Path


def rewrite(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"syntax-fix mismatch: {path}: {pattern[:100]!r}")
    file.write_text(updated, encoding="utf-8")


rewrite(
    "tests/test_sync.py",
    r"def test_sync_updates_template_version_and_machine_registry\(.*?\n\ndef test_project_config_write_is_failure_atomic",
    r'''def test_sync_updates_template_version_and_machine_registry(tmp_path: Path, monkeypatch):
    from ai_layer.core.registry import register_project

    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    get_settings.cache_clear()
    register_project(project, "legacy-id", "legacy", mode="standard", provenance="allow")
    meta = home / ".ai-layer" / "projects" / "legacy-id"
    meta.mkdir(parents=True)
    (meta / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "project_id": "legacy-id",
                "name": "legacy",
                "root": str(project.resolve()),
                "mode": "standard",
                "provenance": "allow",
            }
        ),
        encoding="utf-8",
    )

    result = sync_project_integrations(project)
    config = yaml.safe_load((meta / "project.yaml").read_text(encoding="utf-8"))
    assert result["template_version"] == INTEGRATION_TEMPLATE_VERSION
    assert result["repository_writes"] is False
    assert config["integration_template_version"] == INTEGRATION_TEMPLATE_VERSION
    assert list_registered_projects()[0]["root"] == str(project.resolve())
    assert not (project / ".ai-layer").exists()
    get_settings.cache_clear()


def test_project_config_write_is_failure_atomic''',
)
rewrite(
    "tests/test_sync.py",
    r"def test_init_commits_project_identity_before_publishing_filesystem_metadata\(.*?\n\ndef test_init_refuses_symlinked_ai_layer_state_directory",
    r'''def test_init_commits_project_identity_before_publishing_filesystem_metadata(
    tmp_path: Path, monkeypatch
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.core import service
    from ai_layer.db.base import Base
    from ai_layer.db.models import Project

    project_root = tmp_path / "project"
    project_root.mkdir()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def fail_publish(path, data):
        raise RuntimeError("simulated metadata publish failure")

    monkeypatch.setattr(service, "_write_project_config", fail_publish)
    with Session(engine) as db:
        try:
            service.init_project(db, project_root)
        except RuntimeError as exc:
            assert "metadata publish failure" in str(exc)
        else:
            raise AssertionError("filesystem publication failure must propagate")

    with Session(engine) as verify:
        project = verify.scalar(
            select(Project).where(Project.root_path == str(project_root.resolve()))
        )
        assert project is not None
        assert not (project_root / ".ai-layer" / "project.yaml").exists()


def test_init_refuses_symlinked_ai_layer_state_directory''',
)
rewrite(
    "tests/test_sync.py",
    r"def test_init_preserves_user_owned_legacy_rule_without_repository_bindings\(.*?\n\ndef test_private_init_requires_git_before_db_identity",
    r'''def test_init_preserves_user_owned_legacy_rule_without_repository_bindings(
    tmp_path: Path, monkeypatch
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.core import service
    from ai_layer.core.paths import project_meta_dir
    from ai_layer.db.base import Base
    from ai_layer.db.models import Project

    home = tmp_path / "home-preflight"
    project_root = tmp_path / "collision-project"
    home.mkdir()
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    get_settings.cache_clear()
    legacy_rule = project_root / ".cursor" / "rules" / "ai-layer.mdc"
    legacy_rule.parent.mkdir(parents=True)
    legacy_rule.write_text("user-owned rule with this historical filename\n", encoding="utf-8")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service.init_project(db, project_root)

    with Session(engine) as verify:
        assert (
            verify.scalar(select(Project).where(Project.root_path == str(project_root.resolve())))
            is not None
        )
    assert (
        legacy_rule.read_text(encoding="utf-8") == "user-owned rule with this historical filename\n"
    )
    assert project_meta_dir(project_root).is_relative_to(home / ".ai-layer")
    assert not (project_root / ".cursor" / "mcp.json").exists()
    assert not (project_root / ".agents" / "mcp_config.json").exists()
    assert not (project_root / ".mcp.json").exists()
    get_settings.cache_clear()


def test_private_init_requires_git_before_db_identity''',
)
rewrite(
    "tests/test_native_skills.py",
    r"def test_project_skill_materializes_namespaced_global_content_in_standard_mode\(.*?\n\ndef test_strict_private_project_skill_uses_namespaced_global_full_skill_only",
    r'''def test_project_skill_materializes_namespaced_global_content_in_standard_mode(
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


def test_strict_private_project_skill_uses_namespaced_global_full_skill_only''',
)
rewrite(
    "tests/test_native_skills.py",
    r"def test_project_native_sync_does_not_touch_repository_host_roots\(.*?\n\ndef test_global_native_sync_refuses_symlinked_parent",
    r'''def test_project_native_sync_does_not_touch_repository_host_roots(tmp_path: Path, monkeypatch):
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


def test_global_native_sync_refuses_symlinked_parent''',
)
