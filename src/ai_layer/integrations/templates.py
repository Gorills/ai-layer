from __future__ import annotations

from pathlib import Path

from ai_layer.domain.orchestrator import native_bootstrap_markdown


def workflow(project_root: Path) -> str:
    """Legacy compatibility helper: project text bridges are no longer installed in standard mode."""
    root = str(project_root.resolve())
    return f"""# Local AI Development Layer — project binding (legacy compatibility)\n\nCanonical project root: `{root}`. AI Layer workflow is delivered by the global native bootstrap and MCP Project Intelligence/control-plane tools.\n"""


def global_bootstrap_workflow() -> str:
    return "# Local AI Development Layer — global bootstrap\n\n" + native_bootstrap_markdown()
