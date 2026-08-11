from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.paths import (
    project_mode,
    project_provenance,
    project_state_path,
)

MAX_SCAN_BYTES = 1_000_000
TRACKED_STREAM_CHUNK_BYTES = 256_000
TRACKED_STREAM_OVERLAP_CHARS = 2_048
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp3",
    ".wav",
    ".mp4",
}
PROVENANCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ai-layer-reference",
        re.compile(
            r"(?i)(?:local\s+ai\s+development\s+layer|\.ai-layer(?:/|\\)|\bai[- ]layer\s+(?:mcp|workflow|memory|session|integration|policy|skill|bootstrap|project\s+state))"
        ),
    ),
    (
        "generated-by-ai",
        re.compile(
            r"(?i)(?:generated|written|created|implemented|modified|edited)\s+(?:by|with|using)\s+(?:an?\s+)?(?:ai|chatgpt|openai|claude|cursor|gemini|copilot|coding agent)"
        ),
    ),
    ("ai-assisted", re.compile(r"(?i)\bai[- ]assisted\b|\bwith\s+ai\s+assistance\b")),
    (
        "agent-provenance",
        re.compile(
            r"(?i)(?:coding|ai)\s+agent\s+(?:generated|created|implemented|modified|edited|work|workflow)"
        ),
    ),
    (
        "ai-coauthor",
        re.compile(
            r"(?im)^\s*co-authored-by:\s*.*(?:chatgpt|openai|anthropic|claude|cursor|gemini|copilot|\bai\b)"
        ),
    ),
)
AI_ARTIFACT_PATHS = {
    ".ai-layer",
    ".cursor/rules/ai-layer.mdc",
    ".cursor/skills/ai-layer/SKILL.md",
    ".claude/skills/ai-layer/SKILL.md",
    ".agents/rules/ai-layer.md",
    ".agents/skills/ai-layer/SKILL.md",
}


def _run_git(root: Path, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(root), *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        return subprocess.CompletedProcess(
            command, 124, stdout=stdout, stderr="git command timed out"
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))


def _run_git_bytes(
    root: Path, *args: str, timeout: float = 10.0
) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", str(root), *args]
    try:
        return subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command, 124, stdout=exc.stdout or b"", stderr=b"git command timed out"
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, stdout=b"", stderr=str(exc).encode())


def is_git_repository(root: str | Path) -> bool:
    path = Path(root).expanduser().resolve()
    proc = _run_git(path, "rev-parse", "--is-inside-work-tree")
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _status_paths(root: Path) -> list[str]:
    proc = _run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")
    raw = proc.stdout.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(raw):
        item = raw[i]
        if not item:
            i += 1
            continue
        status = item[:2]
        path = item[3:] if len(item) > 3 else ""
        if status and ("R" in status or "C" in status) and i + 1 < len(raw):
            # With porcelain v1 -z, the first pathname is the destination and the second is the
            # original source. Scan the destination; skip only the source record.
            i += 1
        if path:
            paths.append(path)
        i += 1
    return sorted(set(paths))


def _staged_paths(root: Path) -> list[str]:
    proc = _run_git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git staged-path query failed")
    return sorted({item for item in proc.stdout.split("\0") if item})


def _known_binary_path(rel: str) -> bool:
    return Path(rel).suffix.lower() in BINARY_EXTENSIONS


def _decode_privacy_text(raw: bytes) -> str | None:
    # Unknown extensions are inspected by content. A NUL byte is a strong binary signal; textual
    # files with uncommon/custom suffixes must not bypass strict-private provenance checks.
    if b"\x00" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _read_worktree_file(root: Path, rel: str) -> tuple[str | None, str | None]:
    path = root / rel
    try:
        if not path.is_file() or path.is_symlink():
            return None, None
        size = path.stat().st_size
        if size > MAX_SCAN_BYTES:
            return (None, None) if _known_binary_path(rel) else (None, "privacy-scan-limit")
        raw = path.read_bytes()
    except OSError:
        return None, "privacy-read-error"
    return _decode_privacy_text(raw), None


