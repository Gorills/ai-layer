from __future__ import annotations

import hashlib
import shutil
import stat as stat_module
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ai_layer.db.models import ProjectFile
from ai_layer.memory.source import AI_LAYER_CONTROL_PATHS, iter_files, read_stable_source


class RepositoryChangedDuringScan(RuntimeError):
    """Raised when a candidate file cannot be read as one stable version."""


@dataclass(frozen=True)
class SourceSnapshot:
    path: str
    text: str | None
    size: int
    mtime_ns: int
    ctime_ns: int
    content_sha256: str

    def state(self, *, indexed: bool) -> dict[str, int | str | bool]:
        return {
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
            "content_sha256": self.content_sha256,
            "indexed": indexed,
        }


@dataclass
class ChangeSet:
    current_hints: dict[str, dict[str, int]]
    snapshots: dict[str, SourceSnapshot] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    metadata_only: list[str] = field(default_factory=list)
    renamed: list[dict[str, str]] = field(default_factory=list)
    git_candidates: list[str] = field(default_factory=list)
    hashes_calculated: int = 0

    @property
    def content_changed(self) -> list[str]:
        return [*self.added, *self.modified]

    def summary(self, *, max_paths: int = 12) -> dict:
        return {
            "added": self.added[:max_paths],
            "modified": self.modified[:max_paths],
            "deleted": self.deleted[:max_paths],
            "renamed": self.renamed[:max_paths],
            "unchanged": len(self.unchanged),
            "metadata_only": len(self.metadata_only),
            "hashes_calculated": self.hashes_calculated,
            "git_candidates": len(self.git_candidates),
            "total": len(self.added) + len(self.modified) + len(self.deleted),
            "truncated": any(
                len(items) > max_paths
                for items in (self.added, self.modified, self.deleted, self.renamed)
            ),
        }


def _stat_hint(path: Path) -> dict[str, int] | None:
    try:
        stat = path.lstat()
    except OSError:
        return None
    if path.is_symlink() or not stat_module.S_ISREG(stat.st_mode):
        return None
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "ctime_ns": int(getattr(stat, "st_ctime_ns", 0)),
    }


def build_file_hints(root: Path) -> dict[str, dict[str, int]]:
    """Cheap repository snapshot used only to decide which sources require hash verification."""
    state: dict[str, dict[str, int]] = {}
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in AI_LAYER_CONTROL_PATHS:
            continue
        hint = _stat_hint(path)
        if hint is not None:
            state[rel] = hint
    return state




