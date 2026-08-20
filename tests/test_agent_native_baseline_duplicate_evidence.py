from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_baseline = runpy.run_path(str(ROOT / "scripts" / "agent_native_baseline_lib.py"))
finalize_journey = _baseline["finalize_journey"]
journey_event = _baseline["journey_event"]
new_journey_trace = _baseline["new_journey_trace"]


def test_duplicate_metric_requires_request_fingerprint() -> None:
    trace = new_journey_trace("ordinary_known_location_change", "codex")
    request = {"project_root": "/redacted", "goal": "profiled only"}
    trace["events"] = [
        journey_event("ai_layer_call", "project_status"),
        journey_event("ai_layer_call", "project_status"),
        journey_event("ai_layer_call", "project_status", request_payload=request),
        journey_event("ai_layer_call", "project_status", request_payload=request),
    ]

    metrics = finalize_journey(trace)["metrics"]

    assert metrics["ai_layer_call_count"] == 4
    assert metrics["duplicate_control_plane_call_count"] == 1
