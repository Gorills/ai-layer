from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match in {path}, found {count}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_regex(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"expected exactly one regex match in {path}: {pattern[:120]!r}")
    file.write_text(updated, encoding="utf-8")


replace_once(
    "src/ai_layer/core/paths.py",
    '''def project_meta_dir(root: str | Path) -> Path:
    resolved = Path(root).expanduser().resolve()
    item = get_registered_project(resolved)
    if item and item.get("mode") in {"external", "strict-private"}:
        project_id = str(item.get("project_id") or "").strip()
        if not project_id:
            raise RuntimeError(f"External-state project lacks registry project_id: {resolved}")
        base = get_settings().home / "projects"
        if base.is_symlink():
            raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
        base.mkdir(parents=True, exist_ok=True)
        return _safe_child(base, project_id)
    return project_local_path(resolved, ".ai-layer")
''',
    '''def project_meta_dir(root: str | Path) -> Path:
    resolved = Path(root).expanduser().resolve()
    item = get_registered_project(resolved)
    if item:
        project_id = str(item.get("project_id") or "").strip()
        if project_id:
            base = get_settings().home / "projects"
            if base.is_symlink():
                raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
            base.mkdir(parents=True, exist_ok=True)
            return _safe_child(base, project_id)
        if item.get("mode") in {"external", "strict-private"}:
            raise RuntimeError(f"External-state project lacks registry project_id: {resolved}")
    return project_local_path(resolved, ".ai-layer")
''',
)

replace_once(
    "src/ai_layer/core/registry.py",
    '    """Recover external-state project authority if registry entries are lost."""\n',
    '    """Recover machine-side project authority if registry entries are lost."""\n',
)
replace_once(
    "src/ai_layer/core/registry.py",
    '        if mode not in {"external", "strict-private"}:\n            continue\n',
    '        if mode not in PROJECT_MODES:\n            continue\n',
)

replace_once(
    "src/ai_layer/skills/native_sync.py",
    '''from ai_layer.skills.native_files import (
    GLOBAL_NATIVE_ROOT_PARTS,
    PROJECT_NATIVE_ROOT_PARTS,
    global_native_roots,
    sync_native_root,
)
''',
    '''from ai_layer.skills.native_files import (
    GLOBAL_NATIVE_ROOT_PARTS,
    global_native_roots,
    sync_native_root,
)
''',
)
replace_regex(
    "src/ai_layer/skills/native_sync.py",
    r"def sync_project_native_skills\(.*?\n\ndef sync_native_after_skill_change",
    '''def sync_project_native_skills(project_root: str | Path, *, home: Path | None = None) -> dict:
    root = Path(project_root).expanduser().resolve()
    mode = project_mode(root)
    project_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    desired, validation = _project_skill_descriptors(root, external_scope=True)
    home_root = (home or Path.home()).expanduser()
    results = {
        host: sync_native_root(
            home_root, *parts, desired=desired, scope="project", project_key=project_key
        )
        for host, parts in GLOBAL_NATIVE_ROOT_PARTS.items()
    }
    return {
        "mode": mode,
        "repository_writes": False,
        "scope": "namespaced-global-zero-footprint",
        "descriptors": sorted(desired),
        "activation_payload": "full-authoritative-skill",
        "validation": validation,
        "sync": results,
    }


def sync_native_after_skill_change''',
)

