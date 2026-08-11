from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ai_layer.core.mcp_process import current_mcp_session_id
from ai_layer.core.paths import project_state_path
from ai_layer.db.models import Project
from ai_layer.memory.embeddings import embedding_signature
from ai_layer.memory.identity import (
    RepositoryChangedDuringScan,
    repository_probe,
    state_hints_match,
)
from ai_layer.memory.identity import (
    build_file_hints as build_file_state,
)
from ai_layer.memory.indexer import scan_project
from ai_layer.memory.locking import project_refresh_lock
from ai_layer.memory.source import ScanLimitExceeded
from ai_layer.memory.versioning import CONTENT_IDENTITY_VERSION, SCANNER_SCHEMA_VERSION
from ai_layer.observability.events import observed_operation

STATE_FILE = "file_state.json"
SCAN_FILE = "scan.json"
MAX_REPORTED_CHANGES = 12
MAX_STABLE_SCAN_ATTEMPTS = 3


def _memory_dir(project: Project) -> Path:
    path = project_state_path(project.root_path, "memory")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_json(path: Path, payload: dict, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def load_file_state(project: Project) -> dict[str, dict[str, int]]:
    _memory_dir(project)
    path = project_state_path(project.root_path, "memory", STATE_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_scan_metadata(project: Project) -> dict:
    _memory_dir(project)
    path = project_state_path(project.root_path, "memory", SCAN_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def embedding_state_matches(project: Project) -> bool:
    return load_scan_metadata(project).get("embedding") == embedding_signature()


def scanner_state_matches(project: Project) -> bool:
    metadata = load_scan_metadata(project)
    return (
        metadata.get("content_identity_version") == CONTENT_IDENTITY_VERSION
        and metadata.get("scanner_schema") == SCANNER_SCHEMA_VERSION
    )


def file_state_changes(previous: dict, current: dict) -> dict:
    """Report physical candidates from cheap metadata; content hashes are verified during refresh."""
    previous_keys = set(previous)
    current_keys = set(current)
    added = sorted(current_keys - previous_keys)
    deleted = sorted(previous_keys - current_keys)
    modified = []
    for path in sorted(previous_keys & current_keys):
        old = previous.get(path) or {}
        new = current.get(path) or {}
        keys = ("size", "mtime_ns", "ctime_ns")
        if any(int(old.get(key, -1)) != int(new.get(key, -1)) for key in keys):
            modified.append(path)
    total = len(added) + len(modified) + len(deleted)
    return {
        "added": added[:MAX_REPORTED_CHANGES],
        "modified": modified[:MAX_REPORTED_CHANGES],
        "deleted": deleted[:MAX_REPORTED_CHANGES],
        "renamed": [],
        "total": total,
        "truncated": any(len(items) > MAX_REPORTED_CHANGES for items in (added, modified, deleted)),
    }


def write_scan_metadata(
    project: Project, stats, *, reason: str, repo_probe: dict | None = None
) -> dict:
    memory_dir = _memory_dir(project)
    snapshot = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "files": stats.files,
        "knowledge_items": stats.knowledge_items,
        "languages": stats.languages,
        "dependencies": stats.dependencies,
        "selected_skills": stats.selected_skills,
        "embedding": embedding_signature(),
        "content_identity_version": CONTENT_IDENTITY_VERSION,
        "scanner_schema": SCANNER_SCHEMA_VERSION,
        "repository_probe": repo_probe,
        "incremental": {
            "source_files": getattr(stats, "source_files", stats.files),
            "changes": getattr(stats, "changes", {}),
            "hashes_calculated": getattr(stats, "hashes_calculated", 0),
            "embeddings_reused": getattr(stats, "embeddings_reused", 0),
            "embeddings_regenerated": getattr(stats, "embeddings_regenerated", 0),
            "decisions_reembedded": getattr(stats, "decisions_reembedded", 0),
            "knowledge_reembedded": getattr(stats, "knowledge_reembedded", 0),
            "raw_source_embeddings_regenerated": 0,
            "legacy_source_knowledge_removed": getattr(stats, "legacy_source_knowledge_removed", 0),
            "knowledge_cards_staled": getattr(stats, "knowledge_cards_staled", 0),
        },
    }
    # `file_state.json` is the freshness commit marker, so write it last. A failed auxiliary
    # `scan.json` write must not cause later reads to skip a refresh.
    _atomic_write_json(memory_dir / SCAN_FILE, snapshot)
    _atomic_write_json(memory_dir / STATE_FILE, stats.file_state, sort_keys=True)
    return snapshot


def scan_until_stable(
    db: Session,
    project: Project,
    root: Path,
    *,
    reason: str,
    max_attempts: int = MAX_STABLE_SCAN_ATTEMPTS,
    reembed_decisions: bool = False,
    force_reparse: bool = False,
):
    """Scan/commit only when the repository still matches the indexed snapshot.

    An unstable attempt is rolled back before it becomes visible. `file_state.json` advances only
    after one verified repository snapshot has committed.
    """
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            stats = scan_project(
                db,
                project,
                root,
                reembed_decisions=reembed_decisions,
                force_reparse=force_reparse,
            )
            probe_before_verify = repository_probe(root)
            observed = build_file_state(root)
            probe_after_verify = repository_probe(root)
        except RepositoryChangedDuringScan:
            db.rollback()
            continue
        except ScanLimitExceeded:
            db.rollback()
            raise
        probe_stable = (
            probe_before_verify is None
            or probe_after_verify is None
            or probe_before_verify == probe_after_verify
        )
        if state_hints_match(stats.file_state, observed) and probe_stable:
            # Publish the stable database state only after repository verification. This keeps an
            # unstable attempt invisible to concurrent readers that already passed freshness.
            db.commit()
            snapshot = write_scan_metadata(
                project, stats, reason=reason, repo_probe=probe_after_verify
            )
            return stats, snapshot, attempt
        db.rollback()
    raise RuntimeError(
        f"Repository changed during AI Layer memory refresh for {root}; "
        f"could not obtain a stable scan after {attempts} attempts. Retry after writes settle."
    )


def probe_memory_freshness(project: Project) -> dict:
    """Cheap, non-blocking freshness view for interactive MCP requests.

    This intentionally does not walk the repository or acquire the refresh lock. Git repositories
    use the existing generation fingerprint; uncertainty is reported as stale/unknown and a
    persistent runtime may rebuild in the background.
    """
    state_path = project_state_path(project.root_path, "memory", STATE_FILE)
    state_exists = state_path.exists()
    metadata = load_scan_metadata(project)
    fast_fresh, current_probe, metadata = _fast_probe_fresh(
        project, state_exists=state_exists, probe_timeout_seconds=0.75
    )
    files = int(metadata.get("files") or 0)
    if fast_fresh:
        return {
            "status": "fresh",
            "refreshed": False,
            "files": files,
            "snapshot_available": True,
            "freshness_probe": "git",
            "waited_for_refresh": False,
        }
    stored_probe = metadata.get("repository_probe") if isinstance(metadata, dict) else None
    changed_paths: list[str] = []
    if isinstance(current_probe, dict):
        dirty = current_probe.get("dirty")
        if isinstance(dirty, dict):
            changed_paths.extend(str(path) for path in dirty.keys())
        if isinstance(stored_probe, dict) and stored_probe.get("head") != current_probe.get("head"):
            changed_paths.append("<committed-history-changed>")
    return {
        "status": "stale" if state_exists else "missing",
        "refreshed": False,
        "files": files,
        "snapshot_available": bool(state_exists and metadata),
        "freshness_probe": "git" if current_probe is not None else "unknown",
        "changed_paths": sorted(set(changed_paths))[:MAX_REPORTED_CHANGES],
        "waited_for_refresh": False,
    }


def _fast_probe_fresh(
    project: Project, *, state_exists: bool, probe_timeout_seconds: float | None = None
) -> tuple[bool, dict | None, dict]:
    metadata = load_scan_metadata(project)
    if not state_exists:
        current_probe = None
    elif probe_timeout_seconds is None:
        current_probe = repository_probe(Path(project.root_path))
    else:
        current_probe = repository_probe(
            Path(project.root_path), budget_seconds=probe_timeout_seconds
        )
    stored_probe = metadata.get("repository_probe")
    fresh = bool(
        state_exists
        and stored_probe
        and current_probe
        and stored_probe == current_probe
        and metadata.get("embedding") == embedding_signature()
        and metadata.get("content_identity_version") == CONTENT_IDENTITY_VERSION
        and metadata.get("scanner_schema") == SCANNER_SCHEMA_VERSION
    )
    return fresh, current_probe, metadata


def ensure_memory_fresh(db: Session, project: Project) -> dict:
    """Refresh deterministic evidence and invalidate curated knowledge when source changes.

    Git repositories use a cheap generation probe for the common unchanged path. Any missing or
    uncertain probe falls back to the full scanner-visible file-state comparison, preserving the
    existing correctness boundary for non-Git repositories and legacy state. Embedding drift
    re-embeds only durable decisions and curated Project Knowledge, never current-source chunks.
    """
    root = Path(project.root_path)
    _memory_dir(project)
    state_path = project_state_path(project.root_path, "memory", STATE_FILE)
    state_exists = state_path.exists()
    fast_fresh, _, metadata = _fast_probe_fresh(project, state_exists=state_exists)
    if fast_fresh:
        return {
            "status": "fresh",
            "refreshed": False,
            "files": int(metadata.get("files") or len(load_file_state(project))),
            "waited_for_refresh": False,
            "freshness_probe": "git",
        }

    previous = load_file_state(project)
    current = build_file_state(root)
    embedding_matches = state_exists and embedding_state_matches(project)
    scanner_matches = state_exists and scanner_state_matches(project)
    if (
        state_exists
        and state_hints_match(previous, current)
        and embedding_matches
        and scanner_matches
    ):
        return {
            "status": "fresh",
            "refreshed": False,
            "files": len(current),
            "waited_for_refresh": False,
        }

    # A second process can reach this point at the same time. Serialize rebuilds, then re-check the
    # state after acquiring the lock so only one process performs DELETE/UPSERT/index work.
    with project_refresh_lock(root) as lock:
        state_exists = state_path.exists()
        fast_fresh, _, metadata = _fast_probe_fresh(project, state_exists=state_exists)
        if fast_fresh:
            return {
                "status": "fresh",
                "refreshed": False,
                "files": int(metadata.get("files") or len(load_file_state(project))),
                "waited_for_refresh": bool(lock.get("waited")),
                "freshness_probe": "git",
            }
        previous = load_file_state(project)
        current = build_file_state(root)
        embedding_matches = state_exists and embedding_state_matches(project)
        scanner_matches = state_exists and scanner_state_matches(project)
        if (
            state_exists
            and state_hints_match(previous, current)
            and embedding_matches
            and scanner_matches
        ):
            return {
                "status": "fresh",
                "refreshed": False,
                "files": len(current),
                "waited_for_refresh": bool(lock.get("waited")),
            }

        embedding_drift = state_exists and not embedding_matches
        scanner_drift = state_exists and not scanner_matches
        if embedding_drift:
            reason = "embedding_configuration_changed"
        elif scanner_drift:
            reason = "scanner_schema_changed"
        else:
            reason = "automatic_freshness_refresh" if state_exists else "missing_or_legacy_state"
        with observed_operation(
            root,
            category="memory",
            operation="refresh",
            session_id=current_mcp_session_id(),
            start_metrics={
                "reason": reason,
                "candidate_files": len(current),
                "waited_for_lock": bool(lock.get("waited")),
            },
        ) as observed:
            stats, snapshot, attempts = scan_until_stable(
                db,
                project,
                root,
                reason=reason,
                reembed_decisions=embedding_drift,
                force_reparse=scanner_drift,
            )
            observed["metrics"] = {
                "reason": snapshot["reason"],
                "files": stats.files,
                "knowledge_items": stats.knowledge_items,
                "hashes_calculated": getattr(stats, "hashes_calculated", 0),
                "embeddings_reused": getattr(stats, "embeddings_reused", 0),
                "embeddings_regenerated": getattr(stats, "embeddings_regenerated", 0),
                "knowledge_reembedded": getattr(stats, "knowledge_reembedded", 0),
                "legacy_source_knowledge_removed": getattr(
                    stats, "legacy_source_knowledge_removed", 0
                ),
                "knowledge_cards_staled": getattr(stats, "knowledge_cards_staled", 0),
                "refresh_attempts": attempts,
                "waited_for_lock": bool(lock.get("waited")),
            }
        return {
            "status": "refreshed",
            "refreshed": True,
            "files": stats.files,
            "knowledge_items": stats.knowledge_items,
            "reason": snapshot["reason"],
            "changes": getattr(stats, "changes", {}),
            "hashes_calculated": getattr(stats, "hashes_calculated", 0),
            "embeddings_reused": getattr(stats, "embeddings_reused", 0),
            "embeddings_regenerated": getattr(stats, "embeddings_regenerated", 0),
            "raw_source_embeddings_regenerated": 0,
            "legacy_source_knowledge_removed": getattr(stats, "legacy_source_knowledge_removed", 0),
            "knowledge_cards_staled": getattr(stats, "knowledge_cards_staled", 0),
            "knowledge_reembedded": getattr(stats, "knowledge_reembedded", 0),
            "refresh_attempts": attempts,
            "waited_for_refresh": bool(lock.get("waited")),
        }
