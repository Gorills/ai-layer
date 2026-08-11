from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ModelAssurance(StrEnum):
    VERIFIED = "verified"
    HOST_REPORTED = "host_reported"
    REQUESTED_UNVERIFIED = "requested_unverified"


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    requested: str | None = None
    actual: str | None = None
    assurance: ModelAssurance = ModelAssurance.REQUESTED_UNVERIFIED
    host: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assurance"] = self.assurance.value
        return data


@dataclass(frozen=True, slots=True)
class AgentRequirement:
    role: str
    minimum_capability: str
    risk: str
    complexity: str
    uncertainty: str
    context_requirement: str
    readonly: bool
    isolation: str
    quality_cost_preference: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