replace_once(
    "src/ai_layer/core/service.py",
    '''from ai_layer.integrations.service import (
    INTEGRATION_TEMPLATE_VERSION,
    install_project_integrations,
    preflight_project_integrations,
    remove_project_integrations,
)
''',
    '''from ai_layer.integrations.service import (
    INTEGRATION_TEMPLATE_VERSION,
    remove_project_integrations,
)
''',
)
replace_once(
    "src/ai_layer/core/service.py",
    '''        if mode in {"external", "strict-private"}:
            remove_project_integrations(path)
            result = {
                "template_version": INTEGRATION_TEMPLATE_VERSION,
                "ai_layer_version": __version__,
                "mode": mode,
                "repository_writes": False,
                "native_skills": sync_project_native_skills(path),
            }
            if mode == "strict-private":
                guard = install_git_privacy_guard(path)
                if not guard.get("ready", False):
                    raise RuntimeError(
                        f"Strict-private Git privacy guard is not ready: {guard.get('reason') or guard}"
                    )
                result["git_guard"] = guard
            else:
                remove_git_privacy_guard(path)
        else:
            result = install_project_integrations(path)
''',
    '''        remove_project_integrations(path)
        result = {
            "template_version": INTEGRATION_TEMPLATE_VERSION,
            "ai_layer_version": __version__,
            "mode": mode,
            "repository_writes": False,
            "native_skills": sync_project_native_skills(path),
        }
        if mode == "strict-private":
            guard = install_git_privacy_guard(path)
            if not guard.get("ready", False):
                raise RuntimeError(
                    f"Strict-private Git privacy guard is not ready: {guard.get('reason') or guard}"
                )
            result["git_guard"] = guard
        else:
            remove_git_privacy_guard(path)
''',
)
replace_regex(
    "src/ai_layer/core/service.py",
    r"    # Reject deterministic integration/privacy conflicts before creating durable project identity\.\n    # Later filesystem I/O can still fail, so PostgreSQL remains the recovery anchor after this gate\.\n    if mode == \"strict-private\":.*?    elif mode == \"standard\":\n        preflight_project_integrations\(path\)\n",
    '''    # Strict-private alone needs a repository-level precondition because it installs a Git guard.
    # Standard and external attachment are zero-footprint and have no repository integration targets.
    if mode == "strict-private" and not is_git_repository(path):
        raise RuntimeError(
            "Strict-private initialization requires an existing Git repository so privacy "
            "enforcement can fail closed. Initialize Git first, then retry."
        )
''',
)
replace_once(
    "src/ai_layer/core/service.py",
    '''    # Registry is the authority that selects local vs external state. Publish it before resolving
    # project_meta_dir, then migrate any existing local state if this is a standard -> private move.
''',
    '''    # Registry publishes durable project identity before resolving machine-side state. Existing
    # repository-local state from older standard installs is copied out before repository cleanup.
''',
)
replace_regex(
    "src/ai_layer/core/service.py",
    r"    if \(\n        mode in \{\"external\", \"strict-private\"\}\n        and local_meta\.exists\(\)\n        and local_meta\.resolve\(\) != meta\.resolve\(\)\n    \):\n",
    "    if local_meta.exists() and local_meta.resolve() != meta.resolve():\n",
)
replace_regex(
    "src/ai_layer/core/service.py",
    r"    if mode in \{\"external\", \"strict-private\"\}:\n        remove_project_integrations\(path\).*?    else:\n        install_project_integrations\(path\)\n    register_project\(",
    '''    remove_project_integrations(path)
    sync_project_native_skills(path)
    if local_meta.exists() and local_meta.resolve() != meta.resolve():
        shutil.rmtree(local_meta)
    if mode == "strict-private":
        guard = install_git_privacy_guard(path)
        if not guard.get("ready", False):
            raise RuntimeError(
                f"Strict-private Git privacy guard is not ready: {guard.get('reason') or guard}"
            )
    else:
        remove_git_privacy_guard(path)
    register_project(''',
)

replace_regex(
    "src/ai_layer/core/repair.py",
    r"def _archive_external_local_residue\(root: Path\) -> list\[str\]:.*?\n\ndef _archive_overlapping_state",
    '''def _migrate_legacy_local_state(root: Path) -> dict:
    """Move verified legacy repository-local state to canonical machine-side project storage."""
    local_meta = project_local_path(root, ".ai-layer")
    if not local_meta.exists() and not local_meta.is_symlink():
        return {"migrated": False, "destination": None, "archived": []}
    project_id = _project_id(root)
    if not project_id:
        raise RuntimeError(
            f"Registered project lacks project_id; refusing to move legacy state: {root}"
        )
    if not _validated_owned_state(local_meta, root, project_id):
        return {"migrated": False, "destination": None, "archived": []}

    base = get_settings().projects_state_dir
    if base.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
    destination = base / project_id
    try:
        destination.resolve().relative_to(base.expanduser().resolve())
    except ValueError as exc:
        raise RuntimeError(f"Unsafe external AI Layer project state path: {destination}") from exc

    if destination.exists() or destination.is_symlink():
        if not _validated_owned_state(destination, root, project_id):
            raise RuntimeError(f"Canonical project state is not safely owned: {destination}")
        recovery = _recovery_dir(root, project_id, "legacy-local-state")
        archived = _archive_dir(local_meta, recovery, "local-state")
        return {"migrated": False, "destination": str(destination), "archived": [archived]}

    base.mkdir(parents=True, exist_ok=True)
    shutil.move(str(local_meta), str(destination))
    try:
        os.chmod(destination, 0o700)
    except OSError:
        pass
    return {"migrated": True, "destination": str(destination), "archived": []}


def _archive_overlapping_state''',
)
replace_regex(
    "src/ai_layer/core/repair.py",
    r"        mode = project_mode\(path\)\n        if mode in \{\"external\", \"strict-private\"\}:.*?        if sync:\n",
    '''        mode = project_mode(path)
        layout = _migrate_legacy_local_state(path)
        if layout.get("migrated"):
            result["actions"].append("migrated legacy local .ai-layer state to machine storage")
            result["state_destination"] = layout.get("destination")
        if layout.get("archived"):
            result["actions"].append("archived duplicate legacy local .ai-layer state")
            result["archived_state"] = layout["archived"]

        remove_project_integrations(path)
        result["actions"].append("removed repository-local AI Layer integration residue")
        if mode == "strict-private":
            guard = install_git_privacy_guard(path)
            result["git_guard"] = guard
            if not guard.get("ready", False):
                result["manual"].append(
                    f"Git privacy guard conflict: {guard.get('reason') or guard}"
                )
        else:
            remove_git_privacy_guard(path)
        if sync:
''',
)

