from __future__ import annotations

from typing import TypedDict


class SafeEventPayload(TypedDict, total=False):
    status: str
    summary: str
    reason: str
    goal: str
    kind: str
    tool: str
    command_name: str
    duration_ms: int | float
    error_type: str | None
    updated: int
    removed: int
    scope_paths: list[str]
    map_status: str
