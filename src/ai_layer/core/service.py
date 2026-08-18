from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, overload

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_layer import __version__
from ai_layer.core.config import get_settings
from ai_layer.core.paths import (
    normalize_root,
    project_config_path,
    project_local_path,
    project_meta_dir,
    project_mode,
    project_provenance,
    require_initialized,
)
from ai_layer.core.registry import (
    get_registered_project,
    overlapping_registered_projects,
    register_project,
    unregister_project,
)
from ai_layer.db.models import Project, ProjectSkill
from ai_layer.integrations.service import (
    INTEGRATION_TEMPLATE_VERSION,
    remove_project_integrations,
)
from ai_layer.memory.freshness import (
    embedding_state_matches,
    load_scan_metadata,
    scan_until_stable,
    scanner_state_matches,
)
from ai_layer.memory.knowledge_store import knowledge_status
from ai_layer.memory.locking import project_refresh_lock
from ai_layer.observability.events import observed_operation
from ai_layer.privacy.service import (
    install_git_privacy_guard,
    is_git_repository,
    remove_git_privacy_guard,
)
from ai_layer.skills.native import sync_project_native_skills

PROJECT_RULES = """# Project-specific rules

Add only rules that are specific to this repository. Global engineering policy is loaded separately.
"""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _read_project_config(path: Path) -> dict:
    file = project_config_path(path)
    if not file.exists():
        return {}
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_project_config(path: Path, data: dict) -> None:
    file = project_config_path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    fd, temp_name = tempfile.mkstemp(prefix=file.name + ".", suffix=".tmp", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, file)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _legacy_local_state_owned(path: Path, root: Path, project_id: str) -> bool:
    """Recognize legacy repository-local state without claiming unrelated user content."""
    if not path.exists():
        return False
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer project metadata: {path}")
    if not path.is_dir():
        return False
    config = path / "project.yaml"
    if not config.is_file() or config.is_symlink():
        return False
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    configured_root = str(data.get("root") or "").strip()
    if not configured_root or Path(configured_root).expanduser().resolve() != root:
        return False
    configured_id = str(data.get("project_id") or "").strip()
    return not configured_id or configured_id == project_id


