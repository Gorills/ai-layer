from __future__ import annotations

import re

REGISTRY_VERSION = 1
MAX_SKILL_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_FILES = 2000
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 128 * 1024 * 1024
ALLOWED_PACKAGE_SUFFIXES = {
    ".md",
    ".txt",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".html",
    ".svg",
    ".jinja",
    ".j2",
    ".tmpl",
}
ALLOWED_PACKAGE_NAMES = {"license", "license.md", "notice", "notice.md"}
PACKAGE_RESOURCE_DIR_NAMES = ("scripts", "references", "assets", "data")
PACKAGE_STORE_CONTRACT = (
    "Resolve skill-relative references/data/scripts against this package root. "
    "Package assets stay outside the repository and are not autoloaded into model context."
)
SAFE_SOURCE_TYPES = {
    "local-file",
    "local-directory",
    "zip",
    "stdin",
    "inline",
    "agent-authored",
    "url",
    "catalog",
}
VALID_SCOPES = {"global", "project"}
VALID_STATUS = {"enabled", "disabled"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")

DEFAULT_SKILL_CATALOG: dict[str, dict[str, str]] = {
    "ui-ux-pro-max": {
        "source": "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/archive/abb7f2fd5a083fa1ff55c326a963ff0d95c33f99.zip",
        "source_member": ".claude/skills/ui-ux-pro-max/SKILL.md",
        "upstream": "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill",
        "version": "2.14.1",
        "revision": "abb7f2fd5a083fa1ff55c326a963ff0d95c33f99",
        "license": "MIT",
        "purpose": "Extended searchable UI/UX design intelligence for weak-model design work.",
    },
}

HIGH_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"(?i)ignore\s+(?:all\s+)?(?:previous|higher[- ]level|project|repository)\s+(?:instructions|rules|policy)",
        "asks worker to ignore governing instructions",
    ),
    (
        r"(?i)(?:bypass|disable|circumvent)\s+(?:the\s+)?(?:ai[- ]layer|task layer|review|security|privacy)\b",
        "asks worker to bypass AI Layer/security controls",
    ),
    (
        r"(?i)(?:print|dump|send|upload|exfiltrat\w*)\s+.*(?:environment|env vars?|secrets?|credentials?|tokens?|ssh keys?)",
        "asks worker to expose host secrets/credentials",
    ),
    (r"(?i)curl\s+[^\n|]+\|\s*(?:sh|bash|zsh)\b", "contains remote shell-pipe execution"),
    (
        r"(?i)(?:cat|read)\s+.*(?:\.ssh|id_rsa|id_ed25519|credentials)",
        "asks worker to read credential files",
    ),
)
MEDIUM_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?i)\bsudo\b", "requests privileged host execution"),
    (r"(?i)\brm\s+-rf\b", "contains destructive recursive deletion"),
    (r"(?i)\bchmod\s+777\b", "contains unsafe broad permissions"),
    (r"(?i)disable\s+(?:tests?|lint|typecheck|checks?)", "asks to disable quality gates"),
)
PACKAGE_SCRIPT_HIGH_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"(?i)\b(?:subprocess\.|os\.system\(|popen\()",
        "package script can spawn arbitrary host processes",
    ),
    (r"(?i)\b(?:requests|httpx|urllib\.request|socket)\b", "package script can access the network"),
    (r"(?i)\b(?:eval|exec)\s*\(", "package script uses dynamic code execution"),
)
