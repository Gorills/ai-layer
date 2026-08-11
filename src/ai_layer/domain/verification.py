from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from ai_layer.domain.security import Capability


MAX_TIMEOUT_SECONDS = 900
MAX_COMMAND_PARTS = 64
MAX_COMMAND_PART_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    command: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = 300
    environment: dict[str, str] | None = None

    @property
    def required_capability(self) -> Capability:
        return Capability.SHELL_EXECUTE

    @classmethod
    def from_values(
        cls,
        command: list[str] | tuple[str, ...],
        *,
        cwd: str = ".",
        timeout_seconds: int = 300,
        environment: dict[str, str] | None = None,
    ) -> "VerificationRequest":
        parts = tuple(str(part) for part in command)
        if not parts or len(parts) > MAX_COMMAND_PARTS:
            raise ValueError(f"verification command must contain 1..{MAX_COMMAND_PARTS} argv items")
        if any(not part or len(part) > MAX_COMMAND_PART_CHARS for part in parts):
            raise ValueError("verification command contains an empty or oversized argv item")
        if timeout_seconds < 1 or timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise ValueError(f"verification timeout must be 1..{MAX_TIMEOUT_SECONDS} seconds")
        return cls(parts, str(cwd or "."), int(timeout_seconds), dict(environment or {}))


class VerificationAssurance(StrEnum):
    REPORTED = "reported"
    HOST_VERIFIED = "host_verified"
    AI_LAYER_VERIFIED = "ai_layer_verified"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    assurance: VerificationAssurance
    command: tuple[str, ...]
    cwd: str
    started_at: datetime
    completed_at: datetime
    exit_code: int | None
    timed_out: bool
    output_summary: str
    evidence_ref: str | None = None
    environment: dict[str, str] | None = None

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assurance"] = self.assurance.value
        data["command"] = list(self.command)
        data["started_at"] = self.started_at.isoformat()
        data["completed_at"] = self.completed_at.isoformat()
        data["passed"] = self.passed
        return data
