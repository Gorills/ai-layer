from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

SENSITIVE_KEY_FRAGMENT = (
    r"(?:api[_-]?key|access[_-]?token|token|password|passwd|secret|client[_-]?secret|"
    r"access[_-]?key|private[_-]?key|database[_-]?url|dsn|connection[_-]?string)"
)
SECRET_LINE_RE = re.compile(
    rf"(?im)^(\s*(?:(?:export|const|let|var|final|static)\s+)?[\"']?[\w.-]*?"
    rf"{SENSITIVE_KEY_FRAGMENT}[\w.-]*[\"']?\s*[:=]\s*)(.+)$"
)
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
SECRET_ARG_HINTS = (
    "token",
    "password",
    "passwd",
    "secret",
    "api-key",
    "api_key",
    "credential",
    "authorization",
)
_SECRET_ENV_HINTS = (
    "token",
    "password",
    "passwd",
    "secret",
    "credential",
    "authorization",
    "api_key",
    "private_key",
    "access_key",
    "client_secret",
)
_MIN_SECRET_VALUE_CHARS = 6


def redact_secrets(text: str) -> str:
    redacted = SECRET_OBJECT_PAIR_RE.sub(lambda m: f"{m.group(1)}<redacted>", text)
    redacted = SECRET_LINE_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
    redacted = INLINE_SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
    redacted = URL_USERINFO_RE.sub(lambda m: f"{m.group(1)}<redacted>@", redacted)
    redacted = URL_SECRET_QUERY_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
    return BEARER_SECRET_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)


def bound_text(text: str, max_chars: int, *, marker: str = "\n...[truncated]...\n") -> str:
    if max_chars < 1:
        return ""
    if len(text) <= max_chars:
        return text
    if len(marker) + 32 > max_chars:
        return text[:max_chars]
    available = max_chars - len(marker)
    head = available * 2 // 3
    return text[:head] + marker + text[-(available - head) :]


def _is_secret_flag(item: str) -> bool:
    if not item.startswith("-"):
        return False
    lowered = item.casefold()
    return any(hint in lowered for hint in SECRET_ARG_HINTS)


def secret_values_from_argv(argv: Sequence[str]) -> list[str]:
    values: set[str] = set()
    redact_next = False
    for raw in argv:
        item = str(raw)
        if redact_next:
            if len(item) >= _MIN_SECRET_VALUE_CHARS:
                values.add(item)
            redact_next = False
            continue
        if not _is_secret_flag(item):
            continue
        if "=" in item:
            value = item.split("=", 1)[1]
            if len(value) >= _MIN_SECRET_VALUE_CHARS:
                values.add(value)
            continue
        redact_next = True
    return sorted(values, key=len, reverse=True)


def redact_secret_argv(argv: Sequence[str]) -> list[str]:
    safe: list[str] = []
    redact_next = False
    for raw in argv:
        item = str(raw)
        if redact_next:
            safe.append("<redacted>")
            redact_next = False
            continue
        if _is_secret_flag(item):
            if "=" in item:
                key, _value = item.split("=", 1)
                safe.append(f"{key}=<redacted>")
            else:
                safe.append(item)
                redact_next = True
            continue
        safe.append(redact_secrets(item))
    return safe


def redact_text_with_secrets(text: str, extra_secrets: Sequence[str] = ()) -> str:
    redacted = redact_secrets(text)
    for secret in extra_secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


def redact_secret_env(values: Mapping[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in values.items():
        lowered = str(key).casefold().replace("-", "_")
        if any(hint in lowered for hint in _SECRET_ENV_HINTS):
            safe[str(key)] = "<redacted>"
        else:
            safe[str(key)] = redact_secrets(str(value))
    return safe
