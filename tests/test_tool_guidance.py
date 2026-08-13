from ai_layer.memory.service import _compact_context_hits, build_tool_guidance


def test_generic_prompt_does_not_trigger_hidden_session_or_memory_routing():
    guidance = build_tool_guidance("продолжай", "/repo", [])
    assert guidance["recommended_calls"] == []
    assert guidance["project_context"] == {"canonical_root": "/repo"}
    assert "task_execution" not in guidance
    assert "avoid" not in guidance


def test_memory_context_does_not_special_case_continuation_word(monkeypatch):
    from types import SimpleNamespace

    from ai_layer.memory import service
    from ai_layer.memory.presentation import context_mode

    project = SimpleNamespace(
        id="p1",
        name="linux-tools",
        root_path="/repo",
        languages={"markdown": 22},
        dependencies={},
        project_intelligence={
            "stack": {"languages": ["markdown"], "frameworks": [], "manifests": []},
            "runtime": {"entrypoints": ["wrong-old-entrypoint.md"]},
            "data": {"databases": [], "caches": []},
            "testing": {"test_files": 0, "frameworks": []},
            "documentation": {"domains": {"startup": ["README.md"]}},
        },
    )
    monkeypatch.setattr(
        service,
        "_freshness_for_request",
        lambda *a, **k: {
            "status": "refreshing",
            "refreshed": False,
            "snapshot_available": True,
            "background_refresh": True,
            "refresh_job": "queued",
            "changed_paths": [],
            "read_contract": "last stable snapshot is stale",
        },
    )
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda *a, **k: {
            "verified": 0,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "verified_categories": [],
            "verified_category_counts": {},
            "verified_subsystems": 0,
            "overview_verified": False,
            "baseline_ready": False,
            "onboarding_recommended": True,
        },
    )
    monkeypatch.setattr(service, "relevant_task_history", lambda *a, **k: [])
    monkeypatch.setattr(service, "relevant_decision_brief", lambda *a, **k: [])
    monkeypatch.setattr(service, "dynamic_policy", lambda root, read_only=False: "policy")

    runtime = {
        "active": False,
        "state": "no_active_task",
        "project_root": "/repo",
        "latest": {
            "key": "T-0001",
            "goal": "Create scaffold",
            "status": "completed",
            "acceptance_criteria": ["DO NOT LEAK"],
            "discovery_result": {"summary": "DO NOT LEAK"},
            "final_changes": {"added": ["a"] * 50, "total": 50},
        },
        "next_action": {"action": "create_task", "tool": "task_create", "message": "Create task"},
    }
    payload = service.memory_context(SimpleNamespace(), project, "продолжай", task_runtime=runtime)

    assert context_mode("продолжай") == "task"
    assert context_mode("Продолжай!") == "task"
    assert context_mode("Continue previous task") == "task"
    assert "presentation_mode" not in payload["task_brief"]
    assert "latest" not in payload["task_runtime"]
    assert "DO NOT LEAK" not in repr(payload)
    assert payload["tool_guidance"]["recommended_calls"] == []
    assert payload["scanner_evidence"] == {
        "available": False,
        "reason": "scanner_snapshot_not_current",
        "freshness_status": "refreshing",
        "snapshot_available": True,
    }
    assert "wrong-old-entrypoint.md" not in repr(payload)
    assert payload["project"]["profile"] == {
        "available": False,
        "reason": "scanner_snapshot_not_current",
    }
    assert payload["freshness"]["scanner_evidence_withheld"] is True
    assert payload["freshness"]["changed_path_count"] is None
    assert payload["context_budget"]["mode"] == "task_project_brief+dynamic_policy+compact_runtime"