def _read_staged_file(root: Path, rel: str) -> tuple[str | None, str | None]:
    size_proc = _run_git(root, "cat-file", "-s", f":{rel}")
    if size_proc.returncode != 0:
        return None, "privacy-read-error"
    try:
        size = int(size_proc.stdout.strip())
    except ValueError:
        return None, "privacy-read-error"
    if size > MAX_SCAN_BYTES:
        return (None, None) if _known_binary_path(rel) else (None, "privacy-scan-limit")
    proc = _run_git_bytes(root, "show", f":{rel}")
    if proc.returncode != 0:
        return None, "privacy-read-error"
    return _decode_privacy_text(proc.stdout), None


def _read_error_violation(rel: str, code: str) -> dict:
    if code == "privacy-scan-limit":
        message = (
            f"Strict-private privacy scan cannot prove this non-binary file safe because it exceeds "
            f"the {MAX_SCAN_BYTES}-byte scan limit."
        )
    else:
        message = "Strict-private privacy scan could not read this changed file safely."
    return {"code": code, "path": rel, "message": message}


def _path_violation(rel: str) -> dict | None:
    normalized = rel.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        normalized == ".ai-layer"
        or normalized.startswith(".ai-layer/")
        or normalized in AI_ARTIFACT_PATHS
    ):
        return {
            "code": "ai-artifact-path",
            "path": rel,
            "message": "AI Layer project artifact is forbidden in strict-private repositories.",
        }
    return None


def _content_violations(rel: str, text: str) -> list[dict]:
    result: list[dict] = []
    for code, pattern in PROVENANCE_PATTERNS:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            result.append(
                {
                    "code": code,
                    "path": rel,
                    "line": line,
                    "message": "AI-development provenance/reference is forbidden by project privacy policy.",
                }
            )
    return result


def privacy_check(
    root: str | Path, *, staged: bool = False, commit_message: str | Path | None = None
) -> dict:
    path = Path(root).expanduser().resolve()
    enabled = project_mode(path) == "strict-private" or project_provenance(path) == "forbid"
    if not enabled:
        return {"ok": True, "enabled": False, "violations": []}
    violations: list[dict] = []
    git_repo = is_git_repository(path)
    if not git_repo:
        violations.append(
            {
                "code": "git-required",
                "path": "",
                "message": "Strict-private mode requires a working Git repository; privacy safety cannot be proven otherwise.",
            }
        )
        return {
            "ok": False,
            "enabled": True,
            "git": False,
            "scope": "staged" if staged else "changed",
            "violations": violations,
        }
    try:
        paths = _staged_paths(path) if staged else _status_paths(path)
    except RuntimeError as exc:
        violations.append(
            {
                "code": "git-query-failed",
                "path": "",
                "message": f"Strict-private Git query failed; privacy safety cannot be proven: {exc}",
            }
        )
        return {
            "ok": False,
            "enabled": True,
            "git": True,
            "scope": "staged" if staged else "changed",
            "violations": violations,
        }
    for rel in paths:
        violation = _path_violation(rel)
        if violation:
            violations.append(violation)
            continue
        text, read_error = (
            _read_staged_file(path, rel) if staged else _read_worktree_file(path, rel)
        )
        if read_error:
            violations.append(_read_error_violation(rel, read_error))
        elif text is not None:
            violations.extend(_content_violations(rel, text))
    if commit_message is not None:
        msg_path = Path(commit_message)
        try:
            text = msg_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            violations.append(_read_error_violation("<commit-message>", "privacy-read-error"))
        else:
            violations.extend(_content_violations("<commit-message>", text))
    return {
        "ok": not violations,
        "enabled": True,
        "git": git_repo,
        "scope": "staged" if staged else "changed",
        "violations": violations,
    }


