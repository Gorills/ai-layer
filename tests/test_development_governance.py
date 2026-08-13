from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_native_agent_bootstrap_is_single_source() -> None:
    agents = _text("AGENTS.md")
    gemini = _text("GEMINI.md")
    assert "make dev-setup" in agents
    assert "make fast-gate" in agents
    assert "make preflight" in agents
    assert "--no-verify" in agents
    assert "executable local worktree" in agents
    assert "@./AGENTS.md" in gemini


def test_native_agent_bootstrap_points_to_canonical_decisions_directory() -> None:
    agents = _text("AGENTS.md")
    maintainer = _text("MAINTAINER_INSTRUCTIONS.md")
    assert "relevant ADRs in `DECISIONS/`" in agents
    assert "docs/DECISIONS/" not in agents
    assert "relevant files in `DECISIONS/`" in maintainer
    assert "docs/DECISIONS/" not in maintainer
    assert (ROOT / "DECISIONS" / "0020-durable-work-spine-and-truthful-observability.md").is_file()


def test_repository_bootstrap_rejects_ambient_ai_layer_as_source_evidence() -> None:
    agents = _text("AGENTS.md")
    assert "intentionally **not registered as an AI Layer target project**" in agents
    assert "Do not call installed AI Layer project tools" in agents
    assert "Do not run a globally installed `ai-layer` or `ai-layer-mcp`" in agents
    assert "Global agent skills may be used as professional guidance only" in agents
    assert "never reuse ambient machine AI Layer state as test evidence" in agents
    assert "Current checkout source and repository verification are authoritative" in agents
    assert (ROOT / "DECISIONS" / "0021-self-hosting-development-isolation.md").is_file()


def test_repository_bootstrap_requires_canonical_current_product_goal() -> None:
    agents = _text("AGENTS.md")
    maintainer = _text("MAINTAINER_INSTRUCTIONS.md")
    goal = _text("PRODUCT_GOAL.md")
    roadmap = _text("ROADMAP.md")
    assert "`PRODUCT_GOAL.md`, `ROADMAP.md`" in agents
    assert "Read `PRODUCT_GOAL.md` for the current target outcome" in maintainer
    assert (
        "describes the product we are trying to reach, not the behavior already implemented" in goal
    )
    assert (
        "WorkItem" in goal and "Managed Task / Epic" in goal and "Activity / RuntimeEvent" in goal
    )
    assert "Target repository cleanliness" in goal
    assert "Raw Task count, tool-call count and event volume are not success metrics" in goal
    assert "The canonical target outcome is [PRODUCT_GOAL.md](PRODUCT_GOAL.md)" in roadmap
    assert (ROOT / "DECISIONS" / "0022-current-product-improvement-goal.md").is_file()


def test_completed_work_requires_next_action_and_next_chat_prompt() -> None:
    agents = _text("AGENTS.md")
    maintainer = _text("MAINTAINER_INSTRUCTIONS.md")
    assert "## Mandatory completion handoff" in agents
    assert "**What next**" in agents
    assert "**Prompt for the next chat**" in agents
    assert "inspect current source and Git state" in agents
    assert "Do not omit this handoff" in agents
    assert "End every completed-work response" in maintainer
    assert "If nothing remains required, say so explicitly" in maintainer
    assert (ROOT / "DECISIONS" / "0023-mandatory-agent-completion-handoff.md").is_file()


def test_git_hooks_fail_closed_into_repository_targets() -> None:
    pre_commit = _text(".githooks/pre-commit")
    pre_push = _text(".githooks/pre-push")
    assert "set -euo pipefail" in pre_commit
    assert "exec make fast-gate" in pre_commit
    assert "set -euo pipefail" in pre_push
    assert "exec make preflight" in pre_push


def test_makefile_owns_local_and_ci_gate_composition() -> None:
    makefile = _text("Makefile")
    compose = _text("docker-compose.yml")
    assert "quality:\n\tpython scripts/quality_gate.py --deterministic-wheel" in makefile
    assert "postgres-gate:\n\tpython scripts/postgres_gate.py" in makefile
    assert "preflight-ci:\n\t$(MAKE) quality\n\t$(MAKE) postgres-gate" in makefile
    assert ".venv/bin/python scripts/local_preflight.py" in makefile
    assert "REPO_VENV_BIN := $(CURDIR)/.venv/bin" in makefile
    assert "fast-gate: check-dev-env" in makefile
    assert "preflight: check-dev-env" in makefile
    assert '"CPython 3.12"' in makefile
    assert "container_name:" not in compose
    assert "${AI_LAYER_POSTGRES_PORT:-54329}" in compose
    assert "git config core.hooksPath .githooks" in makefile


