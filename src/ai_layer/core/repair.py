from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ai_layer.core.config import get_settings
from ai_layer.core.paths import project_local_path, project_mode
from ai_layer.core.registry import (
    get_registered_project,
    is_ephemeral_project_root,
    list_registered_projects,
    unregister_project,
)
from ai_layer.core.service import sync_project_integrations
from ai_layer.integrations.service import remove_project_integrations
from ai_layer.privacy.service import (
    git_privacy_guard_status,
    install_git_privacy_guard,
    privacy_check,
    remove_git_privacy_guard,
    repository_footprint,
)


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _project_id(root: Path) -> str | None:
    entry = get_registered_project(root) or {}
    value = str(entry.get("project_id") or "").strip()
    return value or None


def _validated_owned_state(path: Path, root: Path, project_id: str | None) -> bool:
    """Validate that an existing directory is AI Layer state owned by exactly this root."""
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"Refusing to archive unsafe AI Layer project state: {path}")
    try:
        nested_symlink = next((item for item in path.rglob("*") if item.is_symlink()), None)
    except OSError as exc:
        raise RuntimeError(
            f"Refusing to archive unreadable AI Layer project state: {path}"
        ) from exc
    if nested_symlink is not None:
        raise RuntimeError(
            f"Refusing to archive symlinked AI Layer project state: {nested_symlink}"
        )
    config = path / "project.yaml"
    if config.is_symlink() or not config.is_file():
        raise RuntimeError(f"Refusing to archive unverified AI Layer project state: {path}")
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RuntimeError(
            f"Refusing to archive unreadable AI Layer project state: {path}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Refusing to archive invalid AI Layer project state: {path}")
    configured_root = str(data.get("root") or "").strip()
    if not configured_root or Path(configured_root).expanduser().resolve() != root:
        raise RuntimeError(f"Refusing to archive AI Layer state owned by another root: {path}")
    configured_id = str(data.get("project_id") or "").strip()
    if project_id and configured_id and configured_id != project_id:
        raise RuntimeError(f"Refusing to archive AI Layer state with mismatched project_id: {path}")
    return True


def _recovery_dir(root: Path, project_id: str | None, reason: str) -> Path:
    settings = get_settings()
    base = settings.home / "recovery" / reason
    if base.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer recovery root: {base}")
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    safe_name = root.name.replace(os.sep, "-") or "project"
    token = (project_id or "no-id")[:12]
    candidate = base / f"{_utc_stamp()}-{safe_name}-{token}"
    suffix = 1
    while candidate.exists():
        candidate = base / f"{_utc_stamp()}-{safe_name}-{token}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, mode=0o700)
    return candidate


def _archive_dir(source: Path, destination_root: Path, name: str) -> str:
    destination = destination_root / name
    shutil.move(str(source), str(destination))
    return str(destination)


def _registered_overlap_groups() -> list[tuple[Path, list[Path]]]:
    """Return canonical parent roots and every registered descendant below each parent."""
    roots = sorted(
        {
            Path(str(item["root"])).expanduser().resolve()
            for item in list_registered_projects()
            if item.get("root")
        },
        key=lambda path: (len(path.parts), str(path)),
    )
    detached: set[Path] = set()
    groups: list[tuple[Path, list[Path]]] = []
    for index, parent in enumerate(roots):
        if parent in detached:
            continue
        children: list[Path] = []
        for child in roots[index + 1 :]:
            if child in detached:
                continue
            try:
                child.relative_to(parent)
            except ValueError:
                continue
            children.append(child)
            detached.add(child)
        if children:
            groups.append((parent, children))
    return groups