def _tracked_file_contains_provenance(root: Path, rel: str) -> tuple[bool, str | None]:
    """Scan tracked baseline content without the changed-file size cap.

    Changed/staged privacy checks intentionally remain fail-closed above MAX_SCAN_BYTES.
    Repository baseline repair, however, must be able to inspect legitimate generated text such
    as package-lock.json without treating file size alone as a privacy violation. Large tracked
    text is therefore streamed with bounded memory and overlap for regexes crossing chunk edges.
    """
    path = root / rel
    try:
        if not path.is_file() or path.is_symlink():
            return False, None
        if _known_binary_path(rel):
            return False, None
        with path.open("rb") as handle:
            prefix = handle.read(8192)
            if b"\x00" in prefix:
                return False, None
            handle.seek(0)
            tail = ""
            while True:
                raw = handle.read(TRACKED_STREAM_CHUNK_BYTES)
                if not raw:
                    return False, None
                text = raw.decode("utf-8", errors="replace")
                candidate = tail + text
                if any(pattern.search(candidate) for _, pattern in PROVENANCE_PATTERNS):
                    return True, None
                tail = candidate[-TRACKED_STREAM_OVERLAP_CHARS:]
    except OSError:
        return False, "privacy-read-error"


def _tracked_privacy_footprint(path: Path) -> tuple[list[str], list[str]]:
    if not is_git_repository(path):
        return [], []
    proc = _run_git(path, "ls-files", "-z")
    if proc.returncode != 0:
        return [], []
    tracked: list[str] = []
    unscannable: list[str] = []
    for rel in (x for x in proc.stdout.split("\0") if x):
        if _path_violation(rel):
            tracked.append(rel)
            continue
        contains_provenance, read_error = _tracked_file_contains_provenance(path, rel)
        if read_error:
            unscannable.append(rel)
        elif contains_provenance:
            tracked.append(rel)
    return tracked, unscannable


def repository_footprint(root: str | Path) -> dict:
    path = Path(root).expanduser().resolve()
    candidates = [path / ".ai-layer"] + [
        path / rel for rel in sorted(AI_ARTIFACT_PATHS) if rel != ".ai-layer"
    ]
    artifacts = [
        candidate.relative_to(path).as_posix()
        for candidate in candidates
        if candidate.exists() or candidate.is_symlink()
    ]
    tracked, unscannable = _tracked_privacy_footprint(path)
    return {
        "repository_ai_artifacts": sorted(set(artifacts)),
        "tracked_ai_or_provenance": sorted(set(tracked)),
        "tracked_unscannable": sorted(set(unscannable)),
    }


def _ai_layer_cli() -> str:
    stable = get_settings().stable_bin_dir / "ai-layer"
    if stable.exists():
        return str(stable)
    return shutil.which("ai-layer") or "ai-layer"