def test_ordinary_task_withholds_stale_scanner_evidence_and_profile(monkeypatch):
    from types import SimpleNamespace

    from ai_layer.memory import service

    project = SimpleNamespace(
        id="p1",
        name="demo",
        root_path="/repo",
        languages={"markdown": 20},
        dependencies={},
        project_intelligence={
            "stack": {"languages": ["markdown"], "frameworks": [], "manifests": []},
            "runtime": {"entrypoints": ["obsolete.md"]},
            "data": {},
            "testing": {},
            "documentation": {},
        },
    )
    monkeypatch.setattr(
        service,
        "_freshness_for_request",
        lambda *a, **k: {
            "status": "refreshing",
            "refreshed": False,
            "snapshot_available": True,
            "changed_paths": ["pyproject.toml"],
        },
    )
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda *a, **k: {
            "verified": 0,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "baseline_ready": False,
            "onboarding_recommended": True,
        },
    )
    monkeypatch.setattr(service, "relevant_task_history", lambda *a, **k: [])
    monkeypatch.setattr(service, "relevant_decision_brief", lambda *a, **k: [])
    monkeypatch.setattr(service, "dynamic_policy", lambda root, read_only=False: "policy")
    monkeypatch.setattr(service, "build_tool_guidance", lambda *a, **k: {"recommended_calls": []})

    payload = service.memory_context(
        SimpleNamespace(),
        project,
        "Добавь health endpoint",
        task_runtime={"active": False, "next_action": {"action": "create_task"}},
    )
    assert payload["scanner_evidence"] == {
        "available": False,
        "reason": "scanner_snapshot_not_current",
        "freshness_status": "refreshing",
        "snapshot_available": True,
    }
    assert payload["project"]["profile"] == {
        "available": False,
        "reason": "scanner_snapshot_not_current",
    }
    assert "obsolete.md" not in repr(payload)
    assert payload["freshness"]["scanner_evidence_withheld"] is True
    assert payload["freshness"]["changed_path_count"] is None


def test_low_confidence_context_recommends_targeted_search():
    guidance = build_tool_guidance("fix obscure parser bug", "/repo", [{"score": 0.2}])
    assert guidance["recommended_calls"][0]["tool"] == "knowledge_search"


def test_memory_context_payload_is_bounded_for_token_economy():
    hits = [
        {
            "id": "k1",
            "key": "food-search",
            "category": "subsystem",
            "title": "Food Search",
            "summary": "A" * 5000,
            "claims": ["B" * 500] * 20,
            "constraints": [],
            "source_pointers": ["backend/app/utils/food_search.py"],
            "score": 0.9,
        }
    ]
    compact = _compact_context_hits(hits, max_chars=1800)
    assert (
        compact == []
    )  # oversized curated cards are skipped rather than transport-truncated into misleading prose


def test_existing_mechanism_extension_does_not_speculatively_recommend_decision_search():
    guidance = build_tool_guidance(
        "Расширь payments refresh endpoint поддержкой sync=1. Сохрани совместимость с уже существующей архитектурой.",
        "/repo",
        [{"score": 0.8}],
    )
    assert "decision_search" not in [item["tool"] for item in guidance["recommended_calls"]]


def test_real_consequential_choice_recommends_decision_search():
    guidance = build_tool_guidance(
        "Выбери вариант интеграции нового payment provider и спроектируй API contract без параллельного механизма.",
        "/repo",
        [{"score": 0.8}],
    )
    calls = guidance["recommended_calls"]
    assert [item["tool"] for item in calls] == ["decision_search"]
    assert calls[0]["required"] is True
    assert "consequential design choice" in calls[0]["when"]


def test_normal_guidance_does_not_duplicate_static_workflow_manual():
    guidance = build_tool_guidance("fix payment idempotency bug", "/repo", [{"score": 0.8}])
    assert "task_execution" not in guidance
    assert "avoid" not in guidance
    assert guidance["project_context"] == {"canonical_root": "/repo"}