def _ensure_rules(meta: Path) -> None:
    rules_path = meta / "rules.md"
    if rules_path.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer project policy: {rules_path}")
    if rules_path.exists():
        return
    fd, temp_name = tempfile.mkstemp(
        prefix=rules_path.name + ".", suffix=".tmp", dir=rules_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(PROJECT_RULES)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, rules_path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


@overload
def get_project(
    db: Session, root: str | Path | None = None, required: Literal[True] = True
) -> Project: ...


@overload
def get_project(
    db: Session, root: str | Path | None, required: Literal[False]
) -> Project | None: ...


def get_project(
    db: Session, root: str | Path | None = None, required: bool = True
) -> Project | None:
    path = normalize_root(root)
    project = db.scalar(select(Project).where(Project.root_path == str(path)))
    if required and project is None:
        raise RuntimeError(f"Project is not registered: {path}. Run `ai-layer init`.")
    return project


def sync_project_integrations(root: str | Path | None = None) -> dict:
    path = normalize_root(root)
    require_initialized(path)
    with observed_operation(
        path,
        category="project",
        operation="sync",
        client="cli",
        start_metrics={"template_version": INTEGRATION_TEMPLATE_VERSION},
    ) as observed:
        config = _read_project_config(path)
        mode = project_mode(path)
        remove_project_integrations(path)
        result = {
            "template_version": INTEGRATION_TEMPLATE_VERSION,
            "ai_layer_version": __version__,
            "mode": mode,
            "repository_writes": False,
            "native_skills": sync_project_native_skills(path),
        }
        if mode == "strict-private":
            guard = install_git_privacy_guard(path)
            if not guard.get("ready", False):
                raise RuntimeError(
                    f"Strict-private Git privacy guard is not ready: {guard.get('reason') or guard}"
                )
            result["git_guard"] = guard
        else:
            remove_git_privacy_guard(path)
        config.update(
            {
                "ai_layer_version": __version__,
                "integration_template_version": INTEGRATION_TEMPLATE_VERSION,
                "integrations_synced_at": _utcnow(),
                "root": str(path),
                "mode": mode,
                "provenance": project_provenance(path),
            }
        )
        _write_project_config(path, config)
        register_project(
            path,
            config.get("project_id"),
            config.get("name") or path.name,
            mode=mode,
            provenance=project_provenance(path),
        )
        observed["metrics"] = {"template_version": INTEGRATION_TEMPLATE_VERSION}
        return {"root": str(path), **result}


def init_project(
    db: Session,
    root: str | Path | None = None,
    name: str | None = None,
    *,
    private: bool = False,
    external: bool = False,
) -> Project:
    path = normalize_root(root)
    overlaps = overlapping_registered_projects(path)
    if overlaps:
        roots = ", ".join(str(item.get("root")) for item in overlaps)
        raise RuntimeError(
            f"Project root overlaps an already registered project: {path} <-> {roots}. "
            "Use one project root, or unregister the accidental nested/parent registration first."
        )
    if private and external:
        raise ValueError("private and external attachment modes are mutually exclusive")
    existing = get_registered_project(path) or {}
    if private:
        mode, provenance = "strict-private", "forbid"
    elif external:
        mode, provenance = "external", "allow"
    else:
        mode = str(existing.get("mode") or "standard")
        provenance = str(existing.get("provenance") or "allow")
    local_meta = project_local_path(path, ".ai-layer")
    if local_meta.is_symlink():
        raise RuntimeError(f"Refusing symlinked AI Layer project metadata: {local_meta}")

    # Strict-private alone needs a repository-level precondition because it installs a Git guard.
    # Standard and external attachment are zero-footprint and have no repository integration targets.
    if mode == "strict-private" and not is_git_repository(path):
        raise RuntimeError(
            "Strict-private initialization requires an existing Git repository so privacy "
            "enforcement can fail closed. Initialize Git first, then retry."
        )

    project = get_project(db, path, required=False)
    if project is None:
        project = Project(
            name=name or path.name,
            root_path=str(path),
            languages={},
            dependencies={},
            architecture_summary="Not scanned yet.",
            project_intelligence={},
        )
        db.add(project)
        db.flush()
    db.commit()

    # Registry publishes durable project identity before resolving machine-side state. Existing
    # repository-local state from older standard installs is copied out before repository cleanup.
    register_project(path, str(project.id), project.name, mode=mode, provenance=provenance)
    meta = project_meta_dir(path)
    meta.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(meta, 0o700)
    except OSError:
        pass
    legacy_local_owned = _legacy_local_state_owned(local_meta, path, str(project.id))
    if legacy_local_owned and local_meta.resolve() != meta.resolve():
        symlinks = [item for item in local_meta.rglob("*") if item.is_symlink()]
        if symlinks:
            raise RuntimeError(f"Refusing to migrate symlinked AI Layer state: {symlinks[0]}")
        shutil.copytree(local_meta, meta, dirs_exist_ok=True)

    (meta / "memory").mkdir(parents=True, exist_ok=True)
    (meta / "sessions").mkdir(parents=True, exist_ok=True)
    (meta / "tasks").mkdir(parents=True, exist_ok=True)
    config = {
        "version": 2,
        "project_id": str(project.id),
        "name": project.name,
        "root": str(path),
        "mode": mode,
        "provenance": provenance,
        "ai_layer_version": __version__,
        "integration_template_version": INTEGRATION_TEMPLATE_VERSION,
        "integrations_synced_at": _utcnow(),
        "skill_routing": "host-native",
    }
    _write_project_config(path, config)
    _ensure_rules(meta)

    remove_project_integrations(path)
    sync_project_native_skills(path)
    if legacy_local_owned and local_meta.resolve() != meta.resolve():
        shutil.rmtree(local_meta)
    if mode == "strict-private":
        guard = install_git_privacy_guard(path)
        if not guard.get("ready", False):
            raise RuntimeError(
                f"Strict-private Git privacy guard is not ready: {guard.get('reason') or guard}"
            )
    else:
        remove_git_privacy_guard(path)
    register_project(path, str(project.id), project.name, mode=mode, provenance=provenance)
    return project


def _validated_ai_state_dir(path: Path, root: Path, project_id: str | None) -> bool:
    """Return True only when an existing directory is demonstrably owned by this exact project."""
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"Refusing to purge unsafe AI Layer project state: {path}")
    config = path / "project.yaml"
    if config.is_symlink() or not config.is_file():
        raise RuntimeError(f"Refusing to purge unverified AI Layer project state: {path}")
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Refusing to purge unreadable AI Layer project state: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Refusing to purge invalid AI Layer project state: {path}")
    configured_root = str(data.get("root") or "").strip()
    if not configured_root or Path(configured_root).expanduser().resolve() != root:
        raise RuntimeError(f"Refusing to purge AI Layer state owned by another root: {path}")
    configured_id = str(data.get("project_id") or "").strip()
    if project_id and configured_id and configured_id != project_id:
        raise RuntimeError(f"Refusing to purge AI Layer state with mismatched project_id: {path}")
    return True


