#!/usr/bin/env python3
"""Supported release builder: quality gate first, deterministic artifact second."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    quality = subprocess.run(
        [sys.executable, "scripts/quality_gate.py", "--deterministic-wheel"], cwd=ROOT
    )
    if quality.returncode:
        return quality.returncode
    return subprocess.run(
        [sys.executable, "scripts/build_release_archive.py", "--output", str(args.output)], cwd=ROOT
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
