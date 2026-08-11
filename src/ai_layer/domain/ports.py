from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from ai_layer.domain.verification import VerificationRequest, VerificationResult


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    """Persistence-neutral identity for an immutable workflow repository snapshot."""

    id: UUID
    project_id: UUID
    digest: str
    file_count: int
    storage_backend: str
    schema_version: int


class WorkflowSnapshotStore(Protocol):
    """Strategic port for durable workflow recovery snapshots."""

    def create(
        self,
        *,
        project_id: UUID,
        state: dict[str, Any],
        snapshot_kind: str,
    ) -> SnapshotReference: ...

    def get(self, snapshot_id: UUID) -> SnapshotReference | None: ...

    def load(self, snapshot_id: UUID, *, expected_digest: str) -> dict[str, Any]: ...


class VerificationExecutor(Protocol):
    """Replaceable execution boundary for authoritative verification commands."""

    def execute(
        self,
        *,
        project_id: UUID,
        project_root: str,
        request: VerificationRequest,
    ) -> tuple[VerificationResult, dict[str, Any]]: ...
