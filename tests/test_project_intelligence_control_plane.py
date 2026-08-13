from __future__ import annotations

from ai_layer.agents.policy import DEFAULT_CURSOR_MODELS
from ai_layer.application.context import (
    LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT,
    LEGACY_CONTEXT_SOURCE_POINTER_LIMIT,
    LEGACY_CONTEXT_SUMMARY_MAX_CHARS,
    _compact_legacy_context,
)
from ai_layer.core.mcp_runtime import (
    CONTEXT_TOOLS,
    FAST_TOOLS,
    LONG_TOOLS,
    REPLAY_SAFE_TOOLS,
    tool_runtime_class,
)
from ai_layer.domain.orchestrator import native_bootstrap_markdown
from ai_layer.domain.project_map import project_map_capability_contract
from ai_layer.memory.navigation import (
    build_navigation_document,
    extract_symbols,
    semantic_score_from_distance,
)


def test_python_navigation_keeps_symbols_but_not_default_values_or_body():
    source = """\nfrom fastapi import FastAPI\napp = FastAPI()\nSECRET = "do-not-store"\n\nclass PaymentService:\n    def create_payment(self, token="secret-default", amount: int = 10):\n        marker = "body-secret"\n        return marker\n\n@app.post("/payments")\ndef create_payment(payload, api_key="private-key"):\n    return PaymentService().create_payment(api_key)\n"""
    document = build_navigation_document(
        path="src/payments.py",
        text=source,
        language="python",
        purpose="Application source file.",
        imports=["fastapi"],
        risk_flags=[],
        content_sha256="a" * 64,
        scanner_schema=5,
    )
    text = document["navigation_text"]
    assert "PaymentService.create_payment" in text
    assert "POST /payments" in text
    assert "token=..." in text
    assert "api_key=..." in text
    assert "secret-default" not in text
    assert "private-key" not in text
    assert "body-secret" not in text
    assert "do-not-store" not in text


def test_javascript_navigation_extracts_names_without_source_bodies():
    source = """\nexport async function syncOrder(order, token = "secret") {\n  const internal = "body-secret";\n  return internal;\n}\nconst retryOrder = async (order) => order;\nclass OrderClient {}\n"""
    symbols = extract_symbols(source, "javascript")
    names = {item["name"] for item in symbols}
    assert {"syncOrder", "retryOrder", "OrderClient"} <= names
    assert all("secret" not in str(item) for item in symbols)


def test_semantic_distance_zero_is_a_perfect_match_not_a_missing_value():
    assert semantic_score_from_distance(0.0) == 1.0
    assert semantic_score_from_distance(1.0) == 0.0
    assert semantic_score_from_distance(None) == 0.0


def test_bootstrap_uses_status_and_project_map_without_disabling_native_execution():
    bootstrap = native_bootstrap_markdown()
    assert "project_status" in bootstrap
    assert "project_search" in bootstrap
    assert "project_map_reconcile" in bootstrap
    assert "knowledge_search" in bootstrap
    assert "host-native" in bootstrap
    assert "native reads, edits, shell, tests, code search and subagents are allowed" in bootstrap
    assert "first project-related tool call MUST be `memory_context" not in bootstrap
    assert "The top-level chat is the orchestrator, not an implementation worker" not in bootstrap


def test_project_map_contract_is_dynamic_and_explicit_for_old_workflows():
    contract = project_map_capability_contract(source_task_key="T-0042")
    assert contract["read"]["tool"] == "project_search"
    assert contract["update"]["tool"] == "project_map_reconcile"
    assert contract["update"]["source_task_key"] == "T-0042"
    assert contract["update"]["required"] == ["scope_paths", "source_task_key"]
    assert "domain_terms" in contract["update"]["entry_fields"]
    assert "no_changes_reason" in contract["update"]["optional"]
    assert "source_work_key" in contract["update"]["optional"]


def test_application_memory_context_compacts_legacy_composite_payload():
    legacy = {
        "project": {"name": "alia", "root_path": "/repo", "profile": {"framework": "legacy"}},
        "knowledge_state": {
            "verified": 5,
            "stale": 20,
            "draft": 0,
            "baseline_ready": False,
            "verified_categories": ["deployment"],
        },
        "task_brief": {
            "verified_knowledge": [
                {
                    "key": "deployment",
                    "title": "Deployment",
                    "summary": "X" * 4000,
                    "claims": ["must not leak"] * 20,
                    "constraints": ["must not leak"] * 20,
                    "source_pointers": [f"file-{i}.yml" for i in range(20)],
                    "score": 0.8,
                }
            ]
        },
        "scanner_evidence": {"large": "Y" * 5000},
        "freshness": {
            "status": "refreshing",
            "snapshot_available": True,
            "background_refresh": True,
            "refresh_job": "queued",
            "scanner_evidence_withheld": True,
        },
        "task_runtime": {"huge": "runtime"},
        "tool_guidance": {"huge": "guidance"},
        "context_budget": {"huge": "budget"},
        "response_contract": {"huge": "contract"},
        "policy": "strict-private",
    }
    compact = _compact_legacy_context(legacy)
    assert compact["compatibility"]["preferred_startup"] == "project_status"
    assert compact["project_map"]["update"]["tool"] == "project_map_reconcile"
    assert compact["preferred_calls"] == {
        "state": "project_status",
        "navigation": "project_search",
        "map_update": "project_map_reconcile",
        "knowledge": "knowledge_search",
        "decisions": "decision_search",
    }
    assert len(compact["knowledge_hints"]) == LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT - 1
    assert len(compact["knowledge_hints"][0]["summary"]) == LEGACY_CONTEXT_SUMMARY_MAX_CHARS
    assert (
        len(compact["knowledge_hints"][0]["source_pointers"]) == LEGACY_CONTEXT_SOURCE_POINTER_LIMIT
    )
    for removed in (
        "task_brief",
        "scanner_evidence",
        "task_runtime",
        "tool_guidance",
        "context_budget",
        "response_contract",
    ):
        assert removed not in compact
    assert "must not leak" not in repr(compact)


def test_project_intelligence_runtime_classes_are_explicit_and_replay_safe():
    assert "project_status" in FAST_TOOLS
    assert tool_runtime_class("project_status") == "fast"
    assert {"project_search", "knowledge_search"} <= CONTEXT_TOOLS
    assert tool_runtime_class("project_search") == "context"
    assert tool_runtime_class("knowledge_search") == "context"
    assert {"project_status", "project_search", "knowledge_search"} <= REPLAY_SAFE_TOOLS
    assert "project_map_reconcile" in LONG_TOOLS
    assert tool_runtime_class("project_map_reconcile") == "long"
    assert "project_map_reconcile" not in REPLAY_SAFE_TOOLS


def test_default_managed_model_tiers_do_not_claim_two_identical_cost_levels():
    assert DEFAULT_CURSOR_MODELS["economy"] != DEFAULT_CURSOR_MODELS["balanced"]
    assert DEFAULT_CURSOR_MODELS["balanced"] == "inherit"
    assert DEFAULT_CURSOR_MODELS["strong"] == "inherit"
