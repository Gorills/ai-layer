from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ai_layer import __version__
from ai_layer.observability.context_common import profile_value, redact_value

BASELINE_SCHEMA_VERSION = 1
JOURNEY_TRACE_SCHEMA_VERSION = 1
OBSERVABILITY_CLASSES = ("observed", "configured", "unsupported")
PHASE0_JOURNEYS = (
    "ordinary_known_location_change",
    "ordinary_unknown_location_change",
    "explicit_standard_change",
    "native_to_reviewed_escalation",
    "continue_after_restart",
    "epic_continuation",
)
FIELD_RUN_HOSTS = ("codex", "claude-code", "cursor", "antigravity-gemini")
JOURNEY_EVENT_KINDS = (
    "ai_layer_call",
    "native_search",
    "native_read",
    "native_edit",
    "check",
    "review",
    "host_lifecycle",
)
_OPERATION_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")
_PROFILE_KEYS = {"chars", "utf8_bytes", "estimated_tokens", "sha256"}
_PROFILE_COUNTER_KEYS = ("chars", "utf8_bytes", "estimated_tokens")
_EVENT_KEYS = {
    "kind",
    "operation",
    "ok",
    "observability_class",
    "relevant_source",
    "correction_retry",
    "failure_class",
    "request_profile",
    "response_profile",
    "latency_ms",
    "candidate_paths",
    "reviewed_paths",
    "changed_paths",
}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _tool_definition(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "parameters", None)
    if not isinstance(schema, Mapping):
        raise RuntimeError(
            f"Registered MCP tool {getattr(tool, 'name', '<unknown>')} has no input schema"
        )
    result: dict[str, Any] = {"name": str(tool.name), "inputSchema": _jsonable(schema)}
    for attribute, wire_name in (
        ("title", "title"),
        ("description", "description"),
        ("output_schema", "outputSchema"),
        ("annotations", "annotations"),
        ("icons", "icons"),
        ("meta", "_meta"),
    ):
        value = getattr(tool, attribute, None)
        if value is not None:
            result[wire_name] = _jsonable(value)
    return result


