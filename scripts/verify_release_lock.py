#!/usr/bin/env python3
"""Fail-closed verifier for the current closed-world runtime lock."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path

PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
BOOTSTRAP_ALLOWED = {"pip", "setuptools", "wheel"}


def canonicalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_RE.fullmatch(line)
        if not match:
            raise ValueError(f"{path}:{no}: expected exact NAME==VERSION pin: {line!r}")
        name, version = match.groups()
        key = canonicalize(name)
        if key in pins:
            raise ValueError(f"{path}:{no}: duplicate package pin: {name}")
        pins[key] = version
    if not pins:
        raise ValueError(f"{path}: lock is empty")
    return pins


def installed_distributions() -> dict[str, str]:
    result: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            result[canonicalize(name)] = dist.version
    return result


def verify(lock: dict[str, str], installed: dict[str, str], app_version: str) -> list[str]:
    errors: list[str] = []
    expected = dict(lock)
    expected["local-ai-development-layer"] = app_version
    for name, version in sorted(expected.items()):
        actual = installed.get(name)
        if actual is None:
            errors.append(f"missing: {name}=={version}")
        elif actual != version:
            errors.append(f"version mismatch: {name}: expected {version}, installed {actual}")
    unexpected = sorted(set(installed) - set(expected) - BOOTSTRAP_ALLOWED)
    if unexpected:
        errors.append("unexpected distributions outside release lock: " + ", ".join(unexpected))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    locked_packages = 0
    try:
        lock = parse_lock(args.lock)
        locked_packages = len(lock)
        installed = installed_distributions()
        errors = verify(lock, installed, args.app_version)
    except Exception as exc:
        errors = [str(exc)]
    payload = {"ok": not errors, "errors": errors, "locked_packages": locked_packages}
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(f"Release lock verified: {payload['locked_packages']} pinned runtime packages + application wheel.")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
