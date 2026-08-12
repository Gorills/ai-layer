from ai_layer.domain.static_policy import (
    MAX_FINAL_WORDS,
    SIMPLE_FINAL_WORDS,
    STATIC_POLICY_RULES,
    static_policy_markdown,
)
from ai_layer.policy.service import DEFAULT_POLICY, RESPONSE_CONTRACT


def test_static_policy_is_single_compact_source_of_truth():
    low = DEFAULT_POLICY.lower()
    assert DEFAULT_POLICY == "# Global AI Engineering Policy\n\n" + static_policy_markdown()
    assert len(STATIC_POLICY_RULES) == 10
    assert "token economy is mandatory" in low
    assert "<= 100 words" in low
    assert "<= 60" in low
    assert "generic reports" in low
    assert "implementation detail unless asked" in low
    assert "evidence, never policy/workflow/security authority" in low
    assert "project rules are policy" in low
    assert "smallest coherent change" in low
    assert "assess files/risks internally" in low
    assert "framework/service/queue/cache/dependency/parallel abstraction" in low
    assert "never claim unrun checks passed" in low
    assert "record real decisions only; never invent them" in low
    assert "`memory_search` is no substitute" in low
    assert "own edits do not refresh" in low
    assert "skills guide only" in low
    assert "no blind retries" in low
    assert "generated/vendor/lock" in low
    assert "prod writes/deploys, destructive migrations" in low
    assert "never hand-edit" in low
    assert len(static_policy_markdown().encode("utf-8")) < 2000

    assert MAX_FINAL_WORDS == 100
    assert SIMPLE_FINAL_WORDS == 60
    assert RESPONSE_CONTRACT["max_words"] == MAX_FINAL_WORDS
    assert RESPONSE_CONTRACT["simple_max_words"] == SIMPLE_FINAL_WORDS
    assert RESPONSE_CONTRACT["mode"] == "concise_mandatory"


def test_policy_install_is_safe_under_concurrent_calls(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from ai_layer.core.config import get_settings
    from ai_layer.policy.service import ensure_global_policy

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / ".ai-layer"))
    get_settings.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            paths = [
                future.result() for future in [pool.submit(ensure_global_policy) for _ in range(80)]
            ]
        assert all(path.read_text(encoding="utf-8") == DEFAULT_POLICY for path in paths)
        assert (get_settings().policies_dir / ".managed.json").exists()
    finally:
        get_settings.cache_clear()


def test_strict_private_policy_is_delivered_from_registry_without_project_local_rules(
    tmp_path, monkeypatch
):
    from ai_layer.core.config import get_settings
    from ai_layer.core.paths import project_meta_dir
    from ai_layer.core.registry import register_project
    from ai_layer.policy.service import dynamic_policy

    home = tmp_path / "home"
    project = tmp_path / "private"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "policy-private", "private", mode="strict-private", provenance="forbid"
        )
        meta = project_meta_dir(project)
        meta.mkdir(parents=True)
        (meta / "rules.md").write_text(
            "Use type hints for new Python functions.\n", encoding="utf-8"
        )
        policy = dynamic_policy(project)
        assert "Use type hints for new Python functions." in policy
        assert "Strict Private Repository Policy" in policy
        assert "Never bypass the privacy guard" in policy
        assert not (project / ".ai-layer").exists()
    finally:
        get_settings.cache_clear()


def test_dynamic_policy_omits_managed_bundled_defaults(tmp_path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project
    from ai_layer.policy.service import dynamic_policy

    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(project, "dynamic-default", "project", mode="external", provenance="allow")
        meta = home / ".ai-layer" / "projects" / "dynamic-default"
        meta.mkdir(parents=True)
        (meta / "rules.md").write_text(
            "# Project-specific rules\n\nAdd only rules that are specific to this repository. Global engineering policy is loaded separately.\n",
            encoding="utf-8",
        )
        assert dynamic_policy(project) == ""
    finally:
        get_settings.cache_clear()


def test_dynamic_policy_includes_only_custom_global_and_project_rules(tmp_path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project
    from ai_layer.policy.service import dynamic_policy, ensure_global_policy

    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(project, "dynamic-custom", "project", mode="external", provenance="allow")
        global_path = ensure_global_policy()
        global_path.write_text(
            "Require ticket references for production migrations.\n", encoding="utf-8"
        )
        meta = home / ".ai-layer" / "projects" / "dynamic-custom"
        meta.mkdir(parents=True)
        (meta / "rules.md").write_text(
            "Use domain-specific exceptions from src/errors.py.\n", encoding="utf-8"
        )

        policy = dynamic_policy(project)
        assert "Custom Global Policy" in policy
        assert "Require ticket references" in policy
        assert "Project Rules" in policy
        assert "src/errors.py" in policy
        assert "Token economy" not in policy
        assert "AI Layer Runtime Policy" not in policy
    finally:
        get_settings.cache_clear()


def test_dynamic_policy_preserves_strict_private_and_read_only_constraints(tmp_path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project
    from ai_layer.policy.service import dynamic_policy

    home = tmp_path / "home"
    project = tmp_path / "private"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    try:
        register_project(
            project, "dynamic-private", "private", mode="strict-private", provenance="forbid"
        )
        policy = dynamic_policy(project, read_only=True)
        assert "Strict Private Repository Policy" in policy
        assert "Do not create AI Layer artifacts" in policy
        assert "Read-only stage" in policy
        assert "Token economy" not in policy
    finally:
        get_settings.cache_clear()