def detach_nested_registration(child: str | Path, parent: str | Path) -> dict:
    """Detach an accidental nested registration without deleting repository/user code.

    AI-owned project state is archived under ~/.ai-layer/recovery rather than destroyed. The
    database row is intentionally preserved; durable registry tombstones prevent legacy hydration
    from re-attaching the child automatically.
    """
    child_root = Path(child).expanduser().resolve()
    parent_root = Path(parent).expanduser().resolve()
    child_root.relative_to(parent_root)
    entry = get_registered_project(child_root)
    if entry is None:
        return {"root": str(child_root), "changed": False, "reason": "not registered"}

    project_id = _project_id(child_root)
    local_meta = project_local_path(child_root, ".ai-layer")
    local_owned = _validated_owned_state(local_meta, child_root, project_id)

    external_meta: Path | None = None
    external_owned = False
    if project_id:
        base = get_settings().projects_state_dir
        if base.is_symlink():
            raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
        external_meta = base / project_id
        try:
            external_meta.resolve().relative_to(base.expanduser().resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"Unsafe external AI Layer project state path: {external_meta}"
            ) from exc
        external_owned = _validated_owned_state(external_meta, child_root, project_id)

    # Remove only bridges managed by AI Layer. This preserves any surrounding user content.
    guard = remove_git_privacy_guard(child_root)
    integrations = remove_project_integrations(child_root)

    # Tombstone first so moving strict-private external state cannot cause registry resurrection.
    registry = unregister_project(child_root)

    archived: list[str] = []
    if local_owned or external_owned:
        recovery = _recovery_dir(child_root, project_id, "nested-projects")
        if local_owned:
            archived.append(_archive_dir(local_meta, recovery, "local-state"))
        if external_owned and external_meta is not None:
            archived.append(_archive_dir(external_meta, recovery, "external-state"))
    return {
        "root": str(child_root),
        "parent": str(parent_root),
        "changed": True,
        "strategy": "keep-parent-detach-nested",
        "integrations": integrations,
        "privacy_guard": guard,
        "archived_state": archived,
        "database_state_preserved": True,
        "registry": registry,
    }


def _migrate_legacy_local_state(root: Path) -> dict:
    """Move verified legacy repository-local state to canonical machine-side project storage."""
    local_meta = project_local_path(root, ".ai-layer")
    if not local_meta.exists() and not local_meta.is_symlink():
        return {"migrated": False, "destination": None, "archived": []}
    project_id = _project_id(root)
    if not project_id:
        raise RuntimeError(
            f"Registered project lacks project_id; refusing to move legacy state: {root}"
        )
    if not _validated_owned_state(local_meta, root, project_id):
        return {"migrated": False, "destination": None, "archived": []}

    base = get_settings().projects_state_dir
    if base.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
    destination = base / project_id
    try:
        destination.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise RuntimeError(
            f"AI Layer machine state must be outside the registered project root: {destination}"
        )
    try:
        destination.resolve().relative_to(base.expanduser().resolve())
    except ValueError as exc:
        raise RuntimeError(f"Unsafe external AI Layer project state path: {destination}") from exc

    if destination.exists() or destination.is_symlink():
        if not _validated_owned_state(destination, root, project_id):
            raise RuntimeError(f"Canonical project state is not safely owned: {destination}")
        recovery = _recovery_dir(root, project_id, "legacy-local-state")
        archived = _archive_dir(local_meta, recovery, "local-state")
        return {"migrated": False, "destination": str(destination), "archived": [archived]}

    base.mkdir(parents=True, exist_ok=True)
    shutil.move(str(local_meta), str(destination))
    try:
        os.chmod(destination, 0o700)
    except OSError:
        pass
    return {"migrated": True, "destination": str(destination), "archived": []}