def test_live_acceptance_provider_choice_sets_required_decision_gate_even_with_low_context():
    guidance = build_tool_guidance(
        "Добавь поддержку нового payment provider adapter для тестового провайдера. Выбери вариант интеграции, который лучше соответствует существующей архитектуре, не создаёт второй параллельный payment flow и сохраняет текущий публичный API. Реализуй минимальный вариант и добавь тесты.",
        "/repo",
        [{"score": 0.2}],
    )
    calls = guidance["recommended_calls"]
    assert [item["tool"] for item in calls] == ["decision_search", "knowledge_search"]
    assert calls[0]["required"] is True
    assert calls[0]["tool"] == "decision_search"


def test_ordinary_idempotency_bugfix_has_no_decision_gate():
    guidance = build_tool_guidance(
        "При повторном POST /api/payments/ с тем же idempotency_key исправь статус ответа и добавь тесты.",
        "/repo",
        [{"score": 0.8}],
    )
    assert "decision_search" not in [item["tool"] for item in guidance["recommended_calls"]]


def test_memory_search_does_not_pad_results_with_near_zero_similarity():
    from types import SimpleNamespace

    from ai_layer.memory import knowledge_store, service

    item = SimpleNamespace(
        id="k1",
        kind="project-knowledge",
        title="irrelevant",
        content="nothing related",
        source_path=None,
        meta={
            "status": "VERIFIED",
            "knowledge_key": "irrelevant",
            "category": "other",
            "summary": "nothing related",
        },
    )

    class Result:
        def all(self):
            return [(item, 0.99)]

    class DB:
        def execute(self, stmt):
            return Result()

    project = SimpleNamespace(id="p1")
    original = knowledge_store.get_embedder
    knowledge_store.get_embedder = lambda: SimpleNamespace(embed=lambda texts: [[0.0] * 384])
    try:
        assert (
            service._search_memory(DB(), project, "specific missing parser behavior", limit=8) == []
        )
    finally:
        knowledge_store.get_embedder = original


def test_decision_search_does_not_refresh_repository_memory(monkeypatch):
    from types import SimpleNamespace

    from ai_layer.memory import embeddings, service

    class Result:
        def all(self):
            return []

    class DB:
        def execute(self, stmt):
            return Result()

    monkeypatch.setattr(
        service,
        "ensure_memory_fresh",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("decision history must not refresh repo")
        ),
    )
    monkeypatch.setattr(
        embeddings, "get_embedder", lambda: SimpleNamespace(embed=lambda texts: [[0.0] * 384])
    )
    monkeypatch.setattr(service, "snapshot_decisions", lambda project, limit=30: [])
    monkeypatch.setattr(service, "_search_memory", lambda db, project, query, limit=8: [])

    assert service.decision_search(DB(), SimpleNamespace(id="p1"), "choose provider", limit=8) == []


def test_memory_context_never_injects_or_plans_domain_skills(monkeypatch):
    import json
    from types import SimpleNamespace

    from ai_layer.memory import service

    class DB:
        pass

    project = SimpleNamespace(
        id="p1",
        name="demo",
        root_path="/repo",
        languages={"python": 10},
        dependencies={},
        architecture_summary="demo architecture",
        project_intelligence={},
    )
    hits = [
        {
            "id": str(i),
            "key": f"card-{i}",
            "category": "subsystem",
            "title": f"Card {i}",
            "summary": "M" * 500,
            "claims": ["verified behavior"],
            "constraints": [],
            "source_pointers": [f"f{i}.py"],
            "status": "VERIFIED",
            "score": 0.9,
        }
        for i in range(4)
    ]
    monkeypatch.setattr(
        service,
        "_freshness_for_request",
        lambda db, project: {"status": "fresh", "refreshed": False},
    )
    monkeypatch.setattr(service, "_search_memory", lambda db, project, task, limit=4: hits[:limit])
    monkeypatch.setattr(service, "dynamic_policy", lambda root, read_only=False: "P" * 20000)
    monkeypatch.setattr(service, "detect_project_profile", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda *args, **kwargs: {
            "verified": 4,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "baseline_ready": True,
            "onboarding_recommended": False,
        },
    )
    monkeypatch.setattr(service, "relevant_task_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "relevant_decision_brief", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        service, "build_tool_guidance", lambda *args, **kwargs: {"recommended_calls": []}
    )

    payload = service.memory_context(
        DB(),
        project,
        "fix Django parser",
        limit=4,
        task_runtime={
            "active": False,
            "next_action": {"action": "create_task", "tool": "task_create"},
        },
    )
    assert "skill_plan" not in payload
    assert "skills" not in payload
    assert payload["skill_access"]["routing_owner"] == "host-native"
    assert payload["skill_access"]["automatic_domain_skill_injection"] is False
    assert payload["context_budget"]["automatic_skill_chars"] == 0
    assert payload["context_budget"]["raw_source_memory_chars"] == 0
    assert "memory" not in payload
    assert "project_intelligence" not in payload
    assert all(item.get("kind") != "file" for item in payload["task_brief"]["verified_knowledge"])
    assert len(payload["policy"]) == 20000
    assert payload["context_budget"]["policy_over_soft_target"] is True


