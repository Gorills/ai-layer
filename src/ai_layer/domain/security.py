from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Capability(StrEnum):
    PROJECT_READ = "project.read"
    TASK_READ = "task.read"
    TASK_CREATE = "task.create"
    TASK_START = "task.start"
    TASK_CANCEL = "task.cancel"
    TASK_APPROVE = "task.approve"
    WORKSPACE_READ = "workspace.read"
    FILE_MODIFY = "file.modify"
    SHELL_EXECUTE = "shell.execute"
    GIT_COMMIT = "git.commit"
    GIT_PUSH = "git.push"
    EXTERNAL_EXECUTE = "external.execute"


DANGEROUS_CAPABILITIES = frozenset(
    {
        Capability.FILE_MODIFY,
        Capability.SHELL_EXECUTE,
        Capability.GIT_COMMIT,
        Capability.GIT_PUSH,
        Capability.EXTERNAL_EXECUTE,
    }
)


@dataclass(frozen=True, slots=True)
class Actor:
    actor_id: str
    kind: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    authenticated: bool = False

    def has(self, capability: Capability | str) -> bool:
        wanted = str(capability)
        return "*" in self.capabilities or wanted in self.capabilities


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    required_capability: str
    reason: str
    approval_required: bool = False


SYSTEM_ACTOR = Actor(
    actor_id="system:internal",
    kind="system",
    capabilities=frozenset({"*"}),
    authenticated=True,
)

LOCAL_TRUSTED_ACTOR = Actor(
    actor_id="local:trusted",
    kind="local",
    capabilities=frozenset({"*"}),
    authenticated=True,
)
