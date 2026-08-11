from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class StageKind(StrEnum):
    DISCOVERY = "discovery"
    IMPLEMENT = "implement"
    REVIEW = "review"
    FIX = "fix"


class TaskStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class NextAction:
    action: str
    tool: str | None = None
    code: str | None = None
    reason: str | None = None
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepositoryDelta:
    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    total: int = 0
    truncated: bool = False
    digest_before: str | None = None
    digest_after: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FindingContract:
    severity: str
    category: str
    path: str
    problem: str
    required_correction: str
    state: str
    provenance: dict[str, Any] = field(default_factory=dict)
    verification_history: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