replace_once("src/ai_layer/integrations/status.py", "def _external_status(\n", "def _global_project_status(\n")
replace_once(
    "src/ai_layer/integrations/status.py",
    '    if mode in {"external", "strict-private"}:\n        return _external_status(\n',
    '    if mode in {"standard", "external", "strict-private"}:\n        return _global_project_status(\n',
)
replace_once(
    "src/ai_layer/integrations/versioning.py",
    "INTEGRATION_TEMPLATE_VERSION = 23\n",
    "INTEGRATION_TEMPLATE_VERSION = 24\n",
)

replace_once(
    "src/ai_layer/cli/commands/operations.py",
    '        help="Use zero-footprint external state and forbid AI-development provenance.",\n',
    '        help="Use zero-footprint machine state and forbid AI-development provenance.",\n',
)
replace_once(
    "src/ai_layer/cli/commands/operations.py",
    '        help="Use zero-footprint external state without enabling provenance restrictions.",\n',
    '        help="Legacy explicit zero-footprint alias; standard init is already zero-footprint.",\n',
)
replace_once(
    "src/ai_layer/cli/commands/operations.py",
    '    """Register a project using standard adapters or zero-footprint external attachment."""\n',
    '    """Register a project with zero repository footprint; --private adds provenance guards."""\n',
)
replace_once(
    "src/ai_layer/cli/commands/operations.py",
    '            "provenance": project_provenance(root),\n            "integration_template_version": INTEGRATION_TEMPLATE_VERSION,\n',
    '            "provenance": project_provenance(root),\n            "repository_writes": False,\n            "integration_template_version": INTEGRATION_TEMPLATE_VERSION,\n',
)

