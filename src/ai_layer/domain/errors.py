from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    STATE = "state"
    REPOSITORY = "repository"
    VERIFICATION = "verification"
    TRANSPORT = "transport"
    PERSISTENCE = "persistence"
    GOVERNANCE = "governance"
    EXTERNAL = "external"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    STATE_CONFLICT = "STATE_CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    REQUEST_UNAUTHORIZED = "REQUEST_UNAUTHORIZED"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    PROJECT_CONTEXT_REQUIRED = "PROJECT_CONTEXT_REQUIRED"
    PROJECT_CONTEXT_AMBIGUOUS = "PROJECT_CONTEXT_AMBIGUOUS"
    TASK_NOT_ACTIVE = "TASK_NOT_ACTIVE"
    TASK_BLOCKED = "TASK_BLOCKED"
    STAGE_NOT_DELEGATED = "STAGE_NOT_DELEGATED"
    STAGE_KIND_MISMATCH = "STAGE_KIND_MISMATCH"
    UNMANAGED_STAGE_MUTATION = "UNMANAGED_STAGE_MUTATION"
    READONLY_STAGE_MUTATION = "READONLY_STAGE_MUTATION"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_TIMEOUT = "VERIFICATION_TIMEOUT"
    DATABASE_UNAVAILABLE = "AI_LAYER_DATABASE_UNAVAILABLE"
    CORE_UNAVAILABLE = "AI_LAYER_CORE_UNAVAILABLE"
    CORE_TIMEOUT_AMBIGUOUS = "AI_LAYER_CORE_TIMEOUT_AMBIGUOUS"
    CORE_DELIVERY_AMBIGUOUS = "AI_LAYER_CORE_DELIVERY_AMBIGUOUS"
    CORE_PROTOCOL_ERROR = "AI_LAYER_CORE_PROTOCOL_ERROR"
    GOVERNANCE_APPROVAL_REQUIRED = "GOVERNANCE_APPROVAL_REQUIRED"
    UPDATE_CHANNEL_INVALID = "UPDATE_CHANNEL_INVALID"
    UPDATE_MANIFEST_INVALID = "UPDATE_MANIFEST_INVALID"
    UPDATE_SIGNATURE_INVALID = "UPDATE_SIGNATURE_INVALID"
    UPDATE_ARTIFACT_INVALID = "UPDATE_ARTIFACT_INVALID"
    UPDATE_CHECKSUM_MISMATCH = "UPDATE_CHECKSUM_MISMATCH"
    UPDATE_PREFLIGHT_FAILED = "UPDATE_PREFLIGHT_FAILED"
    UPDATE_INSTALL_FAILED = "UPDATE_INSTALL_FAILED"


@dataclass(slots=True)
class StructuredError(Exception):
    code: str
    category: ErrorCategory
    message: str
    retryable: bool = False
    required_action: str | None = None
    ids: dict[str, str] | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["code"] = str(self.code)
        payload["category"] = self.category.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StructuredError:
        category_raw = str(payload.get("category") or ErrorCategory.INTERNAL.value)
        try:
            category = ErrorCategory(category_raw)
        except ValueError:
            category = ErrorCategory.INTERNAL
        return cls(
            code=str(payload.get("code") or ErrorCode.INTERNAL_ERROR),
            category=category,
            message=str(payload.get("message") or "AI Layer operation failed"),
            retryable=bool(payload.get("retryable", False)),
            required_action=(
                str(payload["required_action"]) if payload.get("required_action") else None
            ),
            ids={str(k): str(v) for k, v in dict(payload.get("ids") or {}).items()} or None,
            details=dict(payload.get("details") or {}) or None,
        )


def normalize_error(exc: BaseException) -> StructuredError:
    """Map unstructured legacy exceptions without parsing their message text.

    Specific domain/application paths should raise StructuredError directly. This fallback exists at
    public protocol boundaries while legacy internals are migrated; classification is based only on
    exception type, never string prefixes or regexes.
    """
    if isinstance(exc, StructuredError):
        return exc
    if isinstance(exc, (ValueError, TypeError)):
        return StructuredError(
            code=ErrorCode.VALIDATION_FAILED,
            category=ErrorCategory.VALIDATION,
            message=str(exc) or "Request validation failed",
            retryable=True,
            required_action="Correct the request arguments and retry.",
            details={"legacy_exception_type": type(exc).__name__},
        )
    if isinstance(exc, TimeoutError):
        return StructuredError(
            code=ErrorCode.CORE_TIMEOUT_AMBIGUOUS,
            category=ErrorCategory.TRANSPORT,
            message=str(exc) or "Operation timed out after dispatch",
            retryable=False,
            required_action="Read durable state before deciding whether retry is safe.",
            details={"legacy_exception_type": type(exc).__name__},
        )
    if isinstance(exc, OSError):
        return StructuredError(
            code=ErrorCode.CORE_UNAVAILABLE,
            category=ErrorCategory.EXTERNAL,
            message=str(exc) or "Required local runtime resource is unavailable",
            retryable=True,
            required_action="Restore the required local service/resource and retry.",
            details={"legacy_exception_type": type(exc).__name__},
        )
    if isinstance(exc, RuntimeError):
        return StructuredError(
            code=ErrorCode.STATE_CONFLICT,
            category=ErrorCategory.STATE,
            message=str(exc) or "Operation is not valid in the current durable state",
            retryable=False,
            required_action="Inspect the current state/next action and resolve the reported conflict.",
            details={"legacy_exception_type": type(exc).__name__},
        )
    return StructuredError(
        code=ErrorCode.INTERNAL_ERROR,
        category=ErrorCategory.INTERNAL,
        message="AI Layer encountered an unexpected internal error.",
        retryable=False,
        required_action="Run diagnostics and inspect the correlated server error before retrying.",
        details={"legacy_exception_type": type(exc).__name__},
    )
