from pathlib import Path


def test_installer_does_not_roll_old_code_back_after_upgrade_attempt():
    text = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    failure_block = text.split("if [[ $UPGRADE_STATUS -ne 0 ]]; then", 1)[1].split("\nfi\n", 1)[0]
    assert "current.rollback" not in failure_block
    assert "new executable remains active" in failure_block


def test_installer_enables_always_on_service_by_default():
    text = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    assert '"$CURRENT_LINK/bin/ai-layer" service install' in text
    assert "--no-service" in text
    assert "service uninstall >/dev/null 2>&1 || true" in text


def test_uninstaller_removes_user_service_before_runtime():
    text = (Path(__file__).parents[1] / "uninstall.sh").read_text(encoding="utf-8")
    assert "service uninstall" in text
    assert "ai-layer.service" in text


def test_uninstaller_cleans_owned_integrations_before_runtime_removal():
    text = (Path(__file__).parents[1] / "uninstall.sh").read_text(encoding="utf-8")
    assert "uninstall-integrations" in text
    assert text.index("uninstall-integrations") < text.index(
        'remove_owned_runtime_pointer "$RUNTIME_HOME/current"'
    )
    assert 'rm -rf "$RUNTIME_HOME"' not in text


def test_uninstaller_preserves_unowned_files_and_launchers(tmp_path: Path):
    import os
    import subprocess

    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    runtime = tmp_path / "shared-runtime"
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    home.mkdir()
    runtime.mkdir()
    bindir.mkdir()
    state.mkdir()
    (runtime / "unrelated.txt").write_text("keep\n", encoding="utf-8")
    (runtime / "releases").mkdir()
    foreign_release = runtime / "releases" / "foreign"
    foreign_release.mkdir()
    (foreign_release / "keep.txt").write_text("keep\n", encoding="utf-8")
    launcher = bindir / "ai-layer"
    launcher.write_text("USER TOOL\n", encoding="utf-8")

    env = {
        **os.environ,
        "HOME": str(home),
        "AI_LAYER_RUNTIME_HOME": str(runtime),
        "AI_LAYER_BIN_DIR": str(bindir),
        "AI_LAYER_HOME": str(state),
    }
    proc = subprocess.run(
        ["bash", str(root / "uninstall.sh")], env=env, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert (runtime / "unrelated.txt").read_text(encoding="utf-8") == "keep\n"
    assert (foreign_release / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert launcher.read_text(encoding="utf-8") == "USER TOOL\n"


def test_uninstaller_purge_requires_recognizable_state_and_preserves_unknown_content(
    tmp_path: Path,
):
    import os
    import subprocess

    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    runtime = tmp_path / "runtime"
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    for path in (home, runtime, bindir, state):
        path.mkdir()
    unknown = state / "user-notes.txt"
    unknown.write_text("keep\n", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "AI_LAYER_RUNTIME_HOME": str(runtime),
        "AI_LAYER_BIN_DIR": str(bindir),
        "AI_LAYER_HOME": str(state),
    }
    refused = subprocess.run(
        ["bash", str(root / "uninstall.sh"), "--purge"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "not recognizably AI Layer-owned" in refused.stderr
    assert unknown.exists()

    (state / "install.json").write_text(
        '{"version":"0.8.0","runtime_home":"/tmp/example"}\n', encoding="utf-8"
    )
    (state / "install-journal.json").write_text(
        '{"schema":1,"operation":"global-install","status":"in_progress"}\n', encoding="utf-8"
    )
    (state / "runtime").mkdir()
    (state / "runtime" / "alembic.ini").write_text("owned\n", encoding="utf-8")
    (state / "runtime" / "docker-compose.yml").write_text("owned\n", encoding="utf-8")
    purged = subprocess.run(
        ["bash", str(root / "uninstall.sh"), "--purge"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert purged.returncode == 0, purged.stderr
    assert unknown.read_text(encoding="utf-8") == "keep\n"
    assert not (state / "install.json").exists()
    assert not (state / "install-journal.json").exists()
    assert not (state / "runtime").exists()


def test_installer_refuses_unowned_launcher_before_runtime_changes(tmp_path: Path):
    import os
    import subprocess

    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    runtime = tmp_path / "runtime-home"
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    for path in (home, runtime, bindir, state):
        path.mkdir()
    launcher = bindir / "ai-layer"
    launcher.write_text("USER TOOL\n", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "AI_LAYER_RUNTIME_HOME": str(runtime),
        "AI_LAYER_BIN_DIR": str(bindir),
        "AI_LAYER_HOME": str(state),
    }
    proc = subprocess.run(
        ["bash", str(root / "install.sh"), "--skip-db"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "refusing to overwrite unowned launcher" in proc.stderr
    assert launcher.read_text(encoding="utf-8") == "USER TOOL\n"
    assert not (runtime / "releases").exists()


def test_installer_refuses_unrecognized_machine_runtime_before_runtime_changes(tmp_path: Path):
    import os
    import subprocess

    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    runtime = tmp_path / "runtime-home"
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    machine_runtime = state / "runtime"
    for path in (home, runtime, bindir, state, machine_runtime):
        path.mkdir()
    sentinel = machine_runtime / "user-data.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "AI_LAYER_RUNTIME_HOME": str(runtime),
        "AI_LAYER_BIN_DIR": str(bindir),
        "AI_LAYER_HOME": str(state),
    }
    proc = subprocess.run(
        ["bash", str(root / "install.sh"), "--skip-db"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "refusing to replace unrecognized machine runtime assets" in proc.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert not (runtime / "releases").exists()


def test_installer_keep_releases_requires_value():
    import subprocess

    root = Path(__file__).parents[1]
    proc = subprocess.run(
        ["bash", str(root / "install.sh"), "--keep-releases"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "requires a non-negative integer" in proc.stderr


def test_installer_refuses_nonempty_unrecognized_state_home(tmp_path: Path):
    import os
    import subprocess

    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    runtime = tmp_path / "runtime-home"
    bindir = tmp_path / "bin"
    state = tmp_path / "shared-state"
    for path in (home, runtime, bindir, state):
        path.mkdir()
    sentinel = state / "notes.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "AI_LAYER_RUNTIME_HOME": str(runtime),
        "AI_LAYER_BIN_DIR": str(bindir),
        "AI_LAYER_HOME": str(state),
    }
    proc = subprocess.run(
        ["bash", str(root / "install.sh"), "--skip-db"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "non-empty unrecognized AI Layer state home" in proc.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert not (runtime / "releases").exists()


def test_uninstaller_never_executes_unowned_current_runtime(tmp_path: Path):
    import os
    import subprocess

    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    runtime = tmp_path / "runtime"
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    evil = tmp_path / "evil"
    for path in (home, runtime, bindir, state, evil / "bin"):
        path.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "executed"
    executable = evil / "bin" / "ai-layer"
    executable.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    executable.chmod(0o700)
    (evil / "bin" / "ai-layer-mcp").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (evil / "bin" / "ai-layer-mcp").chmod(0o700)
    (runtime / "current").symlink_to(evil)
    env = {
        **os.environ,
        "HOME": str(home),
        "AI_LAYER_RUNTIME_HOME": str(runtime),
        "AI_LAYER_BIN_DIR": str(bindir),
        "AI_LAYER_HOME": str(state),
    }
    proc = subprocess.run(
        ["bash", str(root / "uninstall.sh")], env=env, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert not marker.exists()
    assert (runtime / "current").is_symlink()


def test_installer_uses_dependency_free_preflight_before_venv_and_full_gate_before_activation():
    text = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    preflight = text.index("scripts/bootstrap_release_gate.py")
    venv = text.index('-m venv "$RELEASE_DIR"')
    install_lock = text.index('--only-binary=:all: --no-deps -r "$LOCK_FILE"')
    full_gate = text.index("scripts/release_gate.py", preflight + 1)
    switch = text.index('mv -Tf "$RUNTIME_HOME/current.next" "$CURRENT_LINK"')
    assert preflight < venv < install_lock < full_gate < switch


def test_installer_cleans_incomplete_release_before_activation():
    text = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    assert "RELEASE_ACTIVATED=0" in text
    assert "cleanup_incomplete_release()" in text
    assert 'rm -rf "$RELEASE_DIR"' in text
    assert text.index("RELEASE_ACTIVATED=1") > text.index(
        'mv -Tf "$RUNTIME_HOME/current.next" "$CURRENT_LINK"'
    )
