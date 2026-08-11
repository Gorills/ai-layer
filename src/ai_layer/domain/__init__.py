"""Pure semantic contracts for AI Layer capabilities.

Modules in this package must not import transports, persistence, hosts, providers, or filesystem/network infrastructure.
"""
from ai_layer.domain.agents import AgentRequirement, ModelAssurance, ModelIdentity
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.domain.tasks import FindingContract, NextAction, RepositoryDelta, StageKind, TaskStatus
from ai_layer.domain.verification import VerificationAssurance, VerificationResult

__all__ = [
    "AgentRequirement", "ErrorCategory", "ErrorCode", "FindingContract", "ModelAssurance",
    "ModelIdentity", "NextAction", "RepositoryDelta",
    "StageKind", "StructuredError", "TaskStatus", "VerificationAssurance", "VerificationResult",
]
