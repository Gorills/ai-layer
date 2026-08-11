from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_layer.application.knowledge import (
    _active_delegated_mutation_stage,
    _record_draft_review_inspection,
)
from ai_layer.db.base import Base
from ai_layer.db.models import Knowledge, Project
from ai_layer.memory import knowledge_store, scanner, service
from ai_layer.memory.knowledge_contract import KNOWLEDGE_KIND, normalize_card_input
from ai_layer.memory.knowledge_store import (
    knowledge_status,
    list_knowledge,
    publish_task_drafts,
    upsert_draft,
)
from ai_layer.tasks import service as tasks


class StableEmbedder:
    def embed(self, texts):
        return [[0.5] + [0.0] * 383 for _ in list(texts)]


def _db_project(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "backend").mkdir()
    (root / "backend" / "food_search.py").write_text(
        "def rank_foods(query, foods):\n    return foods\n", encoding="utf-8"
    )
    (root / "backend" / "test_food_search.py").write_text(
        "def test_word_order():\n    assert True\n", encoding="utf-8"
    )
    project = Project(
        name="demo", root_path=str(root), languages={}, dependencies={}, architecture_summary=""
    )
    db.add(project)
    db.commit()
    scanner.scan_project(db, project, root)
    db.commit()
    return db, project, root


def _draft_food_search(db, project, task_id="task-1"):
    return upsert_draft(
        db,
        project,
        source_task_id=task_id,
        key="nutrition.food-search",
        category="subsystem",
        title="Food Search",
        summary="Ranks foods for the nutrition domain.",
        claims=["Word-order-independent matching is part of the intended behavior."],
        constraints=["Keep one canonical ranking implementation."],
        evidence_paths=["backend/food_search.py", "backend/test_food_search.py"],
    )


def _draft_overview(db, project, task_id="task-1"):
    return upsert_draft(
        db,
        project,
        source_task_id=task_id,
        key="project.overview",
        category="overview",
        title="Project Overview",
        summary="Backend-oriented demo project with a food-search subsystem.",
        claims=["Food search implementation and tests live under backend/."],
        constraints=[],
        unknowns=["Deployment topology is not established by this minimal fixture."],
        evidence_paths=["backend/food_search.py", "backend/test_food_search.py"],
    )


def test_knowledge_contract_requires_repository_evidence_and_rejects_unsafe_paths():
    with pytest.raises(ValueError, match="at least one repository evidence path"):
        normalize_card_input(
            key="food-search",
            category="subsystem",
            title="Food Search",
            summary="Search behavior",
            claims=[],
            constraints=[],
            evidence_paths=[],
        )
    with pytest.raises(ValueError, match="unsafe evidence path"):
        normalize_card_input(
            key="food-search",
            category="subsystem",
            title="Food Search",
            summary="Search behavior",
            claims=[],
            constraints=[],
            evidence_paths=["../secret.txt"],
        )
    card = normalize_card_input(
        key="food-search",
        category="subsystem",
        title="Food Search",
        summary="Search behavior",
        claims=[],
        constraints=[],
        unknowns=["Typo tolerance behavior is not established."],
        evidence_paths=["backend/food_search.py"],
    )
    assert card["unknowns"] == ["Typo tolerance behavior is not established."]