def _existing_default_hooks(root: Path) -> list[Path]:
    # `git rev-parse --git-path hooks` follows core.hooksPath. Once AI Layer has installed its
    # external hook directory, using that command here would stop seeing the repository's original
    # `.git/hooks` directory. A later repair/reinstall would then regenerate the wrappers without
    # the user's legacy hooks and silently disable them. Resolve the repository Git dir directly so
    # idempotent reinstalls always rediscover the original hooks instead.
    proc = _run_git(root, "rev-parse", "--git-dir")
    if proc.returncode != 0:
        return []
    git_dir = Path(proc.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    hooks_dir = git_dir / "hooks"
    if not hooks_dir.exists():
        return []
    return [
        p.resolve()
        for p in hooks_dir.iterdir()
        if p.is_file() and os.access(p, os.X_OK) and not p.name.endswith(".sample")
    ]


def install_git_privacy_guard(root: str | Path) -> dict:
    path = Path(root).expanduser().resolve()
    if not is_git_repository(path):
        return {
            "ready": False,
            "applicable": False,
            "reason": "strict-private mode requires an initialized, working Git repository",
        }
    existing = _run_git(path, "config", "--local", "--get", "core.hooksPath")
    if existing.returncode == 0 and existing.stdout.strip():
        configured = existing.stdout.strip()
        target = project_state_path(path, "git-hooks").resolve()
        try:
            same = Path(configured).expanduser().resolve() == target
        except OSError:
            same = False
        if not same:
            return {
                "ready": False,
                "applicable": True,
                "conflict": configured,
                "reason": "existing core.hooksPath must not be overwritten automatically",
            }
    hooks = project_state_path(path, "git-hooks")
    hooks.mkdir(parents=True, exist_ok=True)
    legacy_hooks = _existing_default_hooks(path)
    cli = shlex.quote(_ai_layer_cli())
    root_q = shlex.quote(str(path))
    legacy_by_name = {p.name: p for p in legacy_hooks}
    names = set(legacy_by_name) | {"pre-commit", "commit-msg"}
    for name in names:
        lines = ["#!/bin/sh", "set -e"]
        legacy = legacy_by_name.get(name)
        if legacy and legacy.resolve() != (hooks / name).resolve():
            lines.append(f'{shlex.quote(str(legacy))} "$@"')
        if name == "pre-commit":
            lines.append(f"{cli} privacy-check --path {root_q} --staged")
        elif name == "commit-msg":
            lines.append(f'{cli} privacy-check --path {root_q} --staged --commit-message "$1"')
        (hooks / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(hooks / name, 0o700)
    proc = _run_git(path, "config", "--local", "core.hooksPath", str(hooks.resolve()))
    if proc.returncode != 0:
        return {
            "ready": False,
            "applicable": True,
            "reason": proc.stderr.strip() or "failed to configure core.hooksPath",
        }
    return {
        "ready": True,
        "applicable": True,
        "path": str(hooks.resolve()),
        "chained_legacy_hooks": sorted(legacy_by_name),
    }


def remove_git_privacy_guard(root: str | Path) -> dict:
    """Remove only the core.hooksPath installed for this exact AI Layer project state."""
    path = Path(root).expanduser().resolve()
    if not is_git_repository(path):
        return {"removed": False, "applicable": False}
    proc = _run_git(path, "config", "--local", "--get", "core.hooksPath")
    configured = proc.stdout.strip() if proc.returncode == 0 else ""
    if not configured:
        return {"removed": False, "applicable": True, "reason": "not configured"}
    expected = project_state_path(path, "git-hooks").resolve()
    try:
        configured_path = Path(configured).expanduser().resolve()
    except OSError:
        return {
            "removed": False,
            "applicable": True,
            "reason": "configured hooks path is unreadable",
        }
    if configured_path != expected:
        return {
            "removed": False,
            "applicable": True,
            "reason": "hooks path belongs to another configuration",
        }
    unset = _run_git(path, "config", "--local", "--unset", "core.hooksPath")
    if unset.returncode not in (0, 5):
        raise RuntimeError(unset.stderr.strip() or "failed to remove AI Layer core.hooksPath")
    return {"removed": True, "applicable": True, "path": str(expected)}


def git_privacy_guard_status(root: str | Path) -> dict:
    path = Path(root).expanduser().resolve()
    if not is_git_repository(path):
        return {"ready": False, "applicable": False, "reason": "Git repository unavailable"}
    proc = _run_git(path, "config", "--local", "--get", "core.hooksPath")
    expected = project_state_path(path, "git-hooks").resolve()
    configured = proc.stdout.strip() if proc.returncode == 0 else ""

    def hook_ready(name: str) -> bool:
        hook = expected / name
        if hook.is_symlink() or not hook.is_file() or not os.access(hook, os.X_OK):
            return False
        try:
            content = hook.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        required = "privacy-check" in content and "--staged" in content
        if name == "commit-msg":
            required = required and "--commit-message" in content
        return required

    try:
        configured_matches = (
            bool(configured) and Path(configured).expanduser().resolve() == expected
        )
    except OSError:
        configured_matches = False
    ready = configured_matches and hook_ready("pre-commit") and hook_ready("commit-msg")
    return {
        "ready": ready,
        "applicable": True,
        "configured": configured or None,
        "expected": str(expected),
    }
