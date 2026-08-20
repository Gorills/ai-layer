from __future__ import annotations

from pathlib import Path

from ai_layer import __version__
from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.mcp.runtime import MCP_INSTRUCTIONS, TOOL_HANDLERS
from ai_layer.mcp.server import mcp
from agent_native_baseline_lib import build_baseline_report, write_baseline_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / f"{__version__}-agent-native-phase0-baseline.json"


def _skill_documents() -> dict[str, str]:
    root = ROOT / "src" / "ai_layer" / "builtin_skills"
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.md"))}


def main() -> None:
    report = build_baseline_report(
        mcp,
        tool_handlers=TOOL_HANDLERS,
        mcp_instructions=MCP_INSTRUCTIONS,
        bootstrap_text=native_bootstrap_markdown(),
        skill_documents=_skill_documents(),
    )
    print(write_baseline_report(DEFAULT_OUTPUT, report))


if __name__ == "__main__":
    main()