replace_once(
    "PROJECT_CHARTER.md",
    "3. **Target projects** — user repositories. AI Layer implementation is never copied into them. Standard mode may install minimal generated host bridge/native-skill files. External and strict-private modes keep managed state machine-side according to their privacy contract.\n",
    "3. **Target projects** — user repositories. AI Layer implementation and managed state are not copied into them. Standard attachment is zero-footprint and uses global host integration plus machine-side project state; strict-private adds provenance restrictions and its Git privacy guard. The legacy `external` mode remains a compatibility spelling for the same zero-footprint attachment model.\n",
)
replace_once(
    "ARCHITECTURE.md",
    "`standard` mode writes only minimal generated/reversible host bridges plus project-native descriptors for explicit project skills under the shared `.agents/skills/` convention. Global AI Layer skills stay in user-level native catalogs. `external` keeps project-specific descriptors at machine/user level and removes repository bridges while preserving normal provenance policy. `strict-private` is external attachment plus provenance prohibition and Git privacy guard. Canonical workflow snapshots and Epic state are machine/DB state and do not add source-controlled AI Layer artifacts to target repositories.\n",
    "`standard` mode is a zero-footprint attachment: project metadata/rules live under the machine AI Layer home, MCP/bootstrap delivery is global, and project-specific native skills are namespaced into user-level host catalogs. The legacy `external` mode is retained as a compatibility spelling for the same repository-clean attachment behavior. `strict-private` uses the same machine-side layout plus provenance prohibition and a Git privacy guard. Upgrade/repair migrates verified legacy `.ai-layer` state out of older standard repositories and removes only AI Layer-owned project MCP/skill residue while preserving unrelated user configuration.\n",
)
replace_once(
    "README.md",
    "External/strict-private project modes keep project-specific AI Layer state and managed skill material outside repositories according to the privacy contract.\n",
    "Standard, external and strict-private project modes keep project-specific AI Layer state and managed skill material outside repositories; strict-private additionally enforces the provenance/privacy contract.\n",
)
replace_once(
    "README.md",
    "The supported flow remains the repository's one-command installer/updater and immutable machine runtime layout. Runtime state lives under the AI Layer machine home rather than being copied into target projects.\n\nUse the CLI health/update/install commands and generated host integrations rather than manually editing runtime internals. Strict-private/external projects should continue to use the zero-footprint path supported by the installer.\n",
    "The supported flow remains the repository's one-command installer/updater and immutable machine runtime layout. Runtime state lives under the AI Layer machine home rather than being copied into target projects. Standard `ai-layer init` is zero-footprint: it registers the project, stores project state machine-side, relies on global host MCP/bootstrap delivery, and publishes project skills through namespaced user-level native catalogs.\n\nUse the CLI health/update/install commands rather than manually editing runtime internals. Upgrading AI Layer repairs registered projects automatically: verified legacy `.ai-layer` state is moved to machine storage and AI Layer-owned project MCP/skill residue is removed. `--private` keeps the same zero-footprint layout and additionally enables provenance restrictions plus the Git privacy guard; `--external` remains a compatibility alias for explicit zero-footprint attachment.\n",
)
replace_once(
    "CURRENT_STATE.md",
    "## Project Map and search\n",
    '''## Target-project attachment

Standard `ai-layer init` is zero-footprint. Registered project metadata/rules live under `~/.ai-layer/projects/<project-id>/`, supported hosts use the global MCP/bootstrap installation, and project-specific native skills are published into namespaced user-level host catalogs rather than `.agents/skills` / `.claude/skills` inside the repository. `--external` remains a compatibility spelling for the same repository-clean attachment model. `--private` uses the same layout but additionally forbids AI-development provenance and installs the strict Git privacy guard.

Machine upgrade/repair migrates verified legacy standard `.ai-layer` state into the canonical machine-side directory, removes only AI Layer-owned project MCP/native-skill residue, and preserves unrelated user configuration. Integration template contract v24 records this physical-delivery change.

## Project Map and search
''',
)

replace_once(
    "tests/test_integrations.py",
    '    assert state["template_version"] == INTEGRATION_TEMPLATE_VERSION\n    assert all(provider["ready"] for provider in state["providers"].values())\n',
    '    assert state["template_version"] == INTEGRATION_TEMPLATE_VERSION\n    assert state["repository_writes"] is False\n    assert all(provider["ready"] for provider in state["providers"].values())\n',
)
replace_regex(
    "tests/test_integrations.py",
    r"def test_codex_project_disabled_mcp_is_not_masked_by_global_config\(.*?\n\ndef test_codex_status_reads_active_codex_home",
    '''def test_codex_legacy_project_disabled_mcp_does_not_override_global_config(
    tmp_path: Path, monkeypatch
):
    _home, project = _installed_health_fixture(tmp_path, monkeypatch)
    config = project / ".codex" / "config.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("args = []\\n", "enabled = false\\nargs = []\\n", 1), encoding="utf-8"
    )

    state = integration_status(project)
    codex = state["providers"]["codex"]
    assert state["mode"] == "standard"
    assert state["repository_writes"] is False
    assert codex["ready"] is True
    assert codex["configuration_ready"] is True
    assert codex.get("mcp_reason") != "mcp_disabled"
    assert state["ready"] is True
    get_settings.cache_clear()


def test_codex_status_reads_active_codex_home''',
)

