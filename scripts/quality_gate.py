#!/usr/bin/env python3
"""Canonical fail-closed contributor/release quality gate."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(name: str, argv: list[str], *, required_tool: str | None = None) -> dict:
    started = time.monotonic()
    if required_tool and shutil.which(required_tool) is None:
        return {
            "name": name,
            "ok": False,
            "exit_code": None,
            "seconds": 0.0,
            "error": f"required tool missing: {required_tool}",
            "argv": argv,
        }
    env = None
    if len(argv) >= 3 and argv[1:3] == ["-m", "pytest"]:
        env = os.environ.copy()
        # Contributor/release tests must not inherit arbitrary globally installed pytest plugins.
        # Project-owned plugins must be declared and loaded explicitly instead.
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, env=env)
    output = (proc.stdout + ("\n" if proc.stdout and proc.stderr else "") + proc.stderr).strip()
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "argv": argv,
        "output_tail": output[-5000:],
    }


def stages(*, deterministic_wheel: bool) -> list[tuple[str, list[str], str | None]]:
    python = sys.executable
    release = [python, "scripts/release_gate.py"]
    if deterministic_wheel:
        release.append("--check-deterministic-wheel")
    return [
        ("format", ["ruff", "format", "--check", "."], "ruff"),
        ("lint", ["ruff", "check", "."], "ruff"),
        ("type", ["mypy", "src/ai_layer"], "mypy"),
        ("architecture-and-complexity", [python, "scripts/architecture_gate.py"], None),
        ("migration-compatibility", [python, "scripts/migration_gate.py"], None),
        ("skill-contracts", [python, "scripts/skill_gate.py"], None),
        ("governance", [python, "scripts/governance_gate.py"], None),
        ("unit-and-integration-tests", [python, "-m", "pytest", "tests"], None),
        ("packaging-and-release", release, None),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--deterministic-wheel", action="store_true")
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="diagnostic only; final status still fails closed",
    )
    args = parser.parse_args()
    results: list[dict] = []
    for name, argv, tool in stages(deterministic_wheel=args.deterministic_wheel):
        result = _run(name, argv, required_tool=tool)
        results.append(result)
        if not result["ok"] and not args.continue_on_failure:
            break
    expected_stages = stages(deterministic_wheel=args.deterministic_wheel)
    payload = {
        "ok": (
            bool(results)
            and all(item["ok"] for item in results)
            and len(results) == len(expected_stages)
        ),
        "stages": results,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for item in results:
            status = "PASS" if item["ok"] else "FAIL"
            print(f"[{status}] {item['name']} ({item['seconds']}s)")
            if not item["ok"] and (item.get("error") or item.get("output_tail")):
                print(item.get("error") or item.get("output_tail"))
        print("QUALITY GATE: " + ("PASS" if payload["ok"] else "FAIL"))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
