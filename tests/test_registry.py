import json
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import list_registered_projects, register_project, unregister_project


def test_machine_registry_survives_without_database(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    register_project(project, "p-1", "demo")
    register_project(project, "p-1", "demo-renamed")

    items = list_registered_projects()
    assert len(items) == 1
    assert items[0]["root"] == str(project.resolve())
    assert items[0]["name"] == "demo-renamed"
    payload = json.loads((home / ".ai-layer" / "projects.json").read_text())
    assert payload["version"] == 4
    assert items[0]["mode"] == "standard"
    assert items[0]["provenance"] == "allow"
    get_settings.cache_clear()


def test_unregister_project_removes_only_target_and_is_idempotent(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    first = tmp_path / "first"
    second = tmp_path / "second"
    home.mkdir()
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()

    register_project(first, "p-1", "first")
    register_project(second, "p-2", "second")

    result = unregister_project(first)
    assert result == {"root": str(first.resolve()), "removed": 1, "forgotten": True}
    assert [item["root"] for item in list_registered_projects()] == [str(second.resolve())]

    result = unregister_project(first)
    assert result["removed"] == 0
    assert [item["root"] for item in list_registered_projects()] == [str(second.resolve())]
    get_settings.cache_clear()


def test_registry_persists_strict_private_mode_and_provenance(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project-private"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "private-1", "private", mode="strict-private", provenance="forbid"
        )
        item = list_registered_projects()[0]
        assert item["mode"] == "strict-private"
        assert item["provenance"] == "forbid"
    finally:
        get_settings.cache_clear()


def test_registry_corruption_fails_closed(tmp_path: Path, monkeypatch):
    from ai_layer.core.paths import project_meta_dir, project_mode
    from ai_layer.core.registry import RegistryCorruptError

    home = tmp_path / "home-corrupt"
    project = tmp_path / "private-corrupt"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "private-corrupt", "private", mode="strict-private", provenance="forbid"
        )
        get_settings().projects_registry_file.write_text("{not-json", encoding="utf-8")

        try:
            project_mode(project)
        except RegistryCorruptError:
            pass
        else:
            raise AssertionError("corrupt registry must not fall back to standard mode")

        try:
            project_meta_dir(project)
        except RegistryCorruptError:
            pass
        else:
            raise AssertionError("corrupt registry must not place state inside the repository")
    finally:
        get_settings.cache_clear()


def test_registry_serializes_concurrent_updates(tmp_path: Path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    home = tmp_path / "home-concurrent"
    home.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    projects = [tmp_path / f"project-{index}" for index in range(30)]
    for project in projects:
        project.mkdir()

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda item: register_project(item, item.name, item.name), projects))
        roots = {item["root"] for item in list_registered_projects()}
        assert roots == {str(project.resolve()) for project in projects}
    finally:
        get_settings.cache_clear()


def test_missing_registry_recovers_existing_strict_private_state(tmp_path: Path, monkeypatch):
    from ai_layer.core.paths import project_meta_dir, project_mode

    home = tmp_path / "home-recover"
    project = tmp_path / "private-recover"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "private-recover", "private", mode="strict-private", provenance="forbid"
        )
        meta = project_meta_dir(project)
        meta.mkdir(parents=True)
        (meta / "project.yaml").write_text(
            "\n".join(
                [
                    "version: 2",
                    "project_id: private-recover",
                    "name: private",
                    f"root: {project.resolve()}",
                    "mode: strict-private",
                    "provenance: forbid",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        get_settings().projects_registry_file.unlink()

        assert project_mode(project) == "strict-private"
        assert project_meta_dir(project) == meta
        assert project_meta_dir(project) != project / ".ai-layer"
    finally:
        get_settings.cache_clear()


def test_registry_invalid_privacy_metadata_fails_closed(tmp_path: Path, monkeypatch):
    from ai_layer.core.paths import project_mode
    from ai_layer.core.registry import RegistryCorruptError

    home = tmp_path / "home-invalid-mode"
    project = tmp_path / "project-invalid-mode"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        registry = get_settings().projects_registry_file
        registry.parent.mkdir(parents=True)
        registry.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": [
                        {
                            "root": str(project.resolve()),
                            "project_id": "private-id",
                            "mode": "unexpected-mode",
                            "provenance": "allow",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        try:
            project_mode(project)
        except RegistryCorruptError:
            pass
        else:
            raise AssertionError("invalid registry privacy metadata must fail closed")
    finally:
        get_settings.cache_clear()


def test_overlapping_registered_projects_detects_parent_and_child(tmp_path: Path, monkeypatch):
    from ai_layer.core.registry import overlapping_registered_projects

    home = tmp_path / "home-overlap"
    parent = tmp_path / "repo"
    child = parent / "main"
    sibling = tmp_path / "other"
    home.mkdir()
    child.mkdir(parents=True)
    sibling.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(parent, "p-parent", "parent", mode="strict-private", provenance="forbid")
        register_project(sibling, "p-other", "other")
        assert [item["root"] for item in overlapping_registered_projects(child)] == [
            str(parent.resolve())
        ]
        assert overlapping_registered_projects(parent) == []
    finally:
        get_settings.cache_clear()


def test_unregister_strict_private_is_durable_against_external_state(tmp_path: Path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import get_registered_project, register_project, unregister_project

    home = tmp_path / "home-durable-unregister"
    project = tmp_path / "repo-private"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "p-private", "repo-private", mode="strict-private", provenance="forbid"
        )
        state = home / ".ai-layer" / "projects" / "p-private"
        state.mkdir(parents=True)
        (state / "project.yaml").write_text(
            f"version: 2\nproject_id: p-private\nname: repo-private\nroot: {project.resolve()}\nmode: strict-private\nprovenance: forbid\n",
            encoding="utf-8",
        )
        assert get_registered_project(project) is not None
        result = unregister_project(project)
        assert result["forgotten"] is True
        assert get_registered_project(project) is None
    finally:
        get_settings.cache_clear()


def test_explicit_register_clears_forgotten_root(tmp_path: Path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import get_registered_project, register_project, unregister_project

    home = tmp_path / "home-reregister"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(project, "p-1", "repo")
        unregister_project(project)
        assert get_registered_project(project) is None
        register_project(project, "p-1", "repo")
        assert get_registered_project(project) is not None
    finally:
        get_settings.cache_clear()


def test_registry_invalid_utf8_fails_closed(tmp_path: Path, monkeypatch):
    from ai_layer.core.paths import project_mode
    from ai_layer.core.registry import RegistryCorruptError

    home = tmp_path / "home-invalid-utf8"
    project = tmp_path / "private-invalid-utf8"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "private-invalid-utf8", "private", mode="strict-private", provenance="forbid"
        )
        get_settings().projects_registry_file.write_bytes(b"\xff\xfe")
        with __import__("pytest").raises(RegistryCorruptError):
            project_mode(project)
    finally:
        get_settings.cache_clear()
