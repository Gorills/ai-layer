from __future__ import annotations

from pathlib import Path

from agent_native_baseline_lib import (
    build_baseline_report,
    finalize_journey,
    journey_event,
    new_journey_trace,
    write_baseline_report,
)
from agent_native_phase0_fixtures import configured_journey_fixtures

from ai_layer import __version__
from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.mcp.runtime import MCP_INSTRUCTIONS, TOOL_HANDLERS
from ai_layer.mcp.server import mcp

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / f"{__version__}-agent-native-phase0-baseline.json"


def _skill_documents() -> dict[str, str]:
    root = ROOT / "src" / "ai_layer" / "builtin_skills"
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.md"))}


def build_report() -> dict:
    report = build_baseline_report(
        mcp,
        tool_handlers=TOOL_HANDLERS,
        mcp_instructions=MCP_INSTRUCTIONS,
        bootstrap_text=native_bootstrap_markdown(),
        skill_documents=_skill_documents(),
    )
    contract = report["journey_trace_contract"]
    contract["fixture_evidence"] = "configured_protocol_not_observed_host_run"
    contract["fixtures"] = configured_journey_fixtures(
        event_builder=journey_event,
        trace_builder=new_journey_trace,
        finalizer=finalize_journey,
    )
    return report


def main() -> None:
    print(write_baseline_report(DEFAULT_OUTPUT, build_report()))


if __name__ == "__main__":
    main()
