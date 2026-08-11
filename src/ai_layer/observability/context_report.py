from __future__ import annotations

import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from ai_layer import __version__
from ai_layer.observability.context_common import (
    project_identity,
    report_path,
    tail_events,
    trace_path,
    utcnow_iso,
)

REPORT_SCHEMA_VERSION = 2


def _build_findings(events: list[dict]) -> list[dict]:
    findings: list[dict] = []
    by_session: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_session[str(event.get("mcp_session_id") or "unknown")].append(event)
    for session_id, session_events in by_session.items():
        context_calls = [
            event
            for event in session_events
            if event.get("tool") == "memory_context" and event.get("ok")
        ]
        if len(context_calls) > 1:
            findings.append(
                {
                    "severity": "warning",
                    "code": "DUPLICATE_MEMORY_CONTEXT",
                    "session_id": session_id,
                    "count": len(context_calls),
                    "message": (
                        "memory_context was delivered more than once in one MCP session; verify that "
                        "task goal or external repository state actually changed."
                    ),
                }
            )
        for event in context_calls:
            result = event.get("result") or {}
            budget = result.get("context_budget") or {}
            if budget.get("policy_over_soft_target"):
                findings.append(
                    {
                        "severity": "warning",
                        "code": "POLICY_OVER_SOFT_TARGET",
                        "session_id": session_id,
                        "policy_chars": budget.get("policy_chars"),
                        "message": (
                            "Mandatory policy exceeded its configured soft target and cannot be "
                            "silently truncated."
                        ),
                    }
                )
            if int(budget.get("raw_source_memory_chars") or 0) > 0:
                findings.append(
                    {
                        "severity": "error",
                        "code": "RAW_SOURCE_MEMORY_REGRESSION",
                        "session_id": session_id,
                        "raw_source_memory_chars": budget.get("raw_source_memory_chars"),
                        "message": "Current-source text entered memory_context; host-native source discovery should own current code.",
                    }
                )
            stale = list(((result.get("task_brief") or {}).get("stale_knowledge") or []))
            if stale:
                findings.append(
                    {
                        "severity": "info",
                        "code": "STALE_PROJECT_KNOWLEDGE_RETURNED",
                        "session_id": session_id,
                        "count": len(stale),
                        "message": "Relevant reviewed knowledge is stale; inspect current source before relying on implementation details.",
                    }
                )
            # Old traces remain readable after the native-first migration, but are explicitly
            # marked as legacy instead of being interpreted as the current routing model.
            if result.get("skill_plan") or result.get("skills"):
                findings.append(
                    {
                        "severity": "info",
                        "code": "LEGACY_SKILL_ROUTING_TRACE",
                        "session_id": session_id,
                        "message": (
                            "This trace predates host-native skill routing and contains the retired "
                            "AI Layer planner/autoload payload."
                        ),
                    }
                )
        fetch_counter: Counter[tuple[str, str]] = Counter()
        for event in session_events:
            fetch = event.get("skill_fetch") or {}
            slug = str(fetch.get("slug") or "")
            section = str(fetch.get("section") or "")
            if not slug:
                continue
            fetch_counter[(slug, section)] += 1
            if fetch.get("full_skill"):
                findings.append(
                    {
                        "severity": "warning",
                        "code": "FULL_SKILL_FETCH",
                        "session_id": session_id,
                        "skill": slug,
                        "estimated_tokens": (fetch.get("content") or {}).get("estimated_tokens"),
                        "message": (
                            "A full authoritative skill was fetched; verify that one targeted section "
                            "would not have been sufficient."
                        ),
                    }
                )
        for (slug, section), count in fetch_counter.items():
            if count > 1:
                findings.append(
                    {
                        "severity": "warning",
                        "code": "REPEATED_SKILL_FETCH",
                        "session_id": session_id,
                        "skill": slug,
                        "section": section,
                        "count": count,
                        "message": "The same skill section was fetched repeatedly in one MCP session.",
                    }
                )
    return findings


