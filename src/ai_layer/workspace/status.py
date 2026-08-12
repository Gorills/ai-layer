from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ai_layer.workspace.repository import git_changed_paths


def _git_text(root: Path, *args: str) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    try:
        proc = subprocess.run(
            [git, "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def repository_runtime_status(project_root: str | Path) -> dict:
    """Read branch/HEAD/worktree status without hashing repository contents."""
    root = Path(project_root).expanduser().resolve()
    inside = _git_text(root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        return {"vcs": "none", "dirty": None, "changed_paths": []}

    branch = _git_text(root, "branch", "--show-current") or None
    head = _git_text(root, "rev-parse", "--short=12", "HEAD") or None
    try:
        changes = git_changed_paths(root)
    except RuntimeError as exc:
        return {
            "vcs": "git",
            "branch": branch,
            "head": head,
            "dirty": None,
            "changed_paths": [],
            "status_error": f"{type(exc).__name__}: {exc}"[:300],
        }
    return {
        "vcs": "git",
        "branch": branch,
        "head": head,
        "dirty": bool(changes.get("total")),
        "changed_paths": list(changes.get("paths") or [])[:30],
        "changed_count": int(changes.get("total") or 0),
        "staged_count": int(changes.get("staged_count") or 0),
        "unstaged_count": int(changes.get("unstaged_count") or 0),
        "untracked_count": int(changes.get("untracked_count") or 0),
        "truncated": bool(changes.get("truncated")),
    }
