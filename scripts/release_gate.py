#!/usr/bin/env python3
"""Static release gate for version alignment and reproducible-install artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from architecture_gate import run_gate as run_architecture_gate
from build_release_archive import ALLOWED_ROOT_DIRS, ALLOWED_ROOT_FILES, EXCLUDED_ROOT_ENTRIES
from governance_gate import run_gate as run_governance_gate
from migration_gate import run_gate as run_migration_gate
from skill_gate import run_gate as run_skill_gate

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "release" / "requirements-linux-x86_64-py312.lock"
TOOLS_LOCK = ROOT / "release" / "requirements-release-tools.lock"
MANIFEST = ROOT / "release" / "release-manifest.json"
DOCKER = ROOT / "docker-compose.yml"
INIT = ROOT / "src" / "ai_layer" / "__init__.py"
PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
DIGEST_RE = re.compile(r"pgvector/pgvector:[^\s@]+@sha256:[0-9a-f]{64}")


def canonicalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_lock() -> dict[str, str]:
    pins: dict[str, str] = {}
    for no, raw in enumerate(LOCK.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = PIN_RE.fullmatch(line)
        if not m:
            raise RuntimeError(f"{LOCK}:{no}: non-exact lock line: {line}")
        name, version = m.groups()
        key = canonicalize(name)
        if key in pins:
            raise RuntimeError(f"duplicate lock pin: {name}")
        pins[key] = version
    return pins


def dependency_name(spec: str) -> str:
    return canonicalize(re.split(r"[<>=!~;\[\s]", spec, maxsplit=1)[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check-deterministic-wheel", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    allowed_root = ALLOWED_ROOT_FILES | ALLOWED_ROOT_DIRS | EXCLUDED_ROOT_ENTRIES
    unexpected_root = sorted(path.name for path in ROOT.iterdir() if path.name not in allowed_root)
    if unexpected_root:
        errors.append("unexpected top-level release artifacts: " + ", ".join(unexpected_root))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    version = project["version"]
    if pyproject.get("build-system", {}).get("requires") != ["hatchling==1.27.0"]:
        errors.append("build backend must be pinned to hatchling==1.27.0")
    if project.get("requires-python") != ">=3.12,<3.13":
        errors.append("official runtime must be constrained to CPython 3.12.x")
    try:
        pins = parse_lock()
    except Exception as exc:
        pins = {}
        errors.append(str(exc))
    for dep in project.get("dependencies", []):
        name = dependency_name(dep)
        if name not in pins:
            errors.append(f"direct runtime dependency missing from lock: {name}")
    if "psycopg-binary" not in pins:
        errors.append("psycopg[binary] requires explicit psycopg-binary pin")
    try:
        tool_lines = [
            line.strip()
            for line in TOOLS_LOCK.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not tool_lines or any(PIN_RE.fullmatch(line) is None for line in tool_lines):
            errors.append("maintainer tooling lock must contain exact NAME==VERSION pins only")
    except Exception as exc:
        errors.append(f"invalid maintainer tooling lock: {exc}")
    docker_text = DOCKER.read_text(encoding="utf-8")
    match = DIGEST_RE.search(docker_text)
    if not match:
        errors.append("PostgreSQL/pgvector image is not pinned by sha256 digest")
    wheel = ROOT / "dist" / f"local_ai_development_layer-{version}-py3-none-any.whl"
    if not wheel.is_file():
        errors.append(f"release application wheel missing: {wheel.relative_to(ROOT)}")
    init_text = INIT.read_text(encoding="utf-8")
    if version not in init_text:
        errors.append("src/ai_layer/__init__.py version is not aligned")
    if MANIFEST.is_file() and wheel.is_file():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            if manifest.get("version") != version:
                errors.append("release manifest version mismatch")
            if manifest.get("runtime_lock_sha256") != sha256(LOCK):
                errors.append("release manifest runtime lock hash mismatch")
            if manifest.get("release_tools_lock_sha256") != sha256(TOOLS_LOCK):
                errors.append("release manifest maintainer tooling lock hash mismatch")
            if manifest.get("application_wheel_sha256") != sha256(wheel):
                errors.append("release manifest wheel hash mismatch")
            if match and manifest.get("docker_image") != match.group(0):
                errors.append("release manifest docker image mismatch")
        except Exception as exc:
            errors.append(f"invalid release manifest: {exc}")
    else:
        errors.append("release manifest missing")
    architecture = run_architecture_gate(ROOT)
    if not architecture.get("ok"):
        errors.extend(f"architecture: {item}" for item in architecture.get("errors", []))

    governance = run_governance_gate()
    if not governance.get("ok"):
        errors.extend(f"governance: {item}" for item in governance.get("errors", []))

    migrations = run_migration_gate()
    if not migrations.get("ok"):
        errors.extend(f"migration: {item}" for item in migrations.get("errors", []))

    skills = run_skill_gate()
    if not skills.get("ok"):
        errors.extend(f"skills: {item}" for item in skills.get("errors", []))

    if args.check_deterministic_wheel:
        import tempfile

        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            # Builder's default output is fixed, so invoke its build() directly for temp dirs.
            code = (
                "from pathlib import Path; import sys; "
                f"sys.path.insert(0,{str(ROOT / 'scripts').__repr__()}); "
                "from build_release_wheel import build; print(build(Path(sys.argv[1])))"
            )
            pa = subprocess.run([sys.executable, "-c", code, a], capture_output=True, text=True)
            pb = subprocess.run([sys.executable, "-c", code, b], capture_output=True, text=True)
            if pa.returncode or pb.returncode:
                errors.append("deterministic wheel rebuild failed")
            else:
                wa = next(Path(a).glob("*.whl"))
                wb = next(Path(b).glob("*.whl"))
                if sha256(wa) != sha256(wb):
                    errors.append("application wheel builder is not deterministic")
    payload = {
        "ok": not errors,
        "version": version,
        "locked_packages": len(pins),
        "architecture": architecture.get("metrics", {}),
        "governance": governance,
        "migrations": migrations,
        "skills": skills,
        "errors": errors,
    }
    print(json.dumps(payload, indent=None if args.json else 2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