def _configured_token_summary(configured: dict) -> dict:
    result: dict[str, int | dict] = {}
    for key in ("global_bootstrap", "project_rule", "mcp_server_instructions", "mcp_tool_catalog"):
        profile = (configured.get(key) or {}).get("profile") or {}
        result[key] = int(profile.get("estimated_tokens") or 0)
    result["worker_profiles"] = {
        str(item.get("name") or "unknown"): int(
            ((item.get("profile") or {}).get("estimated_tokens") or 0)
        )
        for item in (configured.get("configured_worker_profiles") or [])
    }
    native = configured.get("native_skill_catalog") or {}
    result["native_skill_catalog_metadata"] = {
        host: int(((data.get("catalog_metadata_profile") or {}).get("estimated_tokens") or 0))
        for host, data in (native.get("hosts") or {}).items()
    }
    return result


def _aggregate_dynamic_context(events: list[dict]) -> dict:
    delivered_tokens: dict[str, int] = defaultdict(int)
    delivered_bytes: dict[str, int] = defaultdict(int)
    component_tokens: dict[str, int] = defaultdict(int)
    skill_gets: Counter[str] = Counter()
    skill_get_tokens: dict[str, int] = defaultdict(int)
    full_fetches = 0
    legacy_autoload_tokens = 0
    for event in events:
        if not event.get("ok"):
            continue
        profile = event.get("result_profile") or {}
        tool = str(event.get("tool") or "unknown")
        delivered_tokens[tool] += int(profile.get("estimated_tokens") or 0)
        delivered_bytes[tool] += int(profile.get("utf8_bytes") or 0)
        if tool == "memory_context":
            for name, item_profile in (
                (event.get("breakdown") or {}).get("components") or {}
            ).items():
                component_tokens[str(name)] += int(
                    (item_profile or {}).get("estimated_tokens") or 0
                )
            for item in (event.get("breakdown") or {}).get("skills") or []:
                legacy_autoload_tokens += int(
                    (item.get("content") or {}).get("estimated_tokens") or 0
                )
        fetch = event.get("skill_fetch") or {}
        if fetch.get("slug"):
            key = f"{fetch.get('slug')}:{fetch.get('section') or 'full'}"
            skill_gets[key] += 1
            skill_get_tokens[str(fetch.get("slug"))] += int(
                (fetch.get("content") or {}).get("estimated_tokens") or 0
            )
            full_fetches += int(bool(fetch.get("full_skill")))
    return {
        "delivered_tokens": delivered_tokens,
        "delivered_bytes": delivered_bytes,
        "component_tokens": component_tokens,
        "skill_gets": skill_gets,
        "skill_get_tokens": skill_get_tokens,
        "full_fetches": full_fetches,
        "legacy_autoload_tokens": legacy_autoload_tokens,
    }