integration_marker = "def test_remove_project_integrations_preserves_user_content(tmp_path: Path):\n"
integration_test = '''def test_standard_sync_removes_legacy_repository_bindings(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core import service as project_service
    from ai_layer.core.registry import register_project

    home = tmp_path / "home"
    project = tmp_path / "standard-project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    monkeypatch.setenv("AI_LAYER_MCP_EXECUTABLE", str(home / "bin" / "ai-layer-mcp"))
    (home / "bin").mkdir()
    (home / "bin" / "ai-layer-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
    (home / "bin" / "ai-layer-mcp").chmod(0o755)
    get_settings.cache_clear()
    try:
        register_project(project, "standard-id", "standard", mode="standard", provenance="allow")
        state_dir = home / ".ai-layer" / "projects" / "standard-id"
        state_dir.mkdir(parents=True)
        (state_dir / "project.yaml").write_text(
            "version: 2\n"
            "project_id: standard-id\n"
            "name: standard\n"
            f"root: {project.resolve()}\n"
            "mode: standard\n"
            "provenance: allow\n",
            encoding="utf-8",
        )
        install_global_integrations()
        install_project_integrations(project)
        assert (project / ".cursor" / "mcp.json").exists()
        assert (project / ".mcp.json").exists()

        monkeypatch.setattr(
            project_service,
            "sync_project_native_skills",
            lambda _root: {"repository_writes": False, "scope": "namespaced-global-zero-footprint"},
        )
        synced = project_service.sync_project_integrations(project)

        assert synced["mode"] == "standard"
        assert synced["repository_writes"] is False
        for rel in [".mcp.json", ".codex/config.toml", ".agents/mcp_config.json"]:
            assert not (project / rel).exists(), rel
        cursor = project / ".cursor" / "mcp.json"
        if cursor.exists():
            assert "ai-layer" not in json.loads(cursor.read_text(encoding="utf-8")).get(
                "mcpServers", {}
            )
        state = integration_status(project)
        assert state["mode"] == "standard"
        assert state["repository_writes"] is False
        assert state["ready"] is True
    finally:
        get_settings.cache_clear()


'''
replace_once("tests/test_integrations.py", integration_marker, integration_test + integration_marker)

privacy_marker = "def test_privacy_check_blocks_provenance_but_allows_legitimate_ai_domain_content(\n"
privacy_test = '''def test_standard_state_is_external_to_repository(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "standard-project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(project, "standard-project-id", "standard", mode="standard", provenance="allow")
        meta = project_meta_dir(project)
        assert meta == (home / ".ai-layer" / "projects" / "standard-project-id").resolve()
        assert project not in meta.parents and meta != project
        assert not (project / ".ai-layer").exists()
    finally:
        get_settings.cache_clear()


'''
replace_once("tests/test_privacy.py", privacy_marker, privacy_test + privacy_marker)

repair_marker = "def test_repair_moves_verified_strict_private_local_residue_out_of_repository(\n"
repair_test = '''def test_repair_migrates_legacy_standard_state_and_removes_project_bindings(
    tmp_path: Path, monkeypatch
):
    from ai_layer.integrations.service import install_project_integrations

    home = tmp_path / "home"
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(root, "p-standard", "repo", mode="standard", provenance="allow")
        local = root / ".ai-layer"
        (local / "memory").mkdir(parents=True)
        (local / "project.yaml").write_text(
            _project_yaml(root, "p-standard", mode="standard", provenance="allow"),
            encoding="utf-8",
        )
        (local / "memory" / "keep.txt").write_text("durable\n", encoding="utf-8")
        cursor = root / ".cursor" / "mcp.json"
        cursor.parent.mkdir(parents=True)
        cursor.write_text(
            '{"mcpServers":{"existing":{"command":"keep"}}}\n', encoding="utf-8"
        )
        install_project_integrations(root)

        result = repair_project(root, sync=False)

        destination = home / ".ai-layer" / "projects" / "p-standard"
        assert result["ok"] is True
        assert result["state_destination"] == str(destination)
        assert not local.exists()
        assert (destination / "project.yaml").exists()
        assert (destination / "memory" / "keep.txt").read_text(encoding="utf-8") == "durable\n"
        cursor_data = __import__("json").loads(cursor.read_text(encoding="utf-8"))
        assert cursor_data == {"mcpServers": {"existing": {"command": "keep"}}}
        assert not (root / ".mcp.json").exists()
        assert not (root / ".codex" / "config.toml").exists()
        assert not (root / ".agents" / "mcp_config.json").exists()
    finally:
        get_settings.cache_clear()


'''
replace_once("tests/test_repair.py", repair_marker, repair_test + repair_marker)
