from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_SNAPSHOT_SCHEMA = 4
MAX_CHANGE_PATHS = 200
FALLBACK_IGNORE_DIRS = {
    ".git",
    ".ai-layer",
    ".idea",
    ".vscode",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def git_visible_paths(root: Path) -> list[Path] | None:
    git = shutil.which("git")
    if not git:
        return None
    try:
        probe = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return None
        proc = subprocess.run(
            [git, "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    result: list[Path] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = Path(os.fsdecode(raw))
        if ".ai-layer" in rel.parts or ".git" in rel.parts:
            continue
        result.append(root / rel)
    return sorted(set(result), key=lambda item: item.as_posix())


def git_changed_paths(root: Path) -> dict:
    """Return Git worktree changes without reading/storing repository content."""
    git = shutil.which("git")
    if not git:
        raise RuntimeError("task_adopt requires Git, but `git` is not available.")
    try:
        probe = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("task_adopt could not verify Git repository state.") from exc
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise RuntimeError(
            "task_adopt requires a Git repository so unmanaged changes can be identified honestly."
        )

    def names(args: list[str], timeout: int = 10) -> list[str]:
        try:
            proc = subprocess.run(
                [git, "-C", str(root), *args], capture_output=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("task_adopt could not inspect Git worktree changes.") from exc
        if proc.returncode != 0:
            message = os.fsdecode(proc.stderr or b"").strip()
            raise RuntimeError(
                f"task_adopt Git inspection failed: {message or 'unknown git error'}"
            )
        decoded = {os.fsdecode(item) for item in proc.stdout.split(b"\0") if item}
        return sorted(
            path for path in decoded if path != ".ai-layer" and not path.startswith(".ai-layer/")
        )

    staged = names(["diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB"])
    unstaged = names(["diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB"])
    untracked = names(["ls-files", "--others", "--exclude-standard", "-z"])
    all_paths = sorted(set(staged) | set(unstaged) | set(untracked))
    return {
        "source": "git_worktree_status",
        "detected_at": utc_iso(),
        "total": len(all_paths),
        "paths": all_paths[:MAX_CHANGE_PATHS],
        "truncated": len(all_paths) > MAX_CHANGE_PATHS,
        "staged": staged[:MAX_CHANGE_PATHS],
        "unstaged": unstaged[:MAX_CHANGE_PATHS],
        "untracked": untracked[:MAX_CHANGE_PATHS],
        "staged_count": len(staged),
        "unstaged_count": len(unstaged),
        "untracked_count": len(untracked),
    }


def repository_files(root: Path) -> Iterable[Path]:
    git_paths = git_visible_paths(root)
    iterable = git_paths if git_paths is not None else root.rglob("*")
    for path in iterable:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if ".ai-layer" in rel.parts or ".git" in rel.parts:
            continue
        if git_paths is None and any(part in FALLBACK_IGNORE_DIRS for part in rel.parts[:-1]):
            continue
        try:
            if path.is_symlink() or not path.is_file():
                continue
        except OSError:
            continue
        yield path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_repository_state(root: str | Path, previous: dict | None = None) -> dict:
    """Capture content identity without persisting repository contents."""
    project_root = Path(root).expanduser().resolve()
    previous_files = (previous or {}).get("files") or {}
    files: dict[str, dict] = {}
    for path in repository_files(project_root):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(project_root).as_posix()
        identity: dict[str, int | str] = {
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "ctime_ns": int(getattr(stat, "st_ctime_ns", 0)),
        }
        old = previous_files.get(rel) if isinstance(previous_files, dict) else None
        can_reuse = (
            isinstance(old, dict)
            and all(
                int(old.get(key, -1)) == identity[key] for key in ("size", "mtime_ns", "ctime_ns")
            )
            and bool(old.get("sha256"))
        )
        try:
            if can_reuse and isinstance(old, dict):
                identity["sha256"] = str(old["sha256"])
            else:
                identity["sha256"] = hash_file(path)
        except OSError:
            continue
        files[rel] = identity

    digest = hashlib.sha256()
    for rel, item in sorted(files.items()):
        digest.update(rel.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).encode("ascii"))
        digest.update(b"\0")
    return {
        "schema": REPOSITORY_SNAPSHOT_SCHEMA,
        "captured_at": utc_iso(),
        "digest": digest.hexdigest(),
        "file_count": len(files),
        "files": files,
    }


def repository_changes(before: dict, after: dict, *, max_paths: int = MAX_CHANGE_PATHS) -> dict:
    old = before.get("files") or {}
    new = after.get("files") or {}
    old_paths, new_paths = set(old), set(new)
    added_all = sorted(new_paths - old_paths)
    deleted_all = sorted(old_paths - new_paths)
    modified_all = sorted(
        path
        for path in old_paths & new_paths
        if str((old.get(path) or {}).get("sha256")) != str((new.get(path) or {}).get("sha256"))
    )
    total = len(added_all) + len(modified_all) + len(deleted_all)
    return {
        "added": added_all[:max_paths],
        "modified": modified_all[:max_paths],
        "deleted": deleted_all[:max_paths],
        "total": total,
        "truncated": any(
            len(items) > max_paths for items in (added_all, modified_all, deleted_all)
        ),
    }


def git_changed_line_count(root: Path, changes: dict) -> dict | None:
    git = shutil.which("git")
    if not git:
        return None
    paths = [
        *(changes.get("added") or []),
        *(changes.get("modified") or []),
        *(changes.get("deleted") or []),
    ]
    if not paths:
        return {"insertions": 0, "deletions": 0, "total": 0, "binary": False}
    try:
        probe = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if probe.returncode != 0:
            return None
        proc = subprocess.run(
            [git, "-C", str(root), "diff", "--numstat", "HEAD", "--", *paths],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    insertions = deletions = 0
    binary = False
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, rel = parts
        seen.add(rel)
        if added == "-" or removed == "-":
            binary = True
            continue
        try:
            insertions += int(added)
            deletions += int(removed)
        except ValueError:
            return None
    for rel in changes.get("added") or []:
        if str(rel) in seen:
            continue
        path = root / str(rel)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if b"\0" in data:
            binary = True
            continue
        insertions += len(data.decode("utf-8", errors="replace").splitlines())
    return {
        "insertions": insertions,
        "deletions": deletions,
        "total": insertions + deletions,
        "binary": binary,
    }