def test_coverage_audit_uses_complete_inventory_without_prior_reviewer_reasoning(monkeypatch):
    from types import SimpleNamespace

    from ai_layer.memory import service

    project = SimpleNamespace(
        id="p1",
        name="trener",
        root_path="/repo",
        languages={"python": 10, "typescript": 20},
        dependencies={},
        project_intelligence={
            "stack": {
                "languages": ["python", "typescript"],
                "frameworks": ["scanner-might-be-wrong"],
                "manifests": ["backend/requirements.txt", "mobile/package.json"],
            },
            "runtime": {"entrypoints": ["wrong-candidate.ts"]},
            "data": {"databases": ["postgresql"], "caches": []},
            "testing": {"test_files": 77, "frameworks": ["pytest"]},
            "documentation": {"domains": {"architecture": ["docs/ARCHITECTURE.md"]}},
        },
    )
    cards = [
        {
            "id": f"k{i}",
            "key": key,
            "category": category,
            "title": title,
            "summary": summary,
            "claims": ["claim"],
            "constraints": [],
            "unknowns": [],
            "source_pointers": [path],
            "status": "VERIFIED",
        }
        for i, (key, category, title, summary, path) in enumerate(
            [
                ("project.overview", "overview", "Project Overview", "Project map", "README.md"),
                (
                    "subsystem.backend",
                    "subsystem",
                    "Backend",
                    "Backend subsystem",
                    "backend/app/main.py",
                ),
                (
                    "subsystem.mobile",
                    "subsystem",
                    "Mobile",
                    "Mobile subsystem",
                    "mobile/package.json",
                ),
            ]
        )
    ]
    monkeypatch.setattr(
        service,
        "_freshness_for_request",
        lambda *a, **k: {"status": "fresh", "refreshed": False, "changed_paths": []},
    )
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda *a, **k: {
            "verified": 3,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "verified_categories": ["overview", "subsystem"],
            "verified_category_counts": {"overview": 1, "subsystem": 2},
            "verified_subsystems": 2,
            "overview_verified": True,
            "baseline_ready": True,
            "onboarding_recommended": False,
        },
    )
    monkeypatch.setattr(
        service,
        "list_knowledge",
        lambda *a, status="VERIFIED", **k: cards if status == "VERIFIED" else [],
    )
    monkeypatch.setattr(
        service,
        "knowledge_audit_history",
        lambda *a, **k: [
            {
                "key": "T-0017",
                "goal": "Independent Project Knowledge audit",
                "completed_at": "2026-08-11T00:00:00+00:00",
                "provenance": "ai_layer_task_history_metadata_only",
            }
        ],
    )
    monkeypatch.setattr(
        service, "dynamic_policy", lambda root, read_only=False: "critical read-only policy"
    )
    monkeypatch.setattr(service, "detect_project_profile", lambda *a, **k: {})

    runtime = {
        "active": False,
        "state": "no_active_task",
        "project_root": "/repo",
        "latest": {
            "key": "T-0017",
            "discovery_result": {"summary": "DO NOT LEAK", "proposed_plan": ["anchoring"]},
        },
        "next_action": {"action": "create_task", "tool": "task_create", "message": "Create task"},
    }
    payload = service.memory_context(
        SimpleNamespace(),
        project,
        "Coverage audit of VERIFIED Project Knowledge for trener project",
        task_runtime=runtime,
    )

    brief = payload["task_brief"]
    assert brief["presentation_mode"] == "knowledge_coverage_audit"
    assert brief["inventory_complete"] is True
    assert [item["key"] for item in brief["knowledge_inventory"]] == [
        "project.overview",
        "subsystem.backend",
        "subsystem.mobile",
    ]
    assert "verified_knowledge" not in brief
    assert "relevant_decisions" not in brief
    assert brief["relevant_history"][0].get("outcome") is None
    assert "memory" not in payload
    assert "project_intelligence" not in payload
    assert "latest" not in payload["task_runtime"]
    assert "DO NOT LEAK" not in repr(payload)
    assert "framework_candidates" not in payload["scanner_evidence"]
    assert "entrypoint_candidates" not in payload["scanner_evidence"]
    assert payload["policy"] == "critical read-only policy"
    assert (
        payload["context_budget"]["mode"]
        == "knowledge_audit_inventory+compact_read_only_control_plane"
    )


