#!/usr/bin/env python3
"""Tamper-evident local guard for governance-sensitive repository files.

This gate deliberately does not pretend that hashes stored in the same writable repository are a
security boundary. CI/protected branches and a release signer are the production trust boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "release" / "governance-policy.json"
BASELINE = ROOT / "release" / "governance-baseline.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_policy() -> dict:
    payload = json.loads(POLICY.read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or not isinstance(payload.get("protected_paths"), list):
        raise RuntimeError("governance policy schema is invalid")
    return payload


def build_baseline() -> dict:
    policy = _load_policy()
    hashes: dict[str, str] = {}
    for raw in policy["protected_paths"]:
        rel = Path(str(raw))
        if rel.is_absolute() or ".." in rel.parts:
            raise RuntimeError(f"unsafe protected path: {raw}")
        path = ROOT / rel
        if not path.is_file():
            raise RuntimeError(f"protected file missing: {raw}")
        hashes[rel.as_posix()] = _sha256(path)
    return {
        "schema": 1,
        "policy_sha256": _sha256(POLICY),
        "protected": hashes,
        "note": "Local tamper-evident baseline; production trust is external protected CI/release signing.",
    }


def run_gate() -> dict:
    errors: list[str] = []
    try:
        expected = build_baseline()
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)], "protected_files": 0}
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "errors": [f"governance baseline unavailable: {exc}"],
            "protected_files": len(expected["protected"]),
        }
    if baseline.get("schema") != 1:
        errors.append("governance baseline schema mismatch")
    if baseline.get("policy_sha256") != expected["policy_sha256"]:
        errors.append("governance policy differs from trusted baseline")
    actual_hashes = expected["protected"]
    baseline_hashes = baseline.get("protected")
    if not isinstance(baseline_hashes, dict):
        errors.append("governance baseline protected hash map is missing")
        baseline_hashes = {}
    if set(baseline_hashes) != set(actual_hashes):
        missing = sorted(set(actual_hashes) - set(baseline_hashes))
        stale = sorted(set(baseline_hashes) - set(actual_hashes))
        if missing:
            errors.append("unbaselined governance files: " + ", ".join(missing))
        if stale:
            errors.append("stale governance baseline files: " + ", ".join(stale))
    for rel, digest in actual_hashes.items():
        if baseline_hashes.get(rel) != digest:
            errors.append(f"governance-sensitive file changed: {rel}")
    return {"ok": not errors, "errors": errors, "protected_files": len(actual_hashes)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Maintainer-only: acknowledge reviewed governance changes.",
    )
    args = parser.parse_args()
    if args.write_baseline:
        payload = build_baseline()
        BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = run_gate()
    print(json.dumps(result, indent=None if args.json else 2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