def runtime_catalog_snapshot(
    mcp_server: Any, *, tool_handlers: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Measure the registered runtime catalog without executing product tools."""
    manager = getattr(mcp_server, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        raise RuntimeError("MCP runtime tool registry is unavailable")
    tools = sorted(manager.list_tools(), key=lambda item: str(item.name))
    names = [str(tool.name) for tool in tools]
    if len(names) != len(set(names)):
        raise RuntimeError("MCP runtime catalog contains duplicate tool names")
    if tool_handlers is not None and names != sorted(str(name) for name in tool_handlers):
        raise RuntimeError("MCP runtime catalog differs from TOOL_HANDLERS")

    entries: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    for tool in tools:
        definition = _tool_definition(tool)
        definitions.append(definition)
        entries.append(
            {
                "name": definition["name"],
                "input_schema_profile": profile_value(definition["inputSchema"]),
                "tool_definition_profile": profile_value(definition),
                "definition": definition,
            }
        )
    return {
        "tool_count": len(entries),
        "catalog_profile": profile_value({"tools": definitions}),
        "total_input_schema_utf8_bytes": sum(
            int(item["input_schema_profile"]["utf8_bytes"]) for item in entries
        ),
        "total_tool_definition_utf8_bytes": sum(
            int(item["tool_definition_profile"]["utf8_bytes"]) for item in entries
        ),
        "tools": entries,
    }


def _identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _OPERATION_RE.fullmatch(value):
        raise ValueError(f"journey {field} must be a short stable identifier")
    return value


def _boolean(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"journey event {field} must be boolean")
    return value


def _latency(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("journey event latency_ms must be a non-negative number")
    return float(value)


def _portable_paths(paths: Sequence[str]) -> list[str]:
    if isinstance(paths, (str, bytes, bytearray)):
        raise ValueError("journey paths must be a sequence of strings")
    if any(not isinstance(path, str) for path in paths):
        raise ValueError("journey paths must be strings")
    result = set()
    for path in paths:
        raw = path.strip().replace("\\", "/")
        candidate = PurePosixPath(raw)
        if (
            not raw
            or re.match(r"^[A-Za-z]:/", raw)
            or candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.as_posix() in {"", "."}
        ):
            raise ValueError(
                "journey paths must be repository-relative and may not traverse parents"
            )
        result.add(candidate.as_posix())
    return sorted(result)


def journey_event(
    kind: str,
    operation: str,
    *,
    request_payload: Any = None,
    response_payload: Any = None,
    latency_ms: float | None = None,
    ok: bool = True,
    candidate_paths: Sequence[str] = (),
    reviewed_paths: Sequence[str] = (),
    changed_paths: Sequence[str] = (),
    relevant_source: bool = False,
    correction_retry: bool = False,
    failure_class: str | None = None,
    observability_class: str = "observed",
) -> dict[str, Any]:
    """Create a privacy-bounded trace event; raw payloads are never retained."""
    if kind not in JOURNEY_EVENT_KINDS:
        raise ValueError(f"Unsupported journey event kind: {kind}")
    operation = _identifier(operation, field="operation")
    if observability_class not in OBSERVABILITY_CLASSES:
        raise ValueError(f"Unsupported observability class: {observability_class}")
    ok = _boolean(ok, field="ok")
    relevant_source = _boolean(relevant_source, field="relevant_source")
    correction_retry = _boolean(correction_retry, field="correction_retry")
    latency = _latency(latency_ms)
    if failure_class is not None:
        failure_class = _identifier(failure_class, field="failure_class")
    if not ok and failure_class is None:
        raise ValueError("failed journey events require failure_class")

    event: dict[str, Any] = {
        "kind": kind,
        "operation": operation,
        "ok": ok,
        "observability_class": observability_class,
        "relevant_source": relevant_source,
        "correction_retry": correction_retry,
    }
    if failure_class is not None:
        event["failure_class"] = failure_class
    if request_payload is not None:
        event["request_profile"] = profile_value(redact_value(request_payload))
    if response_payload is not None:
        event["response_profile"] = profile_value(redact_value(response_payload))
    if latency is not None:
        event["latency_ms"] = latency
    for field, paths in (
        ("candidate_paths", candidate_paths),
        ("reviewed_paths", reviewed_paths),
        ("changed_paths", changed_paths),
    ):
        normalized = _portable_paths(paths)
        if normalized:
            event[field] = normalized
    return event


def retrieval_usefulness(
    candidate_paths: Sequence[str],
    *,
    reviewed_paths: Sequence[str],
    changed_paths: Sequence[str],
) -> dict[str, Any]:
    candidates = _portable_paths(candidate_paths)
    reviewed = set(_portable_paths(reviewed_paths))
    changed = set(_portable_paths(changed_paths))
    inspected_hits = [path for path in candidates if path in reviewed or path in changed]
    changed_hits = [path for path in candidates if path in changed]

    def ratio(count: int) -> float | None:
        return round(count / len(candidates), 6) if candidates else None

    return {
        "candidate_count": len(candidates),
        "reviewed_path_count": len(reviewed),
        "changed_path_count": len(changed),
        "inspected_hit_count": len(inspected_hits),
        "changed_hit_count": len(changed_hits),
        "candidate_to_inspected_hit_rate": ratio(len(inspected_hits)),
        "candidate_to_changed_hit_rate": ratio(len(changed_hits)),
        "inspected_hit_paths": inspected_hits,
        "changed_hit_paths": changed_hits,
    }


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    return round(ordered[max(0, math.ceil(percentile * len(ordered)) - 1)], 3)


def summarize_journey(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ai_calls = [event for event in events if event.get("kind") == "ai_layer_call"]
    latencies = [float(event["latency_ms"]) for event in ai_calls if "latency_ms" in event]
    first_relevant = next(
        (index for index, event in enumerate(events) if event.get("relevant_source") is True),
        None,
    )
    first_edit = next(
        (index for index, event in enumerate(events) if event.get("kind") == "native_edit"),
        None,
    )

    def discovery_before(boundary: int | None) -> int | None:
        if boundary is None:
            return None
        return sum(
            event.get("kind") in {"native_search", "native_read"} for event in events[:boundary]
        )

    seen: set[tuple[str, str | None]] = set()
    duplicates = 0
    for event in ai_calls:
        request = event.get("request_profile")
        digest = request.get("sha256") if isinstance(request, Mapping) else None
        identity = (str(event.get("operation") or ""), str(digest) if digest else None)
        duplicates += identity in seen
        seen.add(identity)

    candidates = [str(path) for event in events for path in event.get("candidate_paths", ())]
    reviewed = [str(path) for event in events for path in event.get("reviewed_paths", ())]
    changed = [str(path) for event in events for path in event.get("changed_paths", ())]
    retries = sum(event.get("correction_retry") is True for event in ai_calls)
    failures: dict[str, int] = {}
    classes = {name: 0 for name in OBSERVABILITY_CLASSES}
    for event in events:
        failure = event.get("failure_class")
        if isinstance(failure, str):
            failures[failure] = failures.get(failure, 0) + 1
        observed = event.get("observability_class")
        if observed in classes:
            classes[str(observed)] += 1

    def total_profile(field: str, metric: str) -> int:
        return sum(
            int(event[field][metric]) for event in ai_calls if isinstance(event.get(field), Mapping)
        )

    return {
        "ai_layer_call_count": len(ai_calls),
        "request_payload_utf8_bytes": total_profile("request_profile", "utf8_bytes"),
        "response_payload_utf8_bytes": total_profile("response_profile", "utf8_bytes"),
        "request_payload_estimated_tokens": total_profile("request_profile", "estimated_tokens"),
        "response_payload_estimated_tokens": total_profile("response_profile", "estimated_tokens"),
        "mcp_latency_sample_count": len(latencies),
        "mcp_latency_ms_p50": _percentile(latencies, 0.50),
        "mcp_latency_ms_p95": _percentile(latencies, 0.95),
        "observability_class_counts": classes,
        "native_search_read_before_first_relevant_source": discovery_before(first_relevant),
        "native_search_read_before_first_edit": discovery_before(first_edit),
        "engineering_check_count": sum(event.get("kind") == "check" for event in events),
        "duplicate_control_plane_call_count": duplicates,
        "workflow_correction_retry_count": retries,
        "workflow_correction_retry_rate": round(retries / len(ai_calls), 6) if ai_calls else None,
        "failure_classes": dict(sorted(failures.items())),
        "retrieval_usefulness": retrieval_usefulness(
            candidates,
            reviewed_paths=reviewed,
            changed_paths=changed,
        ),
    }


def new_journey_trace(journey: str, host: str) -> dict[str, Any]:
    if journey not in PHASE0_JOURNEYS:
        raise ValueError("unsupported Phase 0 journey")
    host = _identifier(host, field="host")
    return {
        "schema_version": JOURNEY_TRACE_SCHEMA_VERSION,
        "journey": journey,
        "host": host,
        "events": [],
    }


def _validate_profile(value: Any, field: str) -> None:
    if not isinstance(value, Mapping) or set(value) != _PROFILE_KEYS:
        raise ValueError(f"{field} must be a profile_value() result")
    for key in _PROFILE_COUNTER_KEYS:
        counter = value.get(key)
        if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
            raise ValueError(f"{field} {key} must be a non-negative integer")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256") or "")):
        raise ValueError(f"{field} sha256 must be a lowercase hex digest")


def finalize_journey(trace: Mapping[str, Any]) -> dict[str, Any]:
    journey = trace.get("journey")
    host = trace.get("host")
    if not isinstance(journey, str) or not isinstance(host, str):
        raise ValueError("journey and host must be strings")
    result = new_journey_trace(journey, host)
    events = trace.get("events") or []
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        raise ValueError("journey events must be a sequence")

    normalized: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("journey events must be objects")
        unknown = sorted(set(event) - _EVENT_KEYS)
        if unknown:
            raise ValueError(f"journey event contains unknown fields: {unknown}")
        required = {
            "kind",
            "operation",
            "ok",
            "observability_class",
            "relevant_source",
            "correction_retry",
        }
        missing = sorted(required - set(event))
        if missing:
            raise ValueError(f"journey event missing fields: {missing}")
        rebuilt = journey_event(
            event["kind"],
            event["operation"],
            ok=event["ok"],
            relevant_source=event["relevant_source"],
            correction_retry=event["correction_retry"],
            failure_class=event.get("failure_class"),
            observability_class=event["observability_class"],
            latency_ms=event.get("latency_ms"),
            candidate_paths=event.get("candidate_paths", ()),
            reviewed_paths=event.get("reviewed_paths", ()),
            changed_paths=event.get("changed_paths", ()),
        )
        for field in ("request_profile", "response_profile"):
            if field in event:
                _validate_profile(event[field], field)
                rebuilt[field] = dict(event[field])
        normalized.append(rebuilt)
    result["events"] = normalized
    result["metrics"] = summarize_journey(normalized)
    return result


def phase0_journey_fixtures() -> list[dict[str, Any]]:
    return [new_journey_trace(journey, "unassigned") for journey in PHASE0_JOURNEYS]


def field_run_checklist() -> dict[str, Any]:
    capabilities = {
        "bootstrap_delivery": "configured",
        "mcp_binding": "configured",
        "native_skill_delivery": "configured",
        "session_lifecycle_hooks": "unsupported",
        "subagent_lifecycle_hooks": "unsupported",
        "native_tool_lifecycle_hooks": "unsupported",
    }
    return {
        "observability_classes": list(OBSERVABILITY_CLASSES),
        "evidence_rule": "upgrade configured to observed only from real host evidence",
        "hosts": [
            {
                "host": host,
                "capabilities": dict(capabilities),
                "journeys": list(PHASE0_JOURNEYS),
            }
            for host in FIELD_RUN_HOSTS
        ],
    }


def build_baseline_report(
    mcp_server: Any,
    *,
    tool_handlers: Mapping[str, Any],
    mcp_instructions: str,
    bootstrap_text: str = "",
    skill_documents: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    catalog = runtime_catalog_snapshot(mcp_server, tool_handlers=tool_handlers)
    skills = {name: profile_value(text) for name, text in sorted((skill_documents or {}).items())}
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "package_version": __version__,
        "scope": "agent_native_phase0_measurement_only",
        "catalog": catalog,
        "configured_context": {
            "mcp_instructions_profile": profile_value(mcp_instructions),
            "bootstrap_profile": profile_value(bootstrap_text),
            "skill_document_profiles": skills,
            "estimated_tokens_rule": "ceil(UTF-8 bytes / 4); approximation only",
            "host_schema_visibility": "configured_not_runtime_verified",
        },
        "journey_trace_contract": {
            "schema_version": JOURNEY_TRACE_SCHEMA_VERSION,
            "journeys": list(PHASE0_JOURNEYS),
            "event_kinds": list(JOURNEY_EVENT_KINDS),
            "fixtures": phase0_journey_fixtures(),
        },
        "field_run_checklist": field_run_checklist(),
        "privacy": {
            "raw_prompt": "not_recorded",
            "raw_source_body": "not_recorded",
            "request_response": "profile_only",
            "repository_locations": "relative_paths_only",
        },
    }


def write_baseline_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return output
