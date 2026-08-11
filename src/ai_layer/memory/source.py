from __future__ import annotations

import hashlib
import json
import os
import re
import stat as stat_module
import subprocess
from pathlib import Path
from typing import Iterable

from ai_layer.core.config import get_settings
from ai_layer.core.redaction import redact_secrets as _shared_redact_secrets

IGNORE_DIRS = {
    ".git", ".ai-layer", ".idea", ".vscode", "node_modules", "vendor", "dist", "build",
    "target", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".wav", ".mp4",
}
LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".cs": "csharp", ".cpp": "cpp",
    ".c": "c", ".h": "c", ".hpp": "cpp", ".gd": "gdscript", ".php": "php", ".rb": "ruby",
    ".sql": "sql", ".html": "html", ".css": "css", ".scss": "scss", ".vue": "vue", ".svelte": "svelte",
    ".sh": "shell", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".json": "json", ".md": "markdown",
}
IMPORTANT_NAMES = {
    "README.md", "pyproject.toml", "package.json", "composer.json", "composer.lock", "Cargo.toml", "go.mod", "docker-compose.yml",
    "docker-compose.yaml", "Dockerfile", "Makefile", "project.godot", "requirements.txt", ".env.example",
}
SENSITIVE_NAMES = {
    ".env", ".envrc", ".npmrc", ".pypirc", ".netrc", ".git-credentials", ".dockerconfigjson",
    "credentials", "credentials.json", "credentials.ini", "credentials.toml", "credentials.yaml", "credentials.yml",
    "secrets.json", "secrets.toml", "secrets.yaml", "secrets.yml", "service-account.json",
    "id_rsa", "id_ed25519",
}
SAFE_ENV_TEMPLATE_NAMES = {".env.example", ".env.sample", ".env.template"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

# AI Layer bootstrap/config files must never outrank actual repository code in semantic retrieval.
AI_LAYER_CONTROL_PATHS = {
    ".cursor/rules/ai-layer.mdc",
    ".cursor/skills/ai-layer/SKILL.md",
    ".cursor/mcp.json",
    ".claude/skills/ai-layer/SKILL.md",
    ".agents/rules/ai-layer.md",
    ".agents/skills/ai-layer/SKILL.md",
    ".mcp.json",
    ".codex/config.toml",
}
SHARED_AGENT_INSTRUCTION_PATHS = {"AGENTS.md", "CLAUDE.md"}
MANAGED_START = "<!-- BEGIN AI-LAYER MANAGED -->"
MANAGED_END = "<!-- END AI-LAYER MANAGED -->"
MANAGED_BLOCK_RE = re.compile(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.DOTALL)

PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
JS_IMPORT_RE = re.compile(
    r"(?:import\s+(?:[^;\n]*?\s+from\s+)?|export\s+[^;\n]*?\s+from\s+|require\(\s*|import\(\s*)[\"']([^\"']+)[\"']",
    re.M,
)
SENSITIVE_KEY_FRAGMENT = (
    r"(?:api[_-]?key|access[_-]?token|token|password|passwd|secret|client[_-]?secret|"
    r"access[_-]?key|private[_-]?key|database[_-]?url|dsn|connection[_-]?string)"
)
SECRET_LINE_RE = re.compile(
    rf"(?im)^(\s*(?:(?:export|const|let|var|final|static)\s+)?[\"']?[\w.-]*?"
    rf"{SENSITIVE_KEY_FRAGMENT}[\w.-]*[\"']?\s*[:=]\s*)(.+)$"
)
# Secret-bearing JSON/object keys do not necessarily begin a line. Minified JSON such as
# {"SERVICE_TOKEN":"..."} therefore bypasses a line-anchored assignment matcher.
SECRET_OBJECT_PAIR_RE = re.compile(
    rf"(?i)([\"']?[\w.-]*?{SENSITIVE_KEY_FRAGMENT}[\w.-]*[\"']?\s*:\s*)"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^,}\]\n]+)"
)
INLINE_SECRET_ASSIGNMENT_RE = re.compile(
    rf"(?i)(\b[\w.-]*?{SENSITIVE_KEY_FRAGMENT}[\w.-]*\s*=\s*)"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s;,]+)"
)
URL_USERINFO_RE = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)([^/\s@]+)@")
URL_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|password|passwd|secret|client[_-]?secret)=)([^&#\s\"']+)"
)
BEARER_SECRET_RE = re.compile(r"(?i)(\bbearer\s+)([a-z0-9._~+/=-]{8,})")


class ScanLimitExceeded(RuntimeError):
    """The eligible source corpus exceeds the configured correctness boundary."""


def _git_visible_paths(root: Path) -> list[Path] | None:
    """Return tracked + non-ignored untracked files when Git owns the worktree."""
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Git worktree detected but source enumeration failed safely.") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            "Git worktree detected but AI Layer could not enumerate tracked/non-ignored files safely."
        )
    paths = {root / os.fsdecode(raw) for raw in proc.stdout.split(b"\0") if raw}
    return sorted(paths, key=lambda path: path.as_posix())


