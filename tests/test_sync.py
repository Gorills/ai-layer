from pathlib import Path

import yaml

from ai_layer.core.config import get_settings
from ai_layer.core.registry import list_registered_projects
from ai_layer.core.service import sync_project_integrations
from ai_layer.integrations.service import INTEGRATION_TEMPLATE_VERSION


def test_sync_updates_template_version_and_machine_registry(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    (project / ".ai-layer").mkdir(parents=True)
    (project / ".ai-layer" / "project.yaml").write_text(
        yaml.safe_dump({"project_id": "legacy-id", "name": "legacy", "root": str(project)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", "/stable/ai-layer-mcp")
    get_settings.cache_clear()

    result = sync_project_integrations(project)
    config = yaml.safe_load((project / ".ai-layer" / "project.yaml").read_text(encoding="utf-8"))
    assert result["template_version"] == INTEGRATION_TEMPLATE_VERSION
    assert config["integration_template_version"] == INTEGRATION_TEMPLATE_VERSION
    assert list_registered_projects()[0]["root"] == str(project.resolve())
    get_settings.cache_clear()


def test_project_config_write_is_failure_atomic(tmp_path: Path, monkeypatch):
    from ai_layer.core import service

    project = tmp_path / "project-atomic"
    meta = project / ".ai-layer"
    meta.mkdir(parents=True)
    config_file = meta / "project.yaml"
    original = "version: 1\nproject_id: old\n"
    config_file.write_text(original, encoding="utf-8")

    def fail_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(service.os, "replace", fail_replace)
    try:
        service._write_project_config(project, {"version": 1, "project_id": "new"})
    except OSError:
        pass
    else:
        raise AssertionError("replace failure must propagate")

    assert config_file.read_text(encoding="utf-8") == original
    assert not list(meta.glob("project.yaml.*.tmp"))


def test_init_commits_project_identity_before_publishing_filesystem_metadata(
    tmp_path: Path, monkeypatch
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.core import service
    from ai_layer.db.base import Base
    from ai_layer.db.models import Project

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def fail_publish(path, data):
        raise RuntimeError("simulated metadata publish failure")

    monkeypatch.setattr(service, "_write_project_config", fail_publish)
    with Session(engine) as db:
        try:
            service.init_project(db, tmp_path)
        except RuntimeError as exc:
            assert "metadata publish failure" in str(exc)
        else:
            raise AssertionError("filesystem publication failure must propagate")

    with Session(engine) as verify:
        project = verify.scalar(select(Project).where(Project.root_path == str(tmp_path.resolve())))
        assert project is not None
        assert not (tmp_path / ".ai-layer" / "project.yaml").exists()


def test_init_refuses_symlinked_ai_layer_state_directory(tmp_path: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from ai_layer.core import service
    from ai_layer.db.base import Base

    outside = tmp_path.parent / "outside-ai-layer-state"
    outside.mkdir()
    (tmp_path / ".ai-layer").symlink_to(outside, target_is_directory=True)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        try:
            service.init_project(db, tmp_path)
        except RuntimeError as exc:
            assert "symlink" in str(exc).lower()
        else:
            raise AssertionError("symlinked .ai-layer directory must be rejected")

    assert list(outside.iterdir()) == []


def test_manual_scan_detects_embedding_drift_and_reembeds_decisions(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from ai_layer.core import service

    project = SimpleNamespace(id="project-id", root_path=str(tmp_path))
    monkeypatch.setattr(service, "require_initialized", lambda path: None)
    monkeypatch.setattr(service, "get_project", lambda db, path: project)
    monkeypatch.setattr(
        service,
        "load_scan_metadata",
        lambda project: {"embedding": {"provider": "fastembed", "model": "old", "dimensions": 384}},
    )
    monkeypatch.setattr(service, "embedding_state_matches", lambda project: False)
    monkeypatch.setattr(service, "scanner_state_matches", lambda project: True)
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda db, project: {
            "verified": 0,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "verified_categories": [],
            "verified_subsystems": 0,
            "overview_verified": False,
            "baseline_ready": False,
            "onboarding_recommended": True,
        },
    )

    class Lock:
        def __enter__(self):
            return {"waited": False}

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service, "project_refresh_lock", lambda path: Lock())
    calls = []
    stats = SimpleNamespace(
        files=1,
        knowledge_items=2,
        languages={"python": 1},
        dependencies={},
        selected_skills=["backend"],
    )

    def fake_scan(db, p, root, *, reason, reembed_decisions=False, force_reparse=False):
        calls.append((reason, reembed_decisions, force_reparse))
        return stats, {"scanned_at": "now", "reason": reason}, 1

    monkeypatch.setattr(service, "scan_until_stable", fake_scan)
    result = service.scan_registered_project(SimpleNamespace(), tmp_path)

    assert calls == [("embedding_configuration_changed", True, False)]
    assert result["reason"] == "embedding_configuration_changed"
    assert result["raw_source_semantic_index"] is False
    assert result["knowledge_state"]["baseline_ready"] is False
    assert result["next_step"]["action"] == "project_knowledge_onboarding"


def test_manual_scan_without_embedding_drift_keeps_manual_reason(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from ai_layer.core import service

    project = SimpleNamespace(id="project-id", root_path=str(tmp_path))
    monkeypatch.setattr(service, "require_initialized", lambda path: None)
    monkeypatch.setattr(service, "get_project", lambda db, path: project)
    monkeypatch.setattr(
        service,
        "load_scan_metadata",
        lambda project: {"embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384}},
    )
    monkeypatch.setattr(service, "embedding_state_matches", lambda project: True)
    monkeypatch.setattr(service, "scanner_state_matches", lambda project: True)
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda db, project: {
            "verified": 0,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "verified_categories": [],
            "verified_subsystems": 0,
            "overview_verified": False,
            "baseline_ready": False,
            "onboarding_recommended": True,
        },
    )

    class Lock:
        def __enter__(self):
            return {"waited": False}

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service, "project_refresh_lock", lambda path: Lock())
    calls = []
    stats = SimpleNamespace(
        files=1, knowledge_items=1, languages={}, dependencies={}, selected_skills=[]
    )

    def fake_scan(db, p, root, *, reason, reembed_decisions=False, force_reparse=False):
        calls.append((reason, reembed_decisions, force_reparse))
        return stats, {"scanned_at": "now", "reason": reason}, 1

    monkeypatch.setattr(service, "scan_until_stable", fake_scan)
    result = service.scan_registered_project(SimpleNamespace(), tmp_path)

    assert calls == [("manual_scan", False, False)]
    assert result["reason"] == "manual_scan"
    assert result["next_step"]["action"] == "project_knowledge_onboarding"


def test_init_rejects_nested_registered_project(tmp_path: Path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project
    from ai_layer.core.service import init_project

    home = tmp_path / "home-overlap-init"
    parent = tmp_path / "repo"
    child = parent / "main"
    home.mkdir()
    child.mkdir(parents=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    class FakeDB:
        def scalar(self, *args, **kwargs):
            raise AssertionError("DB must not be touched after overlap is detected")

    try:
        register_project(parent, "p-parent", "parent", mode="strict-private", provenance="forbid")
        import pytest

        with pytest.raises(RuntimeError, match="overlaps an already registered project"):
            init_project(FakeDB(), child)
    finally:
        get_settings.cache_clear()


def test_remove_accidental_nested_project_preserves_parent_and_user_files(
    tmp_path: Path, monkeypatch
):
    from types import SimpleNamespace

    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import (
        get_registered_project,
        overlapping_registered_projects,
        register_project,
    )
    from ai_layer.core.service import remove_project_registration

    home = tmp_path / "home-remove-nested"
    parent = tmp_path / "food"
    child = parent / "main"
    child.mkdir(parents=True)
    user_file = child / "app.py"
    user_file.write_text("print('keep me')\n", encoding="utf-8")
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    register_project(child, "p-child", "main", mode="standard", provenance="allow")
    local_meta = child / ".ai-layer"
    local_meta.mkdir()
    (local_meta / "project.yaml").write_text(
        f"version: 2\nproject_id: p-child\nname: main\nroot: {child.resolve()}\nmode: standard\nprovenance: allow\n",
        encoding="utf-8",
    )
    register_project(parent, "p-parent", "food", mode="strict-private", provenance="forbid")

    project_row = SimpleNamespace(id="p-child", root_path=str(child.resolve()))

    class Result:
        rowcount = 1

    class FakeDb:
        def scalar(self, statement):
            return project_row

        def execute(self, statement):
            return Result()

        def commit(self):
            return None

    try:
        assert overlapping_registered_projects(parent)
        result = remove_project_registration(FakeDb(), child)
        assert result["removed"] is True
        assert not local_meta.exists()
        assert user_file.read_text(encoding="utf-8") == "print('keep me')\n"
        assert get_registered_project(child) is None
        assert get_registered_project(parent) is not None
        assert overlapping_registered_projects(parent) == []
    finally:
        get_settings.cache_clear()


def test_remove_nested_standard_project_does_not_remove_parent_strict_private_git_guard(
    tmp_path: Path, monkeypatch
):
    import subprocess
    from types import SimpleNamespace

    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import get_registered_project, register_project
    from ai_layer.core.service import remove_project_registration
    from ai_layer.privacy.service import install_git_privacy_guard

    home = tmp_path / "home-parent-guard"
    parent = tmp_path / "food"
    child = parent / "main"
    child.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(parent)], check=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    register_project(child, "p-child", "main", mode="standard", provenance="allow")
    child_meta = child / ".ai-layer"
    child_meta.mkdir()
    (child_meta / "project.yaml").write_text(
        f"version: 2\nproject_id: p-child\nname: main\nroot: {child.resolve()}\nmode: standard\nprovenance: allow\n",
        encoding="utf-8",
    )

    register_project(parent, "p-parent", "food", mode="strict-private", provenance="forbid")
    parent_meta = home / ".ai-layer" / "projects" / "p-parent"
    parent_meta.mkdir(parents=True)
    (parent_meta / "project.yaml").write_text(
        f"version: 2\nproject_id: p-parent\nname: food\nroot: {parent.resolve()}\nmode: strict-private\nprovenance: forbid\n",
        encoding="utf-8",
    )
    guard = install_git_privacy_guard(parent)
    assert guard["ready"] is True
    before = subprocess.run(
        ["git", "-C", str(parent), "config", "--local", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert before == str((parent_meta / "git-hooks").resolve())

    project_row = SimpleNamespace(id="p-child", root_path=str(child.resolve()))

    class Result:
        rowcount = 1

    class FakeDb:
        def scalar(self, statement):
            return project_row

        def execute(self, statement):
            return Result()

        def commit(self):
            return None

    try:
        remove_project_registration(FakeDb(), child)
        after = subprocess.run(
            ["git", "-C", str(parent), "config", "--local", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert after == before
        assert get_registered_project(parent) is not None
        assert get_registered_project(child) is None
    finally:
        get_settings.cache_clear()


def test_init_preserves_user_owned_legacy_rule_and_uses_sparse_mcp_binding(
    tmp_path: Path, monkeypatch
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.core import service
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
    assert (project_root / ".cursor" / "mcp.json").exists()
    assert (project_root / ".agents" / "mcp_config.json").exists()
    get_settings.cache_clear()


def test_private_init_requires_git_before_db_identity(tmp_path: Path, monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.core import service
    from ai_layer.db.base import Base
    from ai_layer.db.models import Project

    home = tmp_path / "home-private-preflight"
    project_root = tmp_path / "private-non-git"
    home.mkdir()
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        try:
            service.init_project(db, project_root, private=True)
        except RuntimeError as exc:
            assert "requires an existing Git repository" in str(exc)
        else:
            raise AssertionError("strict-private init without Git must fail closed")

    with Session(engine) as verify:
        assert (
            verify.scalar(select(Project).where(Project.root_path == str(project_root.resolve())))
            is None
        )
    assert not (project_root / ".ai-layer").exists()
    get_settings.cache_clear()


def test_external_init_keeps_repository_zero_footprint_without_privacy_policy(
    tmp_path: Path, monkeypatch
):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from ai_layer.core import service
    from ai_layer.core.paths import project_meta_dir, project_mode, project_provenance
    from ai_layer.db.base import Base

    home = tmp_path / "home-external"
    project_root = tmp_path / "external-project"
    home.mkdir()
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            service.init_project(db, project_root, external=True)
        assert project_mode(project_root) == "external"
        assert project_provenance(project_root) == "allow"
        assert project_meta_dir(project_root).is_relative_to(home / ".ai-layer")
        assert not (project_root / ".ai-layer").exists()
        for relative in (
            "AGENTS.md",
            "CLAUDE.md",
            ".cursor/rules/ai-layer.mdc",
            ".mcp.json",
            ".codex/config.toml",
            ".agents/rules/ai-layer.md",
        ):
            assert not (project_root / relative).exists()
    finally:
        get_settings.cache_clear()
