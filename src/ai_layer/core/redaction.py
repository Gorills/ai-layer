from __future__ import annotations

import re

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


def redact_secrets(text: str) -> str:
    redacted = SECRET_OBJECT_PAIR_RE.sub(lambda m: f"{m.group(1)}<redacted>", text)
    redacted = SECRET_LINE_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
    redacted = INLINE_SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
    redacted = URL_USERINFO_RE.sub(lambda m: f"{m.group(1)}<redacted>@", redacted)
    redacted = URL_SECRET_QUERY_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
    return BEARER_SECRET_RE.sub(lambda m: f"{m.group(1)}<redacted>", redacted)
