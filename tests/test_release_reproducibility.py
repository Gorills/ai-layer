from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
LOCK = ROOT / "release" / "requirements-linux-x86_64-py312.lock"


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_runtime_is_intentionally_limited_to_python_312():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["build-system"]["requires"] == ["hatchling==1.27.0"]
    assert data["project"]["requires-python"] == ">=3.12,<3.13"
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'platform.python_implementation() == "CPython"' in installer
    assert "sys.version_info[:2] == (3, 12)" in installer
    assert "sys.version_info >= (3, 12)" not in installer


def test_runtime_lock_is_closed_world_exact_and_contains_every_direct_dependency():
    verifier = _load_script("verify_release_lock.py")
    pins = verifier.parse_lock(LOCK)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    direct = {
        verifier.canonicalize(re.split(r"[<>=!~;\[\s]", dep, maxsplit=1)[0])
        for dep in project["dependencies"]
    }
    assert direct <= set(pins)
    assert "psycopg-binary" in pins
    assert len(pins) >= 70


def test_installer_cannot_resolve_floating_dependencies_or_build_application_from_source():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    lock_install = text.index('--only-binary=:all: --no-deps -r "$LOCK_FILE"')
    wheel_install = text.index('--no-cache-dir --no-deps "$WHEEL_FILE"')
    pip_check = text.index('"$RELEASE_DIR/bin/python" -m pip check')
    exact_set = text.index("scripts/verify_release_lock.py")
    switch = text.index('ln -sfn "$RELEASE_DIR" "$RUNTIME_HOME/current.next"')
    assert lock_install < wheel_install < pip_check < exact_set < switch
    assert 'pip install --disable-pip-version-check "$SOURCE_DIR"' not in text


def test_postgres_image_is_versioned_and_digest_pinned():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(
        r"image: pgvector/pgvector:0\.8\.0-pg16@sha256:[0-9a-f]{64}",
        text,
    )
    assert "image: pgvector/pgvector:pg16\n" not in text


def test_postgres_gate_exercises_manifest_minimum_source_schema():
    manifest = json.loads((ROOT / "release" / "release-manifest.json").read_text(encoding="utf-8"))
    source = manifest["migration_compatibility"]["minimum_source_schema"]
    gate = (ROOT / "scripts" / "postgres_gate.py").read_text(encoding="utf-8")
    assert source in gate
    assert f"supported-source-upgrade-{source.split('_', 1)[0]}" in gate


def test_release_manifest_hashes_match_artifacts():
    manifest = json.loads((ROOT / "release" / "release-manifest.json").read_text(encoding="utf-8"))
    lock = ROOT / manifest["runtime_lock"]
    wheel = ROOT / manifest["application_wheel"]
    assert hashlib.sha256(lock.read_bytes()).hexdigest() == manifest["runtime_lock_sha256"]
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == manifest["application_wheel_sha256"]
    tools = ROOT / manifest["release_tools_lock"]
    assert hashlib.sha256(tools.read_bytes()).hexdigest() == manifest["release_tools_lock_sha256"]
    assert manifest["official_runtime"] == {
        "arch": "x86_64",
        "os": "linux",
        "python_implementation": "CPython",
        "python_series": "3.12.x",
    }


def test_committed_application_wheel_matches_current_source(tmp_path: Path):
    """Fail closed if runtime source changed without refreshing the installable wheel."""
    builder = _load_script("build_release_wheel.py")
    rebuilt = builder.build(tmp_path)
    manifest = json.loads((ROOT / "release" / "release-manifest.json").read_text(encoding="utf-8"))
    committed = ROOT / manifest["application_wheel"]
    assert committed.is_file()
    assert (
        hashlib.sha256(rebuilt.read_bytes()).digest()
        == hashlib.sha256(committed.read_bytes()).digest()
    )


def test_application_wheel_console_scripts_match_pyproject(tmp_path: Path):
    builder = _load_script("build_release_wheel.py")
    wheel = builder.build(tmp_path)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    import zipfile

    with zipfile.ZipFile(wheel) as archive:
        entry_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = archive.read(entry_name).decode("utf-8")

    for name, target in project["scripts"].items():
        assert f"{name} = {target}" in entry_points
    assert "ai_layer.cli.app:app" not in entry_points


def test_application_wheel_builder_is_deterministic():
    builder = _load_script("build_release_wheel.py")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        first = builder.build(Path(a))
        second = builder.build(Path(b))
        assert (
            hashlib.sha256(first.read_bytes()).digest()
            == hashlib.sha256(second.read_bytes()).digest()
        )


def test_canonical_pytest_stage_is_hermetic_from_global_plugins(monkeypatch):
    gate = _load_script("quality_gate.py")
    captured: dict = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["env"] = dict(kwargs.get("env") or {})
        return Result()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    result = gate._run("tests", [sys.executable, "-m", "pytest", "tests"])

    assert result["ok"] is True
    assert captured["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_release_gate_passes_for_archive_artifacts():
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release_gate.py"),
            "--check-deterministic-wheel",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_exact_set_verifier_rejects_missing_wrong_and_unexpected_distributions():
    verifier = _load_script("verify_release_lock.py")
    lock = {"a": "1", "b": "2"}
    installed = {"a": "1", "b": "9", "local-ai-development-layer": "0.7.0", "rogue": "1"}
    errors = verifier.verify(lock, installed, "0.7.0")
    assert any("version mismatch: b" in item for item in errors)
    assert any("unexpected distributions" in item and "rogue" in item for item in errors)


def test_release_archive_builder_is_deterministic_and_excludes_test_cache():
    builder = _load_script("build_release_archive.py")
    import zipfile

    with tempfile.TemporaryDirectory() as tmp:
        first = builder.build(Path(tmp) / "first.zip", ROOT)
        second = builder.build(Path(tmp) / "second.zip", ROOT)
        assert (
            hashlib.sha256(first.read_bytes()).digest()
            == hashlib.sha256(second.read_bytes()).digest()
        )
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
        assert not any(
            "/.pytest_cache/" in name or "/__pycache__/" in name or name.endswith(".pyc")
            for name in names
        )


def test_release_archive_builder_rejects_unknown_top_level_artifacts(tmp_path: Path):
    builder = _load_script("build_release_archive.py")
    root = tmp_path / "release-tree"
    root.mkdir()
    (root / "README.md").write_text("ok\n", encoding="utf-8")
    (root / "accidental-worker-label").write_text("", encoding="utf-8")
    import pytest

    with pytest.raises(RuntimeError, match="unexpected top-level development repository artifacts"):
        builder.included_files(root)


def test_bootstrap_release_gate_is_dependency_free_and_passes_in_isolated_python():
    proc = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts" / "bootstrap_release_gate.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": ""},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_release_trust_chain_files_are_governance_protected():
    policy = json.loads((ROOT / "release" / "governance-policy.json").read_text(encoding="utf-8"))
    protected = set(policy["protected_paths"])
    assert {
        "install.sh",
        "scripts/bootstrap_release_gate.py",
        "scripts/verify_release_lock.py",
        "scripts/build_release_wheel.py",
    } <= protected
