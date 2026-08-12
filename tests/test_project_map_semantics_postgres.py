from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, RuntimeEvent
from ai_layer.db.navigation_models import ProjectNavigation
from ai_layer.memory.project_map_search import search_semantic_map
from ai_layer.memory.project_map_semantics import reconcile_project_map, semantic_map_status

POSTGRES_URL = os.getenv("AI_LAYER_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.postgres


def _engine():
    if not POSTGRES_URL:
        pytest.skip("AI_LAYER_TEST_POSTGRES_URL is not configured")
    return create_engine(POSTGRES_URL, pool_pre_ping=True)


def test_semantic_reconciliation_is_task_provenanced_searchable_and_becomes_stale(
    monkeypatch,
) -> None:
    import ai_layer.memory.project_map_semantics as semantics

    engine = _engine()
    monkeypatch.setattr(semantics, "_embed", lambda text: None)

    class BrokenEmbedder:
        def embed(self, texts):
            raise RuntimeError("semantic provider intentionally unavailable")

    monkeypatch.setattr(semantics, "get_embedder", lambda: BrokenEmbedder())
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name=f"project-map-{uuid4().hex}",
            root_path=f"/tmp/project-map-{uuid4().hex}",
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectNavigation(
                project_id=project.id,
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
                embedding=None,
            )
        )
        db.flush()
        result = reconcile_project_map(
            db,
            project,
            entries=[
                {
                    "path": "src/orders/retry.py",
                    "purpose": "Retries orders after failed iiko synchronization.",
                    "responsibilities": ["Restores failed order submission flow."],
                    "domain_terms": ["retry order", "повторная отправка заказа", "ошибка iiko"],
                    "important_symbols": ["RetryOrderProcessor.process"],
                }
            ],
            remove_paths=None,
            scope_paths=["src/orders/retry.py"],
            source_task_key=None,
            no_changes_reason=None,
        )
        assert result["updated"] == ["src/orders/retry.py"]
        assert semantic_map_status(db, project)["semantic_current"] == 1
        hits = search_semantic_map(db, project, "повторная отправка заказа", limit=8)
        assert hits and hits[0]["path"] == "src/orders/retry.py"
        assert hits[0]["semantic"]["freshness"] == "current"
        event = db.scalar(
            select(RuntimeEvent).where(
                RuntimeEvent.project_id == project.id,
                RuntimeEvent.event_type == "ProjectMapReconciled",
            )
        )
        assert event is not None
        assert event.payload["scope_paths"] == ["src/orders/retry.py"]
        structural = db.scalar(
            select(ProjectNavigation).where(
                ProjectNavigation.project_id == project.id,
                ProjectNavigation.path == "src/orders/retry.py",
            )
        )
        assert structural is not None
        structural.content_sha256 = "b" * 64
        db.flush()
        status = semantic_map_status(db, project)
        assert status["semantic_current"] == 0
        assert status["semantic_stale"] == 1
        stale_hits = search_semantic_map(db, project, "повторная отправка заказа", limit=8)
        assert stale_hits[0]["semantic"]["freshness"] == "stale"
        db.rollback()
