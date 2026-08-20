from __future__ import annotations

import json
import runpy
from pathlib import Path

from ai_layer import __version__
from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.mcp.runtime import MCP_INSTRUCTIONS, TOOL_HANDLERS
from ai_layer.mcp.server import mcp

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "docs" / "evidence" / f"{__version__}-agent-native-phase0-baseline.json"
_baseline = runpy.run_path(str(ROOT / "scripts" / "agent_native_baseline_lib.py"))
build_baseline_report = _baseline["build_baseline_report"]


def _skill_documents() -> dict[str, str]:
    root = ROOT / "src" / "ai_layer" / "builtin_skills"
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.md"))}


def test_committed_phase0_baseline_matches_live_runtime() -> None:
    report = build_baseline_report(
        mcp,
        tool_handlers=TOOL_HANDLERS,
        mcp_instructions=MCP_INSTRUCTIONS,
        bootstrap_text=native_bootstrap_markdown(),
        skill_documents=_skill_documents(),
    )
    expected = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    assert BASELINE_PATH.is_file()
    assert BASELINE_PATH.read_text(encoding="utf-8") == expected