def repository_probe(root: Path, *, budget_seconds: float | None = None) -> dict | None:
    """Return a cheap Git generation fingerprint, or None when Git cannot prove repository state.

    HEAD captures committed changes. Porcelain status captures tracked/untracked path changes; for
    dirty files we additionally persist size/mtime/ctime hints so repeated edits to the same dirty
    pathname cannot be mistaken for an unchanged repository. This is an optimization only: any
    uncertainty falls back to the full scanner-visible file-state comparison.
    """
    git = shutil.which("git")
    if not git:
        return None
    deadline = time.monotonic() + budget_seconds if budget_seconds is not None else None

    def remaining(default: float) -> float:
        if deadline is None:
            return default
        value = deadline - time.monotonic()
        if value <= 0:
            raise subprocess.TimeoutExpired(cmd="git freshness probe", timeout=budget_seconds or 0)
        return max(0.05, min(default, value))

    try:
        inside = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=remaining(5), check=False,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        head = subprocess.run(
            [git, "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=remaining(5), check=False,
        )
        status = subprocess.run(
            [git, "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."],
            capture_output=True, timeout=remaining(10), check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if status.returncode != 0:
        return None
    dirty_paths: set[str] = set()
    parts = status.stdout.split(b"\0")
    index = 0
    while index < len(parts):
        raw = parts[index]
        index += 1
        if not raw:
            continue
        text = raw.decode("utf-8", errors="surrogateescape")
        if len(text) < 4:
            continue
        code, rel = text[:2], Path(text[3:]).as_posix()
        if rel and rel not in AI_LAYER_CONTROL_PATHS:
            dirty_paths.add(rel)
        if ("R" in code or "C" in code) and index < len(parts) and parts[index]:
            old = Path(parts[index].decode("utf-8", errors="surrogateescape")).as_posix()
            if old not in AI_LAYER_CONTROL_PATHS:
                dirty_paths.add(old)
            index += 1
    dirty: dict[str, dict[str, int] | None] = {}
    for rel in sorted(dirty_paths):
        dirty[rel] = _stat_hint(root / rel)
    return {
        "kind": "git-v1",
        "head": head.stdout.strip() if head.returncode == 0 else "<unborn>",
        "status_sha256": hashlib.sha256(status.stdout).hexdigest(),
        "dirty": dirty,
    }


def state_hints_match(previous: dict, current: dict[str, dict[str, int]]) -> bool:
    """Compare physical hints without treating them as content identity.

    A v0.2 state must also carry a persisted content hash. Legacy v0.1 states therefore force one
    verification refresh after upgrade even if size/mtime are unchanged.
    """
    if set(previous) != set(current):
        return False
    for path, hint in current.items():
        old = previous.get(path)
        if not isinstance(old, dict) or not old.get("content_sha256"):
            return False
        if any(int(old.get(key, -1)) != int(hint.get(key, 0)) for key in ("size", "mtime_ns", "ctime_ns")):
            return False
    return True


def _git_changed_paths(root: Path) -> set[str]:
    """Best-effort Git evidence. Correctness never depends on this result."""
    git = shutil.which("git")
    if not git:
        return set()
    try:
        proc = subprocess.run(
            [git, "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if proc.returncode != 0:
        return set()

    parts = proc.stdout.split(b"\0")
    result: set[str] = set()
    index = 0
    while index < len(parts):
        raw = parts[index]
        index += 1
        if not raw:
            continue
        text = raw.decode("utf-8", errors="surrogateescape")
        if len(text) < 4:
            continue
        status = text[:2]
        path = text[3:]
        if path and path not in AI_LAYER_CONTROL_PATHS:
            result.add(Path(path).as_posix())
        if "R" in status or "C" in status:
            if index < len(parts) and parts[index]:
                old = parts[index].decode("utf-8", errors="surrogateescape")
                result.add(Path(old).as_posix())
                index += 1
    return result


def _row_hash(row: ProjectFile) -> str:
    return str(getattr(row, "content_sha256", "") or row.sha256 or "")


def _row_hint(row: ProjectFile) -> tuple[int, int, int]:
    return (
        int(row.size_bytes),
        int(getattr(row, "mtime_ns", 0) or 0),
        int(getattr(row, "ctime_ns", 0) or 0),
    )


def _snapshot(root: Path, rel: str) -> SourceSnapshot:
    stable = read_stable_source(root / rel)
    if stable is None:
        raise RepositoryChangedDuringScan(f"Source changed, disappeared, or became unreadable during scan: {rel}")
    raw, text, stat = stable
    return SourceSnapshot(
        path=rel,
        text=text,
        size=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
        ctime_ns=int(getattr(stat, "st_ctime_ns", 0)),
        content_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _detect_renames(changes: ChangeSet, previous: dict[str, ProjectFile]) -> None:
    """Report only unambiguous equal-content renames; storage still uses delete+add semantics."""
    deleted_by_hash: dict[str, list[str]] = {}
    added_by_hash: dict[str, list[str]] = {}
    for path in changes.deleted:
        digest = _row_hash(previous[path])
        if digest:
            deleted_by_hash.setdefault(digest, []).append(path)
    for path in changes.added:
        snapshot = changes.snapshots.get(path)
        if snapshot:
            added_by_hash.setdefault(snapshot.content_sha256, []).append(path)

    renamed: list[dict[str, str]] = []
    for digest in sorted(set(deleted_by_hash) & set(added_by_hash)):
        old = deleted_by_hash[digest]
        new = added_by_hash[digest]
        if len(old) == 1 and len(new) == 1:
            renamed.append({"from": old[0], "to": new[0]})
    changes.renamed = renamed


def classify_changes(
    root: Path,
    previous_rows: Iterable[ProjectFile],
    *,
    current_hints: dict[str, dict[str, int]] | None = None,
    force_verify_all: bool = False,
) -> ChangeSet:
    """Classify physical changes, using stat/Git only as candidate hints and hashes as verification."""
    previous = {row.path: row for row in previous_rows}
    hints = current_hints if current_hints is not None else build_file_hints(root)
    git_candidates = _git_changed_paths(root)
    changes = ChangeSet(current_hints=hints, git_candidates=sorted(git_candidates))

    previous_paths = set(previous)
    current_paths = set(hints)
    changes.deleted = sorted(previous_paths - current_paths)

    for rel in sorted(current_paths):
        row = previous.get(rel)
        hint = hints[rel]
        current_hint = (hint["size"], hint["mtime_ns"], hint["ctime_ns"])
        needs_hash = (
            row is None
            or not _row_hash(row)
            or _row_hint(row) != current_hint
            or rel in git_candidates
            or force_verify_all
        )
        if not needs_hash:
            changes.unchanged.append(rel)
            continue

        snapshot = _snapshot(root, rel)
        changes.snapshots[rel] = snapshot
        changes.hashes_calculated += 1
        if row is None:
            changes.added.append(rel)
        elif snapshot.content_sha256 != _row_hash(row):
            changes.modified.append(rel)
        else:
            changes.metadata_only.append(rel)
            changes.unchanged.append(rel)

    _detect_renames(changes, previous)
    return changes
