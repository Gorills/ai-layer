from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ai_layer.core.config import get_settings
from ai_layer.core.filelock import directory_lock

REGISTRY_VERSION = 4
PROJECT_MODES = {"standard", "external", "strict-private"}
PROVENANCE_POLICIES = {"allow", "forbid"}


def is_ephemeral_project_root(root: str | Path) -> bool:
    """Return True for machine-local test scratch paths that must not own durable registry state."""
    path = Path(root).expanduser().resolve()
    parts = path.parts
    if len(parts) == 3 and parts[0] == os.sep and parts[1] == "tmp":
        name = parts[2]
        if name.startswith(("work-spine-", "work-scope-", "project-map-")):
            return True
    if (
        len(parts) == 5
        and parts[0] == os.sep
        and parts[1] == "tmp"
        and parts[2].startswith("pytest-of-")
        and parts[3].startswith("pytest-")
        and parts[4].startswith("test_")
    ):
        return True
    return False


class RegistryCorruptError(RuntimeError):
    """Machine project registry exists but cannot be trusted safely."""


def _registry_lock_path() -> Path:
    path = get_settings().projects_registry_file
    return path.with_name(path.name + ".lock")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _external_state_entries() -> list[dict]:
    """Recover machine-side project authority if registry entries are lost."""
    base = get_settings().projects_state_dir
    if not base.exists():
        return []
    if base.is_symlink():
        raise RegistryCorruptError(f"AI Layer external projects state root is symlinked: {base}")
    entries: list[dict] = []
    try:
        children = list(base.iterdir())
    except OSError as exc:
        raise RegistryCorruptError(
            f"AI Layer external projects state root is unreadable: {base}"
        ) from exc
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        config = child / "project.yaml"
        if config.is_symlink() or not config.is_file():
            continue
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise RegistryCorruptError(
                f"AI Layer external project state is unreadable: {config}"
            ) from exc
        if not isinstance(data, dict):
            raise RegistryCorruptError(f"AI Layer external project state is invalid: {config}")
        mode = str(data.get("mode") or "")
        if mode not in PROJECT_MODES:
            continue
        root = str(data.get("root") or "").strip()
        project_id = str(data.get("project_id") or child.name).strip()
        if not root or not project_id or project_id != child.name:
            raise RegistryCorruptError(f"AI Layer external project state is invalid: {config}")
        entries.append(
            {
                "root": str(Path(root).expanduser().resolve()),
                "project_id": project_id,
                "name": str(data.get("name") or Path(root).name),
                "mode": mode,
                "provenance": str(
                    data.get("provenance") or ("forbid" if mode == "strict-private" else "allow")
                ),
                "recovered_from_external_state": True,
            }
        )
    return entries