def iter_files(root: Path) -> Iterable[Path]:
    settings = get_settings()
    count = 0
    candidates = _git_visible_paths(root)
    iterable = candidates if candidates is not None else root.rglob("*")
    for path in iterable:
        if path.is_symlink() or not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORE_DIRS for part in rel_parts[:-1]):
            continue
        if path.suffix.lower() in BINARY_EXTS:
            continue
        name = path.name.lower()
        env_secret = name.startswith(".env.") and name not in SAFE_ENV_TEMPLATE_NAMES
        terraform_secret = name.endswith(".tfstate") or ".tfstate." in name or name.endswith(".tfvars")
        if name in SENSITIVE_NAMES or env_secret or terraform_secret or path.suffix.lower() in SENSITIVE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > settings.scan_max_file_bytes:
                continue
        except OSError:
            continue
        if count >= settings.scan_max_files:
            raise ScanLimitExceeded(
                f"Scanner-visible source count exceeds scan_max_files={settings.scan_max_files}. "
                "Increase AI_LAYER_SCAN_MAX_FILES before refreshing memory; existing memory was not published as fresh."
            )
        count += 1
        yield path


def _read_raw(path: Path) -> bytes | None:
    """Read one bounded regular file without following the final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat_module.S_ISREG(opened.st_mode):
                return None
            limit = get_settings().scan_max_file_bytes
            raw = handle.read(limit + 1)
    except OSError:
        return None
    return None if len(raw) > limit else raw


def _decode_source(raw: bytes) -> str | None:
    if b"\x00" in raw[:4096]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _stable_stat_key(stat) -> tuple[int, int, int, int]:
    return (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))


def read_text(path: Path) -> str | None:
    """Read scanner-visible text; unknown binary content is intentionally non-semantic."""
    raw = _read_raw(path)
    return _decode_source(raw) if raw is not None else None


def read_stable_source(path: Path) -> tuple[bytes, str | None, object] | None:
    """Read one stable physical source version and return raw identity plus optional text."""
    try:
        before = path.lstat()
    except OSError:
        return None
    if not stat_module.S_ISREG(before.st_mode):
        return None
    raw = _read_raw(path)
    if raw is None:
        return None
    try:
        after = path.lstat()
    except OSError:
        return None
    if _stable_stat_key(before) != _stable_stat_key(after) or not stat_module.S_ISREG(after.st_mode):
        return None
    return raw, _decode_source(raw), after


def read_stable_text(path: Path) -> tuple[str, object] | None:
    """Read only a text file version whose identity metadata stayed stable across the read."""
    try:
        before = path.lstat()
    except OSError:
        return None
    if not stat_module.S_ISREG(before.st_mode):
        return None
    text = read_text(path)
    if text is None:
        return None
    try:
        after = path.lstat()
    except OSError:
        return None
    return (text, after) if _stable_stat_key(before) == _stable_stat_key(after) and stat_module.S_ISREG(after.st_mode) else None


def prepare_index_text(rel: str, text: str) -> str | None:
    """Remove AI Layer's own bootstrap text from the corpus.

    AGENTS.md/CLAUDE.md may contain user-authored instructions, so only the managed AI Layer block is
    stripped there. Dedicated AI Layer bridge/config files are excluded completely.
    """
    if rel in AI_LAYER_CONTROL_PATHS:
        return None
    if rel in SHARED_AGENT_INSTRUCTION_PATHS:
        text = MANAGED_BLOCK_RE.sub("", text).strip()
        return text or None
    return text


def language_for(path: Path) -> str | None:
    return LANG_BY_EXT.get(path.suffix.lower())


def infer_purpose(rel: str, text: str, language: str | None) -> str:
    name = Path(rel).name.lower()
    if name.startswith("readme"):
        return "Project documentation and entry-point guidance."
    if name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "requirements.txt"}:
        return "Dependency/build manifest; defines runtime or development dependencies."
    if "test" in Path(rel).parts or name.startswith("test_") or name.endswith("_test.py"):
        return "Automated test or test support code."
    if name in {"main.py", "app.py", "server.py", "index.ts", "index.js", "main.go", "lib.rs", "main.rs"}:
        return "Likely application entry point or composition root."
    if "migration" in rel.lower() or "alembic" in rel.lower():
        return "Database schema migration or migration configuration."
    if language:
        return f"{language} source/configuration file; role inferred from path `{rel}`."
    return f"Project text/configuration file at `{rel}`."


def extract_imports(text: str) -> list[str]:
    found: list[str] = []
    for match in PY_IMPORT_RE.finditer(text[:100_000]):
        value = next((g for g in match.groups() if g), None)
        if value:
            found.append(value)
    for match in JS_IMPORT_RE.finditer(text[:100_000]):
        value = match.group(1)
        if value and not value.startswith((".", "/")):
            found.append(value)
    return sorted(set(found))[:80]


def redact_secrets(text: str) -> str:
    return _shared_redact_secrets(text)


def _safe_metadata_text(value: object) -> str:
    return redact_secrets(str(value))


def risk_flags(rel: str, text: str) -> list[str]:
    flags = []
    low = text.lower()
    rel_low = rel.lower()
    if "todo" in low or "fixme" in low:
        flags.append("contains_todo_or_fixme")
    if any(x in rel_low for x in ("auth", "security", "payment", "migration")):
        flags.append("sensitive_or_high_impact_area")
    if "csrf_exempt" in low:
        flags.append("csrf_exemption_present")
    if "webhook" in low:
        flags.append("webhook_surface")
    if "idempotency" in low:
        flags.append("idempotency_logic_present")
    if len(text) > 50_000:
        flags.append("large_file")
    return flags


def _safe_manifest(path: Path) -> bool:
    return path.exists() and not path.is_symlink() and path.is_file()


def parse_dependencies(root: Path) -> dict[str, list[str]]:
    """Read bounded dependency manifests across supported ecosystems.

    Dependency discovery is descriptive only: malformed/unsupported manifests are skipped rather
    than turning a repository scan into an architectural guess. Secret-bearing values are redacted.
    """
    deps: dict[str, list[str]] = {}
    pyproject = root / "pyproject.toml"
    if _safe_manifest(pyproject):
        try:
            import tomllib
            text = read_text(pyproject)
            if text is not None:
                data = tomllib.loads(text)
                project_deps = list(data.get("project", {}).get("dependencies", []) or [])
                poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                if isinstance(poetry, dict):
                    project_deps.extend(f"{k}{v if isinstance(v, str) else ''}" for k, v in poetry.items() if k != "python")
                deps["python"] = [_safe_metadata_text(x) for x in project_deps]
        except Exception:
            pass
    for req in sorted(root.glob("requirements*.txt"))[:12]:
        if not _safe_manifest(req):
            continue
        try:
            text = read_text(req)
            if text is not None:
                deps.setdefault("python", []).extend(
                    _safe_metadata_text(line.strip()) for line in text.splitlines()
                    if line.strip() and not line.lstrip().startswith(("#", "-r", "--requirement"))
                )
        except Exception:
            pass
    package = root / "package.json"
    if _safe_manifest(package):
        try:
            text = read_text(package)
            if text is not None:
                data = json.loads(text)
                merged = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                deps["node"] = sorted(_safe_metadata_text(f"{k}@{v}") for k, v in merged.items())
        except Exception:
            pass
    composer = root / "composer.json"
    if _safe_manifest(composer):
        try:
            text = read_text(composer)
            if text is not None:
                data = json.loads(text)
                merged = {**data.get("require", {}), **data.get("require-dev", {})}
                deps["composer"] = sorted(_safe_metadata_text(f"{k}@{v}") for k, v in merged.items())
        except Exception:
            pass
    go_mod = root / "go.mod"
    if _safe_manifest(go_mod):
        try:
            text = read_text(go_mod)
            if text is not None:
                lines = text.splitlines()
                deps["go"] = [_safe_metadata_text(line.strip()) for line in lines if line.strip().startswith("require ")]
        except Exception:
            pass
    for ecosystem, values in list(deps.items()):
        deps[ecosystem] = sorted(dict.fromkeys(value for value in values if value))
    return deps

def architecture_summary(root: Path, languages: dict[str, int], dependencies: dict[str, list[str]], files: list[str]) -> str:
    top_dirs = sorted({Path(p).parts[0] for p in files if len(Path(p).parts) > 1})[:30]
    manifests = [p for p in files if Path(p).name in IMPORTANT_NAMES]
    return (
        f"Project `{root.name}`. Languages: {languages or {}}. "
        f"Top-level areas: {top_dirs or ['(flat project)']}. "
        f"Key manifests/docs: {manifests[:20]}. "
        f"Dependency ecosystems: {sorted(dependencies)}. "
        "This summary is scanner-derived and intentionally factual; it does not invent architecture not visible in the repository."
    )
