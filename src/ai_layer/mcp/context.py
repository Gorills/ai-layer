from __future__ import annotations

import os
from pathlib import Path

from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError


class ProjectContextRequiredError(StructuredError):
    """Raised when a project-scoped MCP call has no safe project identity."""


_BOUND_PROJECT_ROOTS: set[str] = set()


def reset_project_bindings_for_tests() -> None:
    _BOUND_PROJECT_ROOTS.clear()


def bind_project_root(root: str | Path) -> str:
    resolved = str(Path(root).expanduser().resolve())
    _BOUND_PROJECT_ROOTS.add(resolved)
    return resolved


def resolve_project_root(project_root: str | None, *, tool: str) -> str:
    """Resolve project identity without ever falling back to process cwd.

    Precedence is explicit tool argument -> project-specific MCP environment -> one unambiguous
    project successfully bound earlier in this MCP process. If multiple projects were used in the
    same process, an omitted argument is intentionally rejected rather than guessing.
    """
    explicit = (project_root or "").strip()
    if explicit:
        return str(Path(explicit).expanduser().resolve())

    env_root = (os.getenv("AI_LAYER_PROJECT_ROOT") or "").strip()
    if env_root:
        return str(Path(env_root).expanduser().resolve())

    if len(_BOUND_PROJECT_ROOTS) == 1:
        return next(iter(_BOUND_PROJECT_ROOTS))
    if len(_BOUND_PROJECT_ROOTS) > 1:
        known = ", ".join(sorted(_BOUND_PROJECT_ROOTS))
        raise ProjectContextRequiredError(
            code=ErrorCode.PROJECT_CONTEXT_AMBIGUOUS,
            category=ErrorCategory.VALIDATION,
            message=(
                f"{tool} is project-scoped and this MCP process has seen multiple projects: {known}. "
                "Pass the exact canonical `project_root` returned by the relevant memory_context/task response. "
                "Do not use shell cwd or bypass Task Layer."
            ),
            retryable=True,
            required_action="Pass the exact canonical project_root for the intended registered project.",
        )
    raise ProjectContextRequiredError(
        code=ErrorCode.PROJECT_CONTEXT_REQUIRED,
        category=ErrorCategory.VALIDATION,
        message=(
            f"{tool} is project-scoped but no explicit, environment, or previously bound project exists. "
            "Pass `project_root` explicitly using the exact canonical root returned by a successful "
            "project_info/memory_context/task response. Do not derive it from MCP cwd and do not bypass Task Layer."
        ),
        retryable=True,
        required_action="Pass the exact canonical project_root for the intended registered project.",
    )