def _merge_external_private_entries(data: dict) -> dict:
    roots = {str(item.get("root")) for item in data.get("projects", []) if isinstance(item, dict)}
    forgotten = set(data.get("forgotten_roots", []))
    for item in _external_state_entries():
        if item["root"] in forgotten:
            continue
        if item["root"] not in roots:
            data["projects"].append(item)
            roots.add(item["root"])
    return data


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def load_registry() -> dict:
    path = get_settings().projects_registry_file
    if not path.exists():
        return _merge_external_private_entries(
            {"version": REGISTRY_VERSION, "projects": [], "forgotten_roots": []}
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise RegistryCorruptError(
            f"AI Layer project registry is unreadable/corrupt: {path}. "
            "Refusing to fall back to standard project mode."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise RegistryCorruptError(
            f"AI Layer project registry has an invalid structure: {path}. "
            "Refusing to fall back to standard project mode."
        )
    data["version"] = REGISTRY_VERSION
    forgotten = data.setdefault("forgotten_roots", [])
    if not isinstance(forgotten, list):
        raise RegistryCorruptError(f"AI Layer project registry has invalid forgotten_roots: {path}")
    normalized_forgotten: list[str] = []
    seen_forgotten: set[str] = set()
    for raw in forgotten:
        if not isinstance(raw, str) or not raw.strip():
            raise RegistryCorruptError(
                f"AI Layer project registry contains invalid forgotten root: {path}"
            )
        canonical = str(Path(raw).expanduser().resolve())
        if canonical != raw or raw in seen_forgotten:
            raise RegistryCorruptError(
                f"AI Layer project registry contains non-canonical/duplicate forgotten root: {raw}"
            )
        seen_forgotten.add(raw)
        normalized_forgotten.append(raw)
    data["forgotten_roots"] = normalized_forgotten
    seen_roots: set[str] = set()
    for item in data["projects"]:
        if not isinstance(item, dict):
            raise RegistryCorruptError(
                f"AI Layer project registry contains an invalid project entry: {path}"
            )
        root = item.get("root")
        if not isinstance(root, str) or not root.strip():
            raise RegistryCorruptError(
                f"AI Layer project registry contains an invalid root: {path}"
            )
        canonical_root = str(Path(root).expanduser().resolve())
        if canonical_root != root or root in seen_roots:
            raise RegistryCorruptError(
                f"AI Layer project registry contains a non-canonical/duplicate root: {root}"
            )
        seen_roots.add(root)
        mode = item.setdefault("mode", "standard")
        provenance = item.setdefault("provenance", "allow")
        if mode not in PROJECT_MODES or provenance not in PROVENANCE_POLICIES:
            raise RegistryCorruptError(
                f"AI Layer project registry contains invalid privacy metadata for: {root}"
            )
        if mode in {"external", "strict-private"} and not str(item.get("project_id") or "").strip():
            raise RegistryCorruptError(
                f"AI Layer external-state registry entry lacks project_id: {root}"
            )
        if root in seen_forgotten:
            raise RegistryCorruptError(
                f"AI Layer project registry contains a root as both active and forgotten: {root}"
            )
    return _merge_external_private_entries(data)


def overlapping_registered_projects(root: str | Path) -> list[dict]:
    """Return registered ancestor/descendant roots, excluding the exact same root."""
    resolved = Path(root).expanduser().resolve()
    conflicts: list[dict] = []
    for item in load_registry().get("projects", []):
        raw = str(item.get("root") or "").strip()
        if not raw:
            continue
        other = Path(raw).expanduser().resolve()
        if other == resolved:
            continue
        try:
            resolved.relative_to(other)
            overlaps = True
        except ValueError:
            try:
                other.relative_to(resolved)
                overlaps = True
            except ValueError:
                overlaps = False
        if overlaps:
            conflicts.append(dict(item))
    return sorted(conflicts, key=lambda item: str(item.get("root", "")))


def get_registered_project(root: str | Path) -> dict | None:
    resolved = str(Path(root).expanduser().resolve())
    return next(
        (item for item in load_registry().get("projects", []) if item.get("root") == resolved), None
    )


def register_project(
    root: str | Path,
    project_id: str | None = None,
    name: str | None = None,
    *,
    mode: str | None = None,
    provenance: str | None = None,
) -> dict:
    resolved = str(Path(root).expanduser().resolve())
    if mode is not None and mode not in PROJECT_MODES:
        raise ValueError(f"Unsupported project mode: {mode}")
    if provenance is not None and provenance not in PROVENANCE_POLICIES:
        raise ValueError(f"Unsupported provenance policy: {provenance}")
    with directory_lock(_registry_lock_path()):
        data = load_registry()
        projects = data["projects"]
        data["forgotten_roots"] = [
            item for item in data.get("forgotten_roots", []) if item != resolved
        ]
        entry = next((item for item in projects if item.get("root") == resolved), None)
        if entry is None:
            entry = {"root": resolved, "mode": "standard", "provenance": "allow"}
            projects.append(entry)
        if project_id:
            entry["project_id"] = str(project_id)
        if name:
            entry["name"] = name
        if mode is not None:
            entry["mode"] = mode
        else:
            entry.setdefault("mode", "standard")
        if provenance is not None:
            entry["provenance"] = provenance
        else:
            entry.setdefault("provenance", "allow")
        entry["last_seen_at"] = _utcnow()
        _atomic_json_write(get_settings().projects_registry_file, data)
        return dict(entry)


def unregister_project(root: str | Path) -> dict:
    resolved = str(Path(root).expanduser().resolve())
    with directory_lock(_registry_lock_path()):
        data = load_registry()
        before = len(data["projects"])
        data["projects"] = [item for item in data["projects"] if item.get("root") != resolved]
        removed = before - len(data["projects"])
        forgotten = list(data.get("forgotten_roots", []))
        if resolved not in forgotten:
            forgotten.append(resolved)
            forgotten.sort()
        data["forgotten_roots"] = forgotten
        _atomic_json_write(get_settings().projects_registry_file, data)
        return {"root": resolved, "removed": removed, "forgotten": True}


def is_project_forgotten(root: str | Path) -> bool:
    resolved = str(Path(root).expanduser().resolve())
    return resolved in set(load_registry().get("forgotten_roots", []))


def list_registered_projects(*, existing_only: bool = False) -> list[dict]:
    projects = list(load_registry().get("projects", []))
    if existing_only:
        projects = [item for item in projects if Path(str(item.get("root", ""))).exists()]
    return sorted(projects, key=lambda item: str(item.get("root", "")))


def prune_registry() -> dict:
    with directory_lock(_registry_lock_path()):
        data = load_registry()
        before = len(data["projects"])
        data["projects"] = [
            item for item in data["projects"] if Path(str(item.get("root", ""))).exists()
        ]
        _atomic_json_write(get_settings().projects_registry_file, data)
        return {
            "before": before,
            "after": len(data["projects"]),
            "removed": before - len(data["projects"]),
        }