def test_russian_knowledge_coverage_audit_selects_inventory_mode():
    from ai_layer.memory.presentation import context_mode

    assert context_mode("Проведи аудит покрытия базы знаний проекта") == "knowledge_coverage_audit"
    assert context_mode("продолжай") == "task"
    assert context_mode("Continue previous task") == "task"
    assert context_mode("Continue using the existing API and add a health endpoint") == "task"
    assert context_mode("Исправь поиск еды") == "task"


def test_near_empty_project_context_omits_static_policy_and_workflow_dump(monkeypatch):
    import json
    from types import SimpleNamespace

    from ai_layer.memory import service

    project = SimpleNamespace(
        id="p-empty",
        name="linux-tools",
        root_path="/repo",
        languages={"markdown": 1},
        dependencies={},
        project_intelligence={
            "stack": {"languages": ["markdown"], "frameworks": [], "manifests": []},
            "runtime": {"entrypoints": []},
            "data": {"databases": [], "caches": []},
            "testing": {"test_files": 0, "frameworks": []},
            "documentation": {"domains": {"startup": ["README.md"]}},
        },
    )
    monkeypatch.setattr(
        service,
        "_freshness_for_request",
        lambda *a, **k: {
            "status": "fresh",
            "refreshed": True,
            "snapshot_available": True,
            "changed_paths": [],
        },
    )
    monkeypatch.setattr(
        service,
        "knowledge_status",
        lambda *a, **k: {
            "verified": 0,
            "stale": 0,
            "draft": 0,
            "superseded": 0,
            "verified_categories": [],
            "verified_category_counts": {},
            "verified_subsystems": 0,
            "overview_verified": False,
            "baseline_ready": False,
            "onboarding_recommended": True,
        },
    )
    monkeypatch.setattr(service, "relevant_task_history", lambda *a, **k: [])
    monkeypatch.setattr(service, "relevant_decision_brief", lambda *a, **k: [])
    monkeypatch.setattr(service, "dynamic_policy", lambda root, read_only=False: "")

    payload = service.memory_context(
        SimpleNamespace(),
        project,
        "Add first endpoint",
        task_runtime={
            "active": False,
            "state": "no_active_task",
            "project_root": "/repo",
            "latest": {"goal": "DO NOT LEAK", "discovery_result": {"summary": "DO NOT LEAK"}},
            "next_action": {"action": "create_task", "tool": "task_create", "required": ["goal"]},
        },
    )

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["policy"] == ""
    assert "latest" not in payload["task_runtime"]
    assert "DO NOT LEAK" not in encoded
    assert "task_execution" not in payload["tool_guidance"]
    assert "avoid" not in payload["tool_guidance"]
    assert payload["context_budget"]["policy_chars"] == 0
