from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"followup replacement mismatch: {path}: {old[:100]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def rewrite(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"followup regex mismatch: {path}: {pattern[:100]!r}")
    file.write_text(updated, encoding="utf-8")


replace_once(
    "src/ai_layer/core/paths.py",
    '''        base = get_settings().home / "projects"
        if base.is_symlink():
            raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
        base.mkdir(parents=True, exist_ok=True)
        return _safe_child(base, project_id)
''',
    '''        base = get_settings().home / "projects"
        if base.is_symlink():
            raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
        base_resolved = base.expanduser().resolve()
        try:
            base_resolved.relative_to(resolved)
        except ValueError:
            pass
        else:
            raise RuntimeError(
                f"AI Layer machine state must be outside the registered project root: {base_resolved}"
            )
        base.mkdir(parents=True, exist_ok=True)
        return _safe_child(base, project_id)
''',
)

replace_once(
    "src/ai_layer/core/service.py",
    '''def _ensure_rules(meta: Path) -> None:
''',
    '''def _legacy_local_state_owned(path: Path, root: Path, project_id: str) -> bool:
    """Recognize legacy repository-local state without claiming unrelated user content."""
    if not path.exists():
        return False
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer project metadata: {path}")
    if not path.is_dir():
        return False
    config = path / "project.yaml"
    if not config.is_file() or config.is_symlink():
        return False
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    configured_root = str(data.get("root") or "").strip()
    if not configured_root or Path(configured_root).expanduser().resolve() != root:
        return False
    configured_id = str(data.get("project_id") or "").strip()
    return not configured_id or configured_id == project_id


def _ensure_rules(meta: Path) -> None:
''',
)
replace_once(
    "src/ai_layer/core/service.py",
    '''    if local_meta.exists() and local_meta.resolve() != meta.resolve():
        symlinks = [item for item in local_meta.rglob("*") if item.is_symlink()]
        if symlinks:
            raise RuntimeError(f"Refusing to migrate symlinked AI Layer state: {symlinks[0]}")
        shutil.copytree(local_meta, meta, dirs_exist_ok=True)
''',
    '''    legacy_local_owned = _legacy_local_state_owned(local_meta, path, str(project.id))
    if legacy_local_owned and local_meta.resolve() != meta.resolve():
        symlinks = [item for item in local_meta.rglob("*") if item.is_symlink()]
        if symlinks:
            raise RuntimeError(f"Refusing to migrate symlinked AI Layer state: {symlinks[0]}")
        shutil.copytree(local_meta, meta, dirs_exist_ok=True)
''',
)
replace_once(
    "src/ai_layer/core/service.py",
    '''    if local_meta.exists() and local_meta.resolve() != meta.resolve():
        shutil.rmtree(local_meta)
''',
    '''    if legacy_local_owned and local_meta.resolve() != meta.resolve():
        shutil.rmtree(local_meta)
''',
)

replace_once(
    "src/ai_layer/core/repair.py",
    '''    destination = base / project_id
    try:
        destination.resolve().relative_to(base.expanduser().resolve())
''',
    '''    destination = base / project_id
    try:
        destination.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise RuntimeError(
            f"AI Layer machine state must be outside the registered project root: {destination}"
        )
    try:
        destination.resolve().relative_to(base.expanduser().resolve())
''',
)

replace_once(
    "src/ai_layer/skills/native_files.py",
    "from ai_layer.core.paths import project_local_path, project_mode\n",
    "from ai_layer.core.paths import project_local_path\n",
)
rewrite(
    "src/ai_layer/skills/native_files.py",
    r'''    elif scope == "project":
        if project_root is None:
            raise ValueError\("project_root is required for project native skill preflight"\)
        root = Path\(project_root\).*?            names = \[
                \(project_local_path\(root, \*parts\), name\) for parts in PROJECT_NATIVE_ROOT_PARTS
            \]
''',
    '''    elif scope == "project":
        if project_root is None:
            raise ValueError("project_root is required for project native skill preflight")
        root = Path(project_root).expanduser().resolve()
        name = native_descriptor_name(slug, project_root=root, external_scope=True)
        home_root = (home or Path.home()).expanduser()
        names = [
            (project_local_path(home_root, *parts), name)
            for parts in GLOBAL_NATIVE_ROOT_PARTS.values()
        ]
''',
)

rewrite(
    "tests/test_sync.py",
    r"def test_sync_updates_template_version_and_machine_registry\(.*?\n\ndef test_project_config_write_is_failure_atomic",
    '''def test_sync_updates_template_version_and_machine_registry(tmp_path: Path, monkeypatch):
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
    '''def test_init_commits_project_identity_before_publishing_filesystem_metadata(
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
    r"def test_init_preserves_user_owned_legacy_rule_and_uses_sparse_mcp_binding\(.*?\n\ndef test_private_init_requires_git_before_db_identity",
    '''def test_init_preserves_user_owned_legacy_rule_without_repository_bindings(
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
    r"def test_project_skill_materializes_full_content_once_in_standard_workspace\(.*?\n\ndef test_strict_private_project_skill_uses_namespaced_global_full_skill_only",
    '''def test_project_skill_materializes_namespaced_global_content_in_standard_mode(
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
    r"def test_project_native_sync_refuses_symlinked_host_root\(.*?\n\ndef test_global_native_sync_refuses_symlinked_parent",
    '''def test_project_native_sync_does_not_touch_repository_host_roots(tmp_path: Path, monkeypatch):
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
