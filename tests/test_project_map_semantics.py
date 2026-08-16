from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_layer.db.navigation_models import ProjectNavigation
from ai_layer.memory.navigation import _semantic_scores
from ai_layer.memory.project_map_search import merge_project_search
from ai_layer.memory.project_map_semantics import _normalize_entry


def _navigation() -> ProjectNavigation:
    return ProjectNavigation(
        path="src/orders/retry.py",
        language="python",
        purpose="python source/configuration file",
        imports=["orders.repository"],
        risk_flags=[],
        symbols=[
            {
                "name": "process",
                "qualified_name": "RetryOrderProcessor.process",
                "kind": "method",
                "line_start": 42,
                "signature": "process(order)",
                "detail": "",
            }
        ],
        navigation_text="Path: src/orders/retry.py",
        content_sha256="a" * 64,
        scanner_schema=5,
    )


def test_semantic_entry_uses_english_canonical_text_and_allows_russian_domain_terms():
    row = _navigation()
    item = _normalize_entry(
        {
            "path": row.path,
            "purpose": "Retries orders after failed iiko synchronization.",
            "responsibilities": ["Restores failed order submission flow."],
            "domain_terms": ["retry order", "повторная отправка заказа", "ошибка iiko"],
            "important_symbols": ["RetryOrderProcessor.process"],
        },
        navigation_rows={row.path: row},
    )
    assert item["purpose"].startswith("Retries orders")
    assert "повторная отправка заказа" in item["domain_terms"]
    assert item["important_symbols"] == ["RetryOrderProcessor.process"]
    assert item["content_sha256"] == "a" * 64


def test_semantic_entry_rejects_russian_canonical_prose_but_not_aliases():
    row = _navigation()
    with pytest.raises(ValueError, match="canonical semantic text"):
        _normalize_entry(
            {
                "path": row.path,
                "purpose": "Повторно отправляет заказ после ошибки iiko.",
                "domain_terms": ["повторная отправка заказа"],
            },
            navigation_rows={row.path: row},
        )


def test_semantic_entry_rejects_symbols_not_proven_by_current_structural_map():
    row = _navigation()
    with pytest.raises(ValueError, match="unknown"):
        _normalize_entry(
            {
                "path": row.path,
                "purpose": "Retries failed orders.",
                "important_symbols": ["ImaginaryRetryService.run"],
            },
            navigation_rows={row.path: row},
        )


def test_structural_semantic_query_failure_degrades_to_lexical(monkeypatch):
    class BrokenEmbedder:
        def embed(self, texts):
            raise RuntimeError("offline")

    monkeypatch.setattr("ai_layer.memory.navigation.get_embedder", lambda: BrokenEmbedder())
    scores, available = _semantic_scores(
        object(),
        SimpleNamespace(id="project-1"),
        [_navigation()],
        "RetryOrderProcessor",
        limit=8,
    )
    assert scores == {}
    assert available is False


def test_project_search_merge_can_promote_semantic_only_breadcrumbs():
    structural = {
        "matches": [
            {
                "path": "src/iiko/client.py",
                "score": 0.31,
                "why": ["path/purpose/import match"],
                "symbols": [],
            }
        ],
        "related_tests": [],
        "search_mode": "hybrid_metadata",
    }
    semantic = [
        {
            "path": "src/orders/retry.py",
            "language": "python",
            "score": 0.82,
            "why": ["semantic domain terms match"],
            "semantic": {
                "purpose": "Retries failed iiko orders.",
                "domain_terms": ["повторная отправка заказа"],
                "related_tests": ["tests/orders/test_retry.py"],
                "freshness": "current",
            },
        }
    ]
    result = merge_project_search(structural, semantic, limit=8)
    assert result["matches"][0]["path"] == "src/orders/retry.py"
    assert result["matches"][0]["semantic"]["freshness"] == "current"
    assert result["related_tests"] == ["tests/orders/test_retry.py"]
    assert result["search_mode"] == "hybrid_structural_semantic"
    assert "language_contract" not in result
    assert "query_contract" not in result
    assert "source_contract" not in result