def repair_project(root: str | Path, *, sync: bool = True) -> dict:
    path = Path(root).expanduser().resolve()
    result: dict = {"root": str(path), "exists": path.exists(), "actions": [], "manual": []}
    if not path.exists():
        result["ok"] = False
        result["manual"].append("registered project path does not exist")
        return result
    if get_registered_project(path) is None:
        result["ok"] = False
        result["manual"].append("project is not registered")
        return result
    try:
        mode = project_mode(path)
        layout = _migrate_legacy_local_state(path)
        if layout.get("migrated"):
            result["actions"].append("migrated legacy local .ai-layer state to machine storage")
            result["state_destination"] = layout.get("destination")
        if layout.get("archived"):
            result["actions"].append("archived duplicate legacy local .ai-layer state")
            result["archived_state"] = layout["archived"]

        remove_project_integrations(path)
        result["actions"].append("removed repository-local AI Layer integration residue")
        if mode == "strict-private":
            guard = install_git_privacy_guard(path)
            result["git_guard"] = guard
            if not guard.get("ready", False):
                result["manual"].append(
                    f"Git privacy guard conflict: {guard.get('reason') or guard}"
                )
        else:
            remove_git_privacy_guard(path)
        if sync:
            synced = sync_project_integrations(path)
            result["sync"] = synced
            result["actions"].append("synchronized project integrations")
    except Exception as exc:
        result["ok"] = False
        result["manual"].append(str(exc))
        return result

    if project_mode(path) == "strict-private":
        footprint = repository_footprint(path)
        changed_check = privacy_check(path)
        guard_state = git_privacy_guard_status(path)
        result["footprint"] = footprint
        result["privacy_check"] = changed_check
        result["git_guard"] = guard_state
        if footprint.get("repository_ai_artifacts"):
            result["manual"].append(
                "repository still contains AI Layer artifacts: "
                + ", ".join(footprint["repository_ai_artifacts"])
            )
        if footprint.get("tracked_ai_or_provenance"):
            result["manual"].append(
                "tracked files contain AI Layer/AI provenance and require user review: "
                + ", ".join(footprint["tracked_ai_or_provenance"])
            )
        if footprint.get("tracked_unscannable"):
            result["manual"].append(
                "tracked files could not be privacy-scanned safely: "
                + ", ".join(footprint["tracked_unscannable"])
            )
        if not changed_check.get("ok", False):
            paths = sorted(
                {
                    str(item.get("path"))
                    for item in changed_check.get("violations", [])
                    if item.get("path")
                }
            )
            result["manual"].append(
                "changed/staged privacy violations require user review"
                + (": " + ", ".join(paths) if paths else "")
            )
        if not guard_state.get("ready", False):
            result["manual"].append("Git privacy guard is not ready")

    result["ok"] = not result["manual"]
    return result


def prune_non_durable_registrations() -> dict:
    """Forget ephemeral test roots and missing registrations before machine repair."""
    from ai_layer.application.projects import remove_project

    pruned: list[dict] = []
    for item in list(list_registered_projects()):
        raw = str(item.get("root") or "").strip()
        if not raw:
            continue
        resolved = Path(raw).expanduser().resolve()
        if is_ephemeral_project_root(resolved):
            reason = "ephemeral-test-root"
        elif not resolved.exists():
            reason = "missing-root"
        else:
            continue
        try:
            result = remove_project(resolved)
        except Exception as exc:
            result = {
                "removed": False,
                "registry": unregister_project(resolved),
                "warning": str(exc),
            }
        pruned.append({"root": str(resolved), "reason": reason, **result})
    return {"count": len(pruned), "items": pruned}


def repair_registered_projects(*, sync: bool = True) -> dict:
    """Repair all safe machine/project drift and return only unresolved user-owned blockers."""
    pruned = prune_non_durable_registrations()
    nested: list[dict] = []
    nested_errors: list[dict] = []
    blocked_nested_roots: set[str] = set()
    for parent, children in _registered_overlap_groups():
        for child in sorted(children, key=lambda p: (len(p.parts), str(p)), reverse=True):
            try:
                nested.append(detach_nested_registration(child, parent))
            except Exception as exc:
                blocked_nested_roots.add(str(child))
                nested_errors.append({"root": str(child), "parent": str(parent), "error": str(exc)})

    projects: list[dict] = []
    for item in list_registered_projects():
        root = Path(str(item.get("root") or "")).expanduser().resolve()
        if str(root) in blocked_nested_roots:
            projects.append(
                {
                    "root": str(root),
                    "exists": root.exists(),
                    "ok": False,
                    "actions": [],
                    "manual": [
                        "nested registration could not be detached safely; no integration sync was attempted"
                    ],
                }
            )
            continue
        projects.append(repair_project(root, sync=sync))

    unresolved = list(nested_errors)
    nested_error_roots = {str(item.get("root")) for item in nested_errors}
    unresolved.extend(
        {"root": item["root"], "manual": item.get("manual", [])}
        for item in projects
        if not item.get("ok", False) and str(item.get("root")) not in nested_error_roots
    )
    return {
        "ok": not unresolved,
        "pruned_registrations": pruned,
        "nested_detached": len(nested),
        "nested": nested,
        "projects_checked": len(projects),
        "projects_healthy": sum(1 for item in projects if item.get("ok", False)),
        "projects": projects,
        "unresolved": unresolved,
    }
