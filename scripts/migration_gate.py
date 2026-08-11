#!/usr/bin/env python3
"""Static migration compatibility gate with no database dependency."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
MANIFEST = ROOT / "release" / "release-manifest.json"


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"{path}: missing {name}")


def migration_graph() -> tuple[dict[str, str | None], dict[str, Path]]:
    parents: dict[str, str | None] = {}
    files: dict[str, Path] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        revision = _literal_assignment(path, "revision")
        down = _literal_assignment(path, "down_revision")
        if not isinstance(revision, str) or not revision:
            raise RuntimeError(f"{path}: revision must be a non-empty string")
        if down is not None and not isinstance(down, str):
            raise RuntimeError(f"{path}: merge/multi-parent migrations require explicit gate support")
        if revision in parents:
            raise RuntimeError(f"duplicate migration revision: {revision}")
        parents[revision] = down
        files[revision] = path
    return parents, files


def run_gate() -> dict:
    errors: list[str] = []
    try:
        parents, _ = migration_graph()
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)], "head": None, "revisions": 0}
    referenced = {parent for parent in parents.values() if parent is not None}
    missing = sorted(referenced - set(parents))
    if missing:
        errors.append("missing migration parents: " + ", ".join(missing))
    roots = sorted(rev for rev, parent in parents.items() if parent is None)
    heads = sorted(set(parents) - referenced)
    if len(roots) != 1:
        errors.append(f"expected exactly one migration root, found {roots}")
    if len(heads) != 1:
        errors.append(f"expected exactly one migration head, found {heads}")
    head = heads[0] if len(heads) == 1 else None
    if head:
        visited: set[str] = set()
        current: str | None = head
        while current is not None and current not in visited:
            visited.add(current)
            current = parents.get(current)
        if current is not None:
            errors.append(f"migration cycle detected at {current}")
        if visited != set(parents):
            errors.append("migration graph is not a single linear compatibility chain")
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        migration = manifest.get("migration_compatibility") or {}
        if migration.get("target_schema") != head:
            errors.append("release manifest target_schema does not match Alembic head")
        source = migration.get("minimum_source_schema")
        if source is not None and source not in parents:
            errors.append("release manifest minimum_source_schema is not a known revision")
        if migration.get("rollback") not in {"supported", "forward_only_after_migration"}:
            errors.append("release manifest must declare rollback policy")
    except Exception as exc:
        errors.append(f"invalid migration compatibility manifest: {exc}")
    return {"ok": not errors, "errors": errors, "head": head, "revisions": len(parents)}


def main() -> int:
    payload = run_gate()
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
