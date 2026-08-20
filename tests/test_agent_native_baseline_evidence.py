from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from ai_layer import __version__

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BASELINE_PATH = ROOT / "docs" / "evidence" / f"{__version__}-agent-native-phase0-baseline.json"
sys.path.insert(0, str(SCRIPTS))
try:
    _generator = runpy.run_path(str(SCRIPTS / "agent_native_baseline.py"))
finally:
    sys.path.pop(0)
build_report = _generator["build_report"]


def test_configured_phase0_journeys_are_executable_and_quantitative() -> None:
    report = build_report()
    contract = report["journey_trace_contract"]
    fixtures = contract["fixtures"]

    assert contract["fixture_evidence"] == "configured_protocol_not_observed_host_run"
    assert {item["journey"] for item in fixtures} == set(contract["journeys"])
    expected_calls = {
        "ordinary_known_location_change": 4,
        "ordinary_unknown_location_change": 5,
        "explicit_standard_change": 8,
        "native_to_reviewed_escalation": 7,
        "continue_after_restart": 4,
        "epic_continuation": 10,
    }
    for fixture in fixtures:
        assert fixture["events"]
        assert fixture["host"] == "protocol-configured"
        assert fixture["metrics"]["ai_layer_call_count"] == expected_calls[fixture["journey"]]
        assert fixture["metrics"]["observability_class_counts"] == {
            "configured": len(fixture["events"]),
            "observed": 0,
            "unsupported": 0,
        }

    unknown = next(
        item for item in fixtures if item["journey"] == "ordinary_unknown_location_change"
    )
    assert unknown["metrics"]["retrieval_usefulness"]["candidate_to_inspected_hit_rate"] == 0.5


def test_committed_phase0_baseline_matches_live_runtime() -> None:
    report = build_report()
    expected = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    assert BASELINE_PATH.is_file()
    assert BASELINE_PATH.read_text(encoding="utf-8") == expected
