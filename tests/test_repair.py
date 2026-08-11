from __future__ import annotations

import subprocess
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import get_registered_project, register_project
from ai_layer.core.repair import repair_project, repair_registered_projects


def _project_yaml(root: Path, project_id: str, *, mode: str, provenance: str) -> str:
    return (
        "version: 2\n"
        f"project_id: {project_id}\n"
        f"name: {root.name}\n"
        f"root: {root.resolve()}\n"
        f"mode: {mode}\n"
        f"provenance: {provenance}\n"
    )


def test_repair_auto_detaches_nested_registration_and_archives_ai_state(
    tmp_path: Path, monkeypatch
):
    home = tmp_path / "home"
    parent = tmp_path / "food"
    child = parent / "main"
    child.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(parent)], check=True)
    user_file = child / "app.py"
    user_file.write_text("print('keep')\n", encoding="utf-8")
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(child, "p-child", "main", mode="standard", provenance="allow")
        local = child / ".ai-layer"
        local.mkdir()
        (local / "project.yaml").write_text(
            _project_yaml(child, "p-child", mode="standard", provenance="allow"), encoding="utf-8"
        )
        # A bridge produced by the accidental child init must be removed from the parent's tree.
        bridge = child / ".cursor" / "rules" / "ai-layer.mdc"
        bridge.parent.mkdir(parents=True)
        bridge.write_text(
            "---\ndescription: Mandatory Local AI Development Layer workflow\n---\n",
            encoding="utf-8",
        )

        register_project(parent, "p-parent", "food", mode="strict-private", provenance="forbid")
        external = get_settings().projects_state_dir / "p-parent"
        external.mkdir(parents=True)
        (external / "project.yaml").write_text(
            _project_yaml(parent, "p-parent", mode="strict-private", provenance="forbid"),
            encoding="utf-8",
        )

        result = repair_registered_projects(sync=True)
        assert result["nested_detached"] == 1
        assert result["projects_healthy"] == 1
        assert get_registered_project(child) is None
        assert get_registered_project(parent) is not None
        assert not local.exists()
        assert not bridge.exists()
        assert user_file.read_text(encoding="utf-8") == "print('keep')\n"
        archived = list(
            (get_settings().home / "recovery" / "nested-projects").glob(
                "*/local-state/project.yaml"
            )
        )
        assert len(archived) == 1
        assert "p-child" in archived[0].read_text(encoding="utf-8")
    finally:
        get_settings.cache_clear()


def test_repair_moves_verified_strict_private_local_residue_out_of_repository(
    tmp_path: Path, monkeypatch
):
    home = tmp_path / "home"
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(root, "p-private", "repo", mode="strict-private", provenance="forbid")
        external = get_settings().projects_state_dir / "p-private"
        external.mkdir(parents=True)
        (external / "project.yaml").write_text(
            _project_yaml(root, "p-private", mode="strict-private", provenance="forbid"),
            encoding="utf-8",
        )
        local = root / ".ai-layer"
        local.mkdir()
        (local / "project.yaml").write_text(
            _project_yaml(root, "p-private", mode="strict-private", provenance="forbid"),
            encoding="utf-8",
        )

        result = repair_project(root, sync=False)
        assert result["ok"] is True
        assert not local.exists()
        assert (external / "project.yaml").exists()
        assert result["archived_state"]
    finally:
        get_settings.cache_clear()


def test_repair_strict_private_does_not_block_on_large_clean_tracked_lockfile(
    tmp_path: Path, monkeypatch
):
    home = tmp_path / "home"
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    lockfile = root / "package-lock.json"
    lockfile.write_text(
        '{"lockfileVersion": 3, "packages": {"x": "' + ("a" * 1_050_000) + '"}}\n', encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(root), "add", "package-lock.json"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(root, "p-private", "repo", mode="strict-private", provenance="forbid")
        external = get_settings().projects_state_dir / "p-private"
        external.mkdir(parents=True)
        (external / "project.yaml").write_text(
            _project_yaml(root, "p-private", mode="strict-private", provenance="forbid"),
            encoding="utf-8",
        )
        result = repair_project(root, sync=False)
        assert result["ok"] is True
        assert result["manual"] == []
        assert result["footprint"]["tracked_unscannable"] == []
    finally:
        get_settings.cache_clear()


def test_repair_reports_user_owned_provenance_without_rewriting_it(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    source = root / "app.py"
    original = "# Generated by ChatGPT\nprint('user code')\n"
    source.write_text(original, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)

    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(root, "p-private", "repo", mode="strict-private", provenance="forbid")
        external = get_settings().projects_state_dir / "p-private"
        external.mkdir(parents=True)
        (external / "project.yaml").write_text(
            _project_yaml(root, "p-private", mode="strict-private", provenance="forbid"),
            encoding="utf-8",
        )

        result = repair_project(root, sync=False)
        assert result["ok"] is False
        assert any("tracked files contain" in item for item in result["manual"])
        assert source.read_text(encoding="utf-8") == original
    finally:
        get_settings.cache_clear()


def test_repair_refuses_nested_symlink_inside_ai_state(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    parent = tmp_path / "food"
    child = parent / "main"
    outside = tmp_path / "outside"
    child.mkdir(parents=True)
    outside.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(child, "p-child", "main", mode="standard", provenance="allow")
        local = child / ".ai-layer"
        local.mkdir()
        (local / "project.yaml").write_text(
            _project_yaml(child, "p-child", mode="standard", provenance="allow"), encoding="utf-8"
        )
        (local / "unsafe-link").symlink_to(outside, target_is_directory=True)
        register_project(parent, "p-parent", "food", mode="strict-private", provenance="forbid")

        result = repair_registered_projects(sync=False)
        assert result["ok"] is False
        assert result["nested_detached"] == 0
        assert get_registered_project(child) is not None
        assert local.exists()
        assert any(
            "symlinked AI Layer project state" in item["error"] for item in result["unresolved"]
        )
    finally:
        get_settings.cache_clear()
