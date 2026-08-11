from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from uuid import uuid4

from ai_layer.domain.security import Actor, SYSTEM_ACTOR

_CURRENT_TOOL: ContextVar[str | None] = ContextVar("ai_layer_current_tool", default=None)
_CURRENT_CLASS: ContextVar[str | None] = ContextVar("ai_layer_current_tool_class", default=None)
_CURRENT_OPERATION: ContextVar["OperationContext | None"] = ContextVar(
    "ai_layer_current_operation", default=None
)


@dataclass(frozen=True, slots=True)
class OperationContext:
    actor: Actor
    interface: str
    correlation_id: str
    command_id: str | None = None
    causation_id: str | None = None


@contextmanager
def operation_context(
    *,
    actor: Actor = SYSTEM_ACTOR,
    interface: str = "internal",
    correlation_id: str | None = None,
    command_id: str | None = None,
    causation_id: str | None = None,
) -> Iterator[OperationContext]:
    current = OperationContext(
        actor=actor,
        interface=str(interface or "internal")[:32],
        correlation_id=str(correlation_id or uuid4().hex)[:64],
        command_id=str(command_id)[:128] if command_id else None,
        causation_id=str(causation_id)[:64] if causation_id else None,
    )
    token = _CURRENT_OPERATION.set(current)
    try:
        yield current
    finally:
        _CURRENT_OPERATION.reset(token)


@contextmanager
def tool_execution_context(tool: str, tool_class: str) -> Iterator[None]:
    token_tool = _CURRENT_TOOL.set(tool)
    token_class = _CURRENT_CLASS.set(tool_class)
    existing = _CURRENT_OPERATION.get()
    operation = (
        nullcontext(existing)
        if existing is not None
        else operation_context(
            actor=Actor(
                actor_id="local:mcp",
                kind="local",
                capabilities=frozenset({"*"}),
                authenticated=True,
            ),
            interface="mcp",
        )
    )
    try:
        with operation:
            yield
    finally:
        _CURRENT_CLASS.reset(token_class)
        _CURRENT_TOOL.reset(token_tool)


def current_tool() -> str | None:
    return _CURRENT_TOOL.get()


def current_tool_class() -> str | None:
    return _CURRENT_CLASS.get()


def current_operation() -> OperationContext | None:
    return _CURRENT_OPERATION.get()


def interactive_request() -> bool:
    return _CURRENT_CLASS.get() in {"fast", "context", "long"}