def remove_project_registration(db: Session, root: str | Path) -> dict:
    """Purge AI Layer-owned state for one exact root and durably forget its registration."""
    path = normalize_root(root)
    entry = get_registered_project(path) or {}
    project = get_project(db, path, required=False)
    project_id = (
        str(entry.get("project_id") or (project.id if project is not None else "")).strip() or None
    )

    if not entry and project is None:
        result = unregister_project(path)
        return {
            "root": str(path),
            "removed": False,
            "reason": "project was not registered",
            "registry": result,
        }

    # Validate every state directory before mutating repository/configuration so failures are fail-closed.
    local_meta = project_local_path(path, ".ai-layer")
    remove_local = _validated_ai_state_dir(local_meta, path, project_id)
    external_meta: Path | None = None
    remove_external = False
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
        remove_external = _validated_ai_state_dir(external_meta, path, project_id)

    privacy_guard = remove_git_privacy_guard(path)
    integrations = remove_project_integrations(path)
    removed_state: list[str] = []
    if remove_local:
        shutil.rmtree(local_meta)
        removed_state.append(str(local_meta))
    if remove_external and external_meta is not None:
        shutil.rmtree(external_meta)
        removed_state.append(str(external_meta))

    db_deleted = 0
    if project is not None:
        db.execute(delete(Project).where(Project.id == project.id))
        db_deleted = 1
        db.commit()

    registry = unregister_project(path)
    return {
        "root": str(path),
        "removed": True,
        "project_id": project_id,
        "integrations": integrations,
        "privacy_guard": privacy_guard,
        "state_dirs_removed": removed_state,
        "database_rows_removed": db_deleted,
        "registry": registry,
    }


