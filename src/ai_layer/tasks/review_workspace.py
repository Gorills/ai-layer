from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.db.models import Project, Task, TaskStage

SANDBOX_MANIFEST = ".ai-layer-review-sandbox.json"


def _sandbox_parent(project: Project) -> Path:
    root = get_settings().home / "review-sandboxes" / str(project.id)
    if root.is_symlink():
        raise RuntimeError(f"Refusing symlinked review sandbox root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def sandbox_path(project: Project, stage: TaskStage) -> Path:
    return _sandbox_parent(project) / str(stage.id)


def _manifest_path(path: Path) -> Path:
    return path / SANDBOX_MANIFEST


def _read_manifest(path: Path) -> dict | None:
    manifest = _manifest_path(path)
    if manifest.is_symlink() or not manifest.exists():
        return None
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_manifest(path: Path, payload: dict) -> None:
    target = _manifest_path(path)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass


def _git_root(root: Path) -> bool:
    git = shutil.which("git")
    if not git:
        return False
    try:
        probe = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0 and probe.stdout.strip() == "true"


def _remove_deleted_tracked_files(source: Path, target: Path) -> None:
    git = shutil.which("git")
    if not git:
        return
    try:
        proc = subprocess.run(
            [git, "-C", str(source), "ls-files", "--deleted", "-z"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if proc.returncode != 0:
        return
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = Path(os.fsdecode(raw))
        if rel.is_absolute() or ".." in rel.parts:
            continue
        candidate = target / rel
        try:
            if candidate.is_dir() and not candidate.is_symlink():
                shutil.rmtree(candidate)
            else:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue


def _git_visible_paths(source: Path) -> list[Path] | None:
    """Return tracked + non-ignored untracked paths for a Git worktree."""
    git = shutil.which("git")
    if not git or not _git_root(source):
        return None
    try:
        proc = subprocess.run(
            [git, "-C", str(source), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            timeout=20,
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
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or ".git" in rel.parts
            or ".ai-layer" in rel.parts
        ):
            continue
        result.append(rel)
    return sorted(set(result), key=lambda item: item.as_posix())


def _copy_worktree_path(source: Path, target: Path, rel: Path) -> None:
    src = source / rel
    dst = target / rel
    try:
        if src.is_symlink():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                if dst.is_dir() and not dst.is_symlink():
                    shutil.rmtree(dst)
                else:
                    dst.unlink(missing_ok=True)
            dst.symlink_to(os.readlink(src), target_is_directory=src.is_dir())
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except OSError:
        return


def _overlay_working_tree(source: Path, target: Path) -> None:
    """Overlay managed Git state, or a bounded non-Git fallback, without following symlinks."""
    git_paths = _git_visible_paths(source)
    if git_paths is not None:
        for rel in git_paths:
            _copy_worktree_path(source, target, rel)
        return

    for current, dirs, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(source)
        if rel_dir == Path("."):
            dirs[:] = [name for name in dirs if name not in {".git", ".ai-layer"}]
        else:
            dirs[:] = [name for name in dirs if name != ".ai-layer"]
        destination_dir = target / rel_dir
        destination_dir.mkdir(parents=True, exist_ok=True)
        for name in list(dirs):
            src_dir = current_path / name
            if not src_dir.is_symlink():
                continue
            dst_dir = destination_dir / name
            try:
                dst_dir.unlink(missing_ok=True)
                dst_dir.symlink_to(os.readlink(src_dir), target_is_directory=True)
            except OSError:
                pass
            dirs.remove(name)
        for name in files:
            if rel_dir == Path(".") and name == SANDBOX_MANIFEST:
                continue
            src = current_path / name
            dst = destination_dir / name
            try:
                if src.is_symlink():
                    dst.unlink(missing_ok=True)
                    dst.symlink_to(os.readlink(src))
                elif src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            except OSError:
                continue


def cleanup_review_sandbox(project: Project, stage_id: str) -> dict:
    path = _sandbox_parent(project) / str(stage_id)
    if not path.exists() and not path.is_symlink():
        return {"ok": True, "removed": False, "path": str(path)}
    manifest = _read_manifest(path)
    if manifest and str(manifest.get("project_id")) != str(project.id):
        raise RuntimeError(f"Refusing to remove review sandbox owned by another project: {path}")
    source = Path(project.root_path).expanduser().resolve()
    # The entire review-sandboxes/<project-id>/ namespace is AI Layer-owned. A missing manifest can
    # occur if the process dies between worktree/copy creation and manifest publication; recover
    # that partial preparation instead of wedging every future review for the stage.
    mode = str((manifest or {}).get("mode") or "unknown")
    removed = False
    if mode in {"git-worktree", "unknown"} and _git_root(source):
        git = shutil.which("git")
        if git:
            try:
                proc = subprocess.run(
                    [git, "-C", str(source), "worktree", "remove", "--force", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                removed = proc.returncode == 0
            except (OSError, subprocess.SubprocessError):
                removed = False
    if not removed:
        shutil.rmtree(path, ignore_errors=True)
        removed = not path.exists()
        if mode == "git-worktree" and _git_root(source):
            git = shutil.which("git")
            if git:
                try:
                    subprocess.run(
                        [git, "-C", str(source), "worktree", "prune"],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
    return {"ok": removed or not path.exists(), "removed": removed, "path": str(path)}


def prepare_review_sandbox(project: Project, task: Task, stage: TaskStage) -> dict:
    if stage.kind not in {"review", "discovery"} or stage.status != "active":
        raise RuntimeError(
            "Read-only sandbox is available only for an active discovery/review stage."
        )
    source = Path(project.root_path).expanduser().resolve()
    path = sandbox_path(project, stage)
    existing = _read_manifest(path) if path.exists() else None
    if existing and (
        str(existing.get("project_id")) == str(project.id)
        and str(existing.get("task_id")) == str(task.id)
        and str(existing.get("stage_id")) == str(stage.id)
        and str(existing.get("repository_digest")) == str(stage.repository_digest_before or "")
    ):
        return {
            "ok": True,
            "reused": True,
            "path": str(path),
            "stage_id": str(stage.id),
            "repository_digest": stage.repository_digest_before,
            "isolation": "disposable-working-copy; not an OS/container security boundary",
        }
    if path.exists():
        cleanup_review_sandbox(project, str(stage.id))

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "copy"
    git = shutil.which("git")
    if git and _git_root(source):
        try:
            proc = subprocess.run(
                [git, "-C", str(source), "worktree", "add", "--detach", str(path), "HEAD"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            proc = None
        if proc is not None and proc.returncode == 0:
            mode = "git-worktree"
            _remove_deleted_tracked_files(source, path)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    _overlay_working_tree(source, path)
    _write_manifest(
        path,
        {
            "schema": 1,
            "owner": "local-ai-development-layer",
            "project_id": str(project.id),
            "task_id": str(task.id),
            "stage_id": str(stage.id),
            "repository_digest": str(stage.repository_digest_before or ""),
            "source_root": str(source),
            "mode": mode,
        },
    )
    return {
        "ok": True,
        "reused": False,
        "path": str(path),
        "stage_id": str(stage.id),
        "repository_digest": stage.repository_digest_before,
        "isolation": "disposable-working-copy; not an OS/container security boundary",
    }
