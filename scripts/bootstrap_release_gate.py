#!/usr/bin/env python3
"""Dependency-free installer preflight for a downloaded AI Layer release tree.

This gate is intentionally stdlib-only. It runs before the isolated runtime and
its dependencies exist, so importing application modules here is forbidden.
The full release gate runs inside the freshly installed runtime before the
active runtime pointer is switched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "release-manifest.json"
PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(raw: object) -> Path:
    value = str(raw or "")
    pure = PurePosixPath(value)
    if not value or pure.is_absolute() or ".." in pure.parts or "\\" in value:
        raise RuntimeError(f"unsafe manifest path: {value!r}")
    return Path(*pure.parts)


def _check_exact_lock(path: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_RE.fullmatch(line)
        if match is None:
            errors.append(f"{path.relative_to(ROOT)}:{line_no}: non-exact lock line")
            continue
        key = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        if key in seen:
            errors.append(f"{path.relative_to(ROOT)}:{line_no}: duplicate package {match.group(1)}")
        seen.add(key)
    if not seen:
        errors.append(f"{path.relative_to(ROOT)}: lock contains no packages")
    return errors


def _check_wheel(path: Path, *, version: str, scripts: dict[str, str]) -> list[str]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for raw in names:
                pure = PurePosixPath(raw)
                if pure.is_absolute() or ".." in pure.parts or "\\" in raw:
                    errors.append(f"application wheel contains unsafe path: {raw}")
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            entry_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
            if len(metadata_names) != 1:
                errors.append("application wheel must contain exactly one METADATA file")
            else:
                metadata = archive.read(metadata_names[0]).decode("utf-8", errors="replace")
                if f"Name: local-ai-development-layer\n" not in metadata:
                    errors.append("application wheel project name mismatch")
                if f"Version: {version}\n" not in metadata:
                    errors.append("application wheel version mismatch")
            if len(entry_names) != 1:
                errors.append("application wheel must contain exactly one entry_points.txt")
            else:
                entry_points = archive.read(entry_names[0]).decode("utf-8", errors="replace")
                for name, target in scripts.items():
                    if f"{name} = {target}" not in entry_points:
                        errors.append(f"application wheel console script mismatch: {name}")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"application wheel is unreadable: {exc}")
    return errors


def run_gate() -> dict:
    errors: list[str] = []
    try:
        project_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        version = str(project_data["version"])
        scripts = {str(k): str(v) for k, v in dict(project_data.get("scripts") or {}).items()}
    except Exception as exc:
        return {"ok": False, "errors": [f"invalid pyproject.toml: {exc}"]}

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "version": version, "errors": [f"invalid release manifest: {exc}"]}

    if manifest.get("version") != version:
        errors.append("release manifest version mismatch")
    runtime = manifest.get("official_runtime") or {}
    if runtime != {
        "arch": "x86_64",
        "os": "linux",
        "python_implementation": "CPython",
        "python_series": "3.12.x",
    }:
        errors.append("release manifest official runtime mismatch")

    artifact_specs = [
        ("runtime_lock", "runtime_lock_sha256"),
        ("release_tools_lock", "release_tools_lock_sha256"),
        ("application_wheel", "application_wheel_sha256"),
    ]
    resolved: dict[str, Path] = {}
    for path_key, hash_key in artifact_specs:
        try:
            rel = _safe_relative(manifest.get(path_key))
        except Exception as exc:
            errors.append(str(exc))
            continue
        path = ROOT / rel
        resolved[path_key] = path
        if not path.is_file():
            errors.append(f"release artifact missing: {rel.as_posix()}")
            continue
        expected = str(manifest.get(hash_key) or "")
        actual = _sha256(path)
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            errors.append(f"invalid manifest sha256 field: {hash_key}")
        elif actual != expected:
            errors.append(f"release artifact checksum mismatch: {rel.as_posix()}")

    lock = resolved.get("runtime_lock")
    if lock and lock.is_file():
        errors.extend(_check_exact_lock(lock))
    tools = resolved.get("release_tools_lock")
    if tools and tools.is_file():
        errors.extend(_check_exact_lock(tools))
    wheel = resolved.get("application_wheel")
    if wheel and wheel.is_file():
        errors.extend(_check_wheel(wheel, version=version, scripts=scripts))

    return {"ok": not errors, "version": version, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_gate()
    print(
        json.dumps(result, sort_keys=True)
        if args.json
        else json.dumps(result, indent=2, sort_keys=True)
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