def test_scan_keeps_deterministic_evidence_but_never_creates_raw_source_knowledge(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        assert db.scalar(select(Knowledge).where(Knowledge.project_id == project.id)) is None
        stats = scanner.scan_project(db, project, root)
        db.commit()
        assert stats.embeddings_regenerated == 0
        assert knowledge_status(db, project)["onboarding_recommended"] is True
    finally:
        db.close()


def test_verified_subsystem_does_not_claim_complete_baseline_without_reviewed_overview(
    tmp_path: Path, monkeypatch
):
    db, project, _ = _db_project(tmp_path)
    monkeypatch.setattr(knowledge_store, "get_embedder", lambda: StableEmbedder())
    try:
        _draft_food_search(db, project)
        publish_task_drafts(db, project, "task-1")
        state = knowledge_status(db, project)
        assert state["verified"] == 1
        assert state["verified_subsystems"] == 1
        assert state["overview_verified"] is False
        assert state["baseline_ready"] is False
        assert state["onboarding_recommended"] is True

        _draft_overview(db, project, task_id="task-2")
        publish_task_drafts(db, project, "task-2")
        state = knowledge_status(db, project)
        assert state["overview_verified"] is True
        assert state["baseline_ready"] is True
        assert state["onboarding_recommended"] is False
        assert state["verified_categories"] == ["overview", "subsystem"]
        assert state["verified_category_counts"] == {"overview": 1, "subsystem": 1}
    finally:
        db.close()


def test_scan_purges_legacy_scanner_memory_but_preserves_curated_project_knowledge(
    tmp_path: Path, monkeypatch
):
    db, project, root = _db_project(tmp_path)
    monkeypatch.setattr(knowledge_store, "get_embedder", lambda: StableEmbedder())
    try:
        for kind in ("file", "architecture", "project-intelligence"):
            db.add(
                Knowledge(
                    project_id=project.id,
                    kind=kind,
                    title=kind,
                    content="legacy",
                    source_path=None,
                    meta={},
                    embedding=[0.0] * 384,
                )
            )
        _draft_food_search(db, project)
        publish_task_drafts(db, project, "task-1")
        db.commit()

        stats = scanner.scan_project(db, project, root)
        db.commit()

        assert stats.legacy_source_knowledge_removed == 3
        kinds = set(
            db.scalars(select(Knowledge.kind).where(Knowledge.project_id == project.id)).all()
        )
        assert kinds == {KNOWLEDGE_KIND}
        assert knowledge_status(db, project)["verified"] == 1
    finally:
        db.close()


def test_draft_is_not_authoritative_until_reviewed_publication(tmp_path: Path, monkeypatch):
    db, project, _ = _db_project(tmp_path)
    monkeypatch.setattr(knowledge_store, "get_embedder", lambda: StableEmbedder())
    try:
        draft = _draft_food_search(db, project)
        db.commit()
        assert draft["status"] == "DRAFT"
        assert list_knowledge(db, project, status="VERIFIED") == []
        assert len(list_knowledge(db, project, status="DRAFT")) == 1

        published = publish_task_drafts(db, project, "task-1")
        db.commit()
        assert published == {"published": 1, "superseded": 0}
        assert len(list_knowledge(db, project, status="VERIFIED")) == 1
        assert list_knowledge(db, project, status="DRAFT") == []
    finally:
        db.close()


def test_review_gated_task_completion_publishes_mapper_drafts(tmp_path: Path, monkeypatch):
    db, project, _ = _db_project(tmp_path)
    monkeypatch.setattr(knowledge_store, "get_embedder", lambda: StableEmbedder())
    try:
        tasks.create_task(
            db,
            project,
            goal="Build verified Project Knowledge baseline",
            acceptance_criteria=[
                "Project knowledge cards cite current repository evidence",
                "Independent review passes",
            ],
            constraints=["Do not modify repository source"],
            workflow="standard",
            complexity="high",
            uncertainty="high",
            cost_policy="quality",
        )
        tasks.delegate_current_stage(db, project, worker_id="mapper-1")
        task, stage = _active_delegated_mutation_stage(db, project, "mapper-1")
        assert stage.kind == "implement"
        _draft_overview(db, project, str(task.id))
        _draft_food_search(db, project, str(task.id))
        db.commit()
        assert knowledge_status(db, project)["verified"] == 0

        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Mapped Project Knowledge with source evidence.",
            checks=["inspected current repository source"],
        )
        assert review["active_stage"]["kind"] == "review"
        review_contract = review["delegation_contract"]
        assert review_contract["project_knowledge_review"]["source_task_id"] == str(task.id)

        tasks.delegate_current_stage(db, project, worker_id="reviewer-1")
        with pytest.raises(RuntimeError, match="PROJECT_KNOWLEDGE_REVIEW_REQUIRED"):
            tasks.complete_current_stage(
                db,
                project,
                expected_kind="review",
                summary="Attempted pass before reading Project Knowledge drafts.",
                checks=["repository review"],
                verdict="pass",
            )
        drafts = list_knowledge(db, project, status="DRAFT", source_task_id=str(task.id))
        assert _record_draft_review_inspection(db, project, str(task.id), drafts) is True
        db.flush()
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="review",
            summary="Independently verified all knowledge claims.",
            checks=["knowledge_list DRAFT reviewed against cited source"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        state = knowledge_status(db, project)
        assert state["verified"] == 2
        assert state["baseline_ready"] is True
        cards = list_knowledge(db, project, status="VERIFIED")
        assert all(card["confidence"] == "independent_review_passed" for card in cards)
        overview = next(card for card in cards if card["category"] == "overview")
        assert overview["unknowns"] == [
            "Deployment topology is not established by this minimal fixture."
        ]
    finally:
        db.close()


def test_micro_and_analysis_only_workflows_cannot_write_project_knowledge(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        tasks.create_task(
            db,
            project,
            goal="Tiny local correction",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
            risk="low",
            complexity="low",
            uncertainty="low",
        )
        tasks.delegate_current_stage(db, project, worker_id="micro-worker")
        with pytest.raises(RuntimeError, match="review-gated"):
            _active_delegated_mutation_stage(db, project, "micro-worker")
        tasks.cancel_task(db, project, reason="test")

        tasks.create_task(
            db,
            project,
            goal="Analyze architecture only",
            acceptance_criteria=[],
            constraints=[],
            workflow="analysis_only",
        )
        tasks.delegate_current_stage(db, project, worker_id="discovery-worker")
        with pytest.raises(RuntimeError, match="review-gated"):
            _active_delegated_mutation_stage(db, project, "discovery-worker")
    finally:
        db.close()


def test_changed_supporting_source_marks_verified_card_stale(tmp_path: Path, monkeypatch):
    db, project, root = _db_project(tmp_path)
    monkeypatch.setattr(knowledge_store, "get_embedder", lambda: StableEmbedder())
    try:
        _draft_food_search(db, project)
        publish_task_drafts(db, project, "task-1")
        db.commit()
        assert knowledge_status(db, project)["verified"] == 1

        (root / "backend" / "food_search.py").write_text(
            "def rank_foods(query, foods):\n    return list(reversed(foods))\n", encoding="utf-8"
        )
        stats = scanner.scan_project(db, project, root)
        db.commit()
        assert stats.knowledge_cards_staled == 1
        state = knowledge_status(db, project)
        assert state["verified"] == 0
        assert state["stale"] == 1
        stale = list_knowledge(db, project, status="STALE")[0]
        assert "backend/food_search.py" in stale["stale_reason"]
    finally:
        db.close()


def test_food_search_memory_context_is_a_compact_project_brief_not_diagnostic_dump(monkeypatch):
    project = SimpleNamespace(
        id="p1",
        name="trener",
        root_path="/repo",
        languages={"python": 173, "typescript": 204},
        dependencies={},
        project_intelligence={
            "stack": {
                "languages": ["python", "typescript"],
                "frameworks": ["expo"],
                "manifests": ["pyproject.toml", "mobile/package.json"],
            },
            "runtime": {"entrypoints": ["backend/app/main.py", "mobile/src/app/_layout.tsx"]},
            "data": {"databases": ["postgresql"], "caches": []},
            "testing": {"test_files": 77, "frameworks": ["pytest"]},
            "documentation": {"domains": {"architecture": ["docs/ARCHITECTURE.md"]}},
            "docker": {"raw": "X" * 50_000},
        },
    )
    card = {
        "id": "k1",
        "key": "nutrition.food-search",
        "category": "subsystem",
        "title": "Food Search",
        "summary": "Ranks foods for nutrition search.",
        "claims": ["Word-order-independent matching already exists."],
        "constraints": ["Keep one canonical ranking implementation."],
        "source_pointers": [
            "backend/app/utils/food_search.py",
            "backend/tests/utils/test_food_search.py",
        ],
        "status": "VERIFIED",
        "score": 0.92,
    }
    monkeypatch.setattr(
        service,
        "_freshness_for_request",
        lambda *args, **kwargs: {"status": "fresh", "refreshed": False, "changed_paths": []},
    )
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda *args, **kwargs: {
            "verified": 1,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "baseline_ready": True,
            "onboarding_recommended": False,
        },
    )
    monkeypatch.setattr(service, "_search_memory", lambda *args, **kwargs: [card])
    monkeypatch.setattr(
        service,
        "relevant_task_history",
        lambda *args, **kwargs: [
            {
                "key": "T-0042",
                "goal": "Add word-order-independent food ranking",
                "outcome": "Implemented ranking behavior",
            }
        ],
    )
    monkeypatch.setattr(service, "relevant_decision_brief", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "dynamic_policy", lambda root, read_only=False: "policy")
    monkeypatch.setattr(service, "detect_project_profile", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        service, "build_tool_guidance", lambda *args, **kwargs: {"recommended_calls": []}
    )

    payload = service.memory_context(
        SimpleNamespace(),
        project,
        "Добавь tolerance к опечаткам в food search",
        task_runtime={"active": False, "next_action": {"action": "create_task"}},
    )
    brief = payload["task_brief"]
    assert brief["source_pointers"] == [
        "backend/app/utils/food_search.py",
        "backend/tests/utils/test_food_search.py",
    ]
    assert brief["verified_knowledge"][0]["title"] == "Food Search"
    assert brief["relevant_history"][0]["key"] == "T-0042"
    assert payload["context_budget"]["raw_source_memory_chars"] == 0
    rendered = repr(payload)
    assert "XXXXX" not in rendered  # giant Docker internals were not exposed
    assert "route_evidence" not in rendered
    assert "Source range:" not in rendered