def test_local_preflight_owns_ephemeral_compose_lifecycle(monkeypatch) -> None:
    path = ROOT / "scripts" / "local_preflight.py"
    spec = importlib.util.spec_from_file_location("local_preflight", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[tuple[list[str], dict[str, str]]] = []

    monkeypatch.setenv("COMPOSE_FILE", "/tmp/foreign-compose.yml")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "foreign-project")
    monkeypatch.setenv("AI_LAYER_POSTGRES_PORT", "54329")

    def fake_run(argv, **kwargs):
        command = list(argv)
        env = dict(kwargs.get("env") or {})
        calls.append((command, env))
        if "port" in command:
            return SimpleNamespace(returncode=0, stdout="127.0.0.1:49152\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.main() == 0
    compose_calls = [(argv, env) for argv, env in calls if argv[:2] == ["docker", "compose"]]
    assert len(compose_calls) == 3
    project_names = {argv[argv.index("--project-name") + 1] for argv, _env in compose_calls}
    assert len(project_names) == 1
    assert all(env["AI_LAYER_POSTGRES_PORT"] == "0" for _argv, env in compose_calls)
    assert all("COMPOSE_FILE" not in env for _argv, env in compose_calls)
    assert all("COMPOSE_PROJECT_NAME" not in env for _argv, env in compose_calls)
    assert calls[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]
    gate_call = next((argv, env) for argv, env in calls if argv == ["make", "preflight-ci"])
    assert gate_call[1]["AI_LAYER_TEST_POSTGRES_URL"].endswith("@127.0.0.1:49152/ai_layer")


def test_local_preflight_rejects_ambiguous_port_mapping() -> None:
    path = ROOT / "scripts" / "local_preflight.py"
    spec = importlib.util.spec_from_file_location("local_preflight_port", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._host_port("127.0.0.1:49152\n") == 49152
    for output in ("", "0.0.0.0:49152", "127.0.0.1:not-a-port", "127.0.0.1:70000"):
        try:
            module._host_port(output)
        except RuntimeError:
            continue
        raise AssertionError(f"accepted unsafe port mapping: {output!r}")


def test_local_preflight_cleans_up_after_gate_failure(monkeypatch) -> None:
    path = ROOT / "scripts" / "local_preflight.py"
    spec = importlib.util.spec_from_file_location("local_preflight_failure", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        command = list(argv)
        calls.append(command)
        if "port" in command:
            return SimpleNamespace(returncode=0, stdout="127.0.0.1:49152\n", stderr="")
        if command == ["make", "preflight-ci"]:
            return SimpleNamespace(returncode=7, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.main() == 7
    assert calls[-1][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_ci_calls_repository_gate_owners_instead_of_raw_gate_commands() -> None:
    workflow = _text(".github/workflows/quality.yml")
    assert "- run: make quality" in workflow
    assert "- run: make postgres-gate" in workflow
    assert "python scripts/quality_gate.py --deterministic-wheel" not in workflow
    assert "python scripts/postgres_gate.py" not in workflow


def test_postgres_gate_discovers_every_postgres_marked_contract() -> None:
    gate = _text("scripts/postgres_gate.py")
    assert '"-m",\n                    "postgres",\n                    "tests",' in gate
    assert "tests/test_postgres_hardening.py" not in gate


def test_development_bootstrap_is_excluded_from_runtime_release() -> None:
    path = ROOT / "scripts" / "build_release_archive.py"
    spec = importlib.util.spec_from_file_location("build_release_archive", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    included = {item.relative_to(ROOT).as_posix() for item in module.included_files(ROOT)}
    assert "AGENTS.md" not in included
    assert "GEMINI.md" not in included
    assert "PRODUCT_GOAL.md" not in included
    assert not any(item.startswith(".githooks/") for item in included)
    assert {".agents", ".codex"} <= module.EXCLUDED_ROOT_ENTRIES


def test_development_trust_chain_is_governance_protected() -> None:
    policy = json.loads(_text("release/governance-policy.json"))
    protected = set(policy["protected_paths"])
    expected = {
        ".github/workflows/quality.yml",
        ".githooks/pre-commit",
        ".githooks/pre-push",
        "AGENTS.md",
        "GEMINI.md",
        "MAINTAINER_INSTRUCTIONS.md",
        "Makefile",
        "QUALITY_GATES.md",
        "docker-compose.yml",
        "pyproject.toml",
        "scripts/local_preflight.py",
        "scripts/postgres_gate.py",
        "scripts/skill_gate.py",
        "tests/test_development_governance.py",
    }
    assert expected <= protected