def build_report(project_root: str | Path, *, limit: int = 500) -> dict:
    root = str(Path(project_root).expanduser().resolve())
    identity = project_identity(root)
    if identity is None:
        raise RuntimeError(f"Project is not registered: {root}")
    project_id, registry = identity
    events = tail_events(trace_path(root), limit=limit)
    tool_counts = Counter(str(event.get("tool") or "unknown") for event in events)
    aggregates = _aggregate_dynamic_context(events)
    delivered_tokens = aggregates["delivered_tokens"]
    delivered_bytes = aggregates["delivered_bytes"]
    component_tokens = aggregates["component_tokens"]
    skill_gets = aggregates["skill_gets"]
    skill_get_tokens = aggregates["skill_get_tokens"]
    full_fetches = aggregates["full_fetches"]
    legacy_autoload_tokens = aggregates["legacy_autoload_tokens"]

    latest_context = next(
        (
            event
            for event in reversed(events)
            if event.get("tool") == "memory_context" and event.get("ok")
        ),
        None,
    )
    configured = (latest_context or {}).get("configured_context") or {}
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": utcnow_iso(),
        "server_version": __version__,
        "project": {
            "project_id": project_id,
            "root_path": root,
            "name": registry.get("name") or Path(root).name,
            "mode": registry.get("mode", "standard"),
        },
        "coverage": {
            "AI_LAYER_OBSERVED": [
                "size/hash profile for each AI Layer MCP result",
                "redacted memory_context payload and component sizes",
                "reviewed Project Knowledge/history delivered by memory_context",
                "knowledge_list/draft tool calls observable through AI Layer MCP",
                "skill_get slug/section/full-vs-targeted plus returned bytes/estimated tokens",
                "duplicate skill_get calls within one observed MCP session",
            ],
            "AI_LAYER_CONFIGURED": [
                "global/project bootstrap rules",
                "MCP server instructions and registered AI Layer tool catalog",
                "native skill descriptor files and metadata-surface sizes per supported host",
            ],
            "HOST_HIDDEN": [
                "host system prompt and full chat context",
                "whether a native skill was selected automatically or invoked manually",
                "whether the host included every configured rule/tool schema on a model call",
                "exact tokenizer usage, prompt caching, compaction and billing",
                "whether the model cognitively used delivered guidance",
            ],
            "token_estimate": (
                "ceil(UTF-8 bytes / 4); relative context estimate only, never billing reconciliation"
            ),
        },
        "summary": {
            "events": len(events),
            "sessions": len({str(event.get("mcp_session_id") or "unknown") for event in events}),
            "tool_calls": dict(sorted(tool_counts.items())),
            "dynamic_tool_result_estimated_tokens_by_tool": dict(
                sorted(delivered_tokens.items(), key=lambda item: (-item[1], item[0]))
            ),
            "dynamic_tool_result_utf8_bytes_by_tool": dict(
                sorted(delivered_bytes.items(), key=lambda item: (-item[1], item[0]))
            ),
            "dynamic_tool_result_estimated_tokens_total": sum(delivered_tokens.values()),
            "memory_context_component_estimated_tokens": dict(
                sorted(component_tokens.items(), key=lambda item: (-item[1], item[0]))
            ),
            "configured_context_estimated_tokens": _configured_token_summary(configured),
        },
        "knowledge_flow": {
            "current_source_owner": "host-native",
            "scanner_role": "deterministic_repository_evidence",
            "raw_source_semantic_index_default": False,
            "memory_context_raw_source_chars": int(
                (((latest_context or {}).get("result") or {}).get("context_budget") or {}).get(
                    "raw_source_memory_chars"
                )
                or 0
            ),
            "knowledge_baseline_ready": bool(
                (((latest_context or {}).get("result") or {}).get("knowledge_state") or {}).get(
                    "baseline_ready"
                )
            ),
            "knowledge_status": (
                ((latest_context or {}).get("result") or {}).get("knowledge_state") or None
            ),
            "selection_note": "AI Layer observes delivered reviewed knowledge; it cannot prove the host/model cognitively used it.",
        },
        "skill_flow": {
            "routing_owner": "host-native",
            "ai_layer_runtime_planner_active": False,
            "automatic_domain_skill_injection": False,
            "automatic_domain_skill_estimated_tokens_current": 0,
            "legacy_autoload_estimated_tokens_in_retained_traces": legacy_autoload_tokens,
            "skill_get_calls": dict(sorted(skill_gets.items())),
            "skill_get_estimated_tokens_by_slug": dict(
                sorted(skill_get_tokens.items(), key=lambda item: (-item[1], item[0]))
            ),
            "full_skill_fetches": full_fetches,
            "selection_source": "HOST_HIDDEN: host-native automatic vs manual cannot be distinguished by AI Layer",
        },
        "latest_configured_context": configured or None,
        "findings": _build_findings(events),
        "events": events,
    }


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def write_latest_report(project_root: str | Path, *, limit: int = 500) -> Path:
    root = str(Path(project_root).expanduser().resolve())
    path = report_path(root)
    _atomic_json(path, build_report(root, limit=limit))
    return path
