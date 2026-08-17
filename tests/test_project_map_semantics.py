from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.db.navigation_models import ProjectNavigation
from ai_layer.memory.navigation import _related_tests, _semantic_scores
from ai_layer.memory.project_map_search import merge_project_search
from ai_layer.memory.project_map_semantics import _normalize_entry, reconcile_project_map


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


def test_reconcile_refreshes_scanner_visible_path_missing_from_structural_map(tmp_path: Path):
    root = tmp_path / "project"
    source = root / "src" / "sync_related_parking_links.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def sync_related_parking_links():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="Map targeted refresh",
            root_path=str(root.resolve()),
            languages={},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        result = reconcile_project_map(
            db,
            project,
            entries=[
                {
                    "path": "src/sync_related_parking_links.py",
                    "purpose": "Synchronizes related parking links.",
                }
            ],
            remove_paths=None,
            scope_paths=None,
            source_task_key=None,
            no_changes_reason=None,
            source_work_key=None,
        )
        assert result["updated"] == ["src/sync_related_parking_links.py"]
        structural = db.scalar(
            select(ProjectNavigation).where(
                ProjectNavigation.project_id == project.id,
                ProjectNavigation.path == "src/sync_related_parking_links.py",
            )
        )
        assert structural is not None


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


def test_related_tests_are_path_adjacent_not_token_overlap() -> None:
    rows = [
        SimpleNamespace(path="src/orders/retry.py"),
        SimpleNamespace(path="tests/orders/test_retry.py"),
        SimpleNamespace(path="tests/test_retry.py"),
        SimpleNamespace(path="tests/test_unrelated.py"),
        SimpleNamespace(path="tests/iiko/test_client.py"),
    ]
    hits = [{"path": "src/orders/retry.py", "symbols": [{"name": "process"}]}]
    assert _related_tests(rows, hits) == [
        "tests/orders/test_retry.py",
        "tests/test_retry.py",
    ]


def test_related_tests_match_spec_and_test_stems() -> None:
    rows = [
        SimpleNamespace(path="src/foo.ts"),
        SimpleNamespace(path="tests/foo.spec.ts"),
        SimpleNamespace(path="tests/foo.test.ts"),
        SimpleNamespace(path="__tests__/foo.test.ts"),
        SimpleNamespace(path="tests/bar.spec.ts"),
        SimpleNamespace(path="tests/unrelated.spec.ts"),
        SimpleNamespace(path="tests/orders/other.spec.ts"),
    ]
    hits = [{"path": "src/foo.ts"}]
    assert _related_tests(rows, hits) == [
        "__tests__/foo.test.ts",
        "tests/foo.spec.ts",
        "tests/foo.test.ts",
    ]


def test_project_search_why_is_capped_to_two_short_reasons() -> None:
    structural = {
        "matches": [
            {
                "path": "src/orders/retry.py",
                "score": 0.31,
                "why": [
                    "matching symbol names",
                    "path/purpose/import match",
                    "semantic navigation metadata match",
                ],
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
            "why": [
                "semantic domain terms match",
                "semantic important symbols match",
                "semantic responsibility/purpose match",
                "multilingual semantic enrichment match",
                "semantic enrichment is stale; verify current source",
            ],
            "semantic": {
                "purpose": "Retries failed iiko orders.",
                "related_tests": ["tests/orders/test_retry.py"],
                "freshness": "stale",
            },
        }
    ]
    result = merge_project_search(structural, semantic, limit=8)
    why = result["matches"][0]["why"]
    assert 1 <= len(why) <= 2
    assert "semantic enrichment is stale; verify current source" in why
    assert all(len(item) < 80 for item in why)
    assert result["related_tests"] == ["tests/orders/test_retry.py"]