def scan_registered_project(db: Session, root: str | Path | None = None) -> dict:
    path = normalize_root(root)
    require_initialized(path)
    project = get_project(db, path)
    assert project is not None
    with project_refresh_lock(path):
        previous_embedding = load_scan_metadata(project).get("embedding")
        embedding_matches = embedding_state_matches(project)
        scanner_matches = scanner_state_matches(project)
        embedding_drift = previous_embedding is not None and not embedding_matches
        scanner_drift = not scanner_matches
        reason = (
            "embedding_configuration_changed"
            if embedding_drift
            else "scanner_schema_changed"
            if scanner_drift
            else "manual_scan"
        )
        # A manual rebuild must not publish a new vector-space signature while explicit
        # decisions still use the previous space. Legacy/missing signatures are re-embedded too.
        with observed_operation(
            path,
            category="memory",
            operation="rebuild",
            client="cli",
            start_metrics={"reason": reason},
        ) as observed:
            stats, snapshot, attempts = scan_until_stable(
                db,
                project,
                path,
                reason=reason,
                reembed_decisions=not embedding_matches,
                force_reparse=scanner_drift,
            )
            observed["metrics"] = {
                "reason": snapshot["reason"],
                "files": stats.files,
                "knowledge_items": stats.knowledge_items,
                "embeddings_reused": getattr(stats, "embeddings_reused", 0),
                "embeddings_regenerated": getattr(stats, "embeddings_regenerated", 0),
                "knowledge_reembedded": getattr(stats, "knowledge_reembedded", 0),
                "legacy_source_knowledge_removed": getattr(
                    stats, "legacy_source_knowledge_removed", 0
                ),
                "knowledge_cards_staled": getattr(stats, "knowledge_cards_staled", 0),
                "refresh_attempts": attempts,
            }
        state = knowledge_status(db, project)
        result = {
            "scanned_at": snapshot["scanned_at"],
            "scan_role": "deterministic_repository_evidence",
            "raw_source_semantic_index": False,
            "reason": snapshot["reason"],
            "files": stats.files,
            "knowledge_items": stats.knowledge_items,
            "languages": stats.languages,
            "dependencies": stats.dependencies,
            "selected_skills": stats.selected_skills,
            "source_files": getattr(stats, "source_files", stats.files),
            "changes": getattr(stats, "changes", {}),
            "hashes_calculated": getattr(stats, "hashes_calculated", 0),
            "embeddings_reused": getattr(stats, "embeddings_reused", 0),
            "embeddings_regenerated": getattr(stats, "embeddings_regenerated", 0),
            "raw_source_embeddings_regenerated": 0,
            "legacy_source_knowledge_removed": getattr(stats, "legacy_source_knowledge_removed", 0),
            "knowledge_cards_staled": getattr(stats, "knowledge_cards_staled", 0),
            "knowledge_reembedded": getattr(stats, "knowledge_reembedded", 0),
            "refresh_attempts": attempts,
            "knowledge_state": state,
        }
        if state["onboarding_recommended"]:
            result["next_step"] = {
                "action": "project_knowledge_onboarding",
                "message": (
                    "No review-gated Project Knowledge overview is VERIFIED yet. When useful, ask a strong host model "
                    "to create an explicit standard managed onboarding task; the mapper writes evidence-backed DRAFT "
                    "cards and an independent reviewer must pass them before publication. Scan itself never authors "
                    "semantic project truth."
                ),
            }
        return result


def project_info(db: Session, root: str | Path | None = None) -> dict:
    project = get_project(db, root)
    assert project is not None
    legacy_skill_rows = db.scalars(
        select(ProjectSkill).where(ProjectSkill.project_id == project.id)
    ).all()
    return {
        "id": str(project.id),
        "name": project.name,
        "root_path": project.root_path,
        "languages": project.languages,
        "dependencies": project.dependencies,
        "architecture_summary": project.architecture_summary,
        "architecture_summary_assurance": "scanner_evidence_not_reviewed_project_knowledge",
        "project_intelligence": project.project_intelligence or {},
        "project_intelligence_assurance": "scanner_evidence_not_reviewed_project_knowledge",
        "knowledge_state": knowledge_status(db, project),
        # Compatibility field: active project relevance is no longer represented by ProjectSkill rows.
        "skills": [],
        "skill_routing": {
            "owner": "host-native",
            "ai_layer_planner_active": False,
            "automatic_domain_skill_injection": False,
            "legacy_project_skill_rows": len(legacy_skill_rows),
        },
        "updated_at": project.updated_at.isoformat(),
    }
