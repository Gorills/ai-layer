from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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


def test_git_hooks_fail_closed_into_repository_targets() -> None:
    pre_commit = _text(".githooks/pre-commit")
    pre_push = _text(".githooks/pre-push")
    assert "set -euo pipefail" in pre_commit
    assert "exec make fast-gate" in pre_commit
    assert "set -euo pipefail" in pre_push
    assert "exec make preflight" in pre_push


def test_makefile_owns_local_and_ci_gate_composition() -> None:
    makefile = _text("Makefile")
    assert "quality:\n\tpython scripts/quality_gate.py --deterministic-wheel" in makefile
    assert "postgres-gate:\n\tpython scripts/postgres_gate.py" in makefile
    assert "preflight-ci:\n\t$(MAKE) quality\n\t$(MAKE) postgres-gate" in makefile
    assert "docker compose up -d --wait postgres" in makefile
    assert 'AI_LAYER_TEST_POSTGRES_URL="$(LOCAL_POSTGRES_URL)" $(MAKE) preflight-ci' in makefile
    assert "git config core.hooksPath .githooks" in makefile


def test_ci_calls_repository_gate_owners_instead_of_raw_gate_commands() -> None:
    workflow = _text(".github/workflows/quality.yml")
    assert "- run: make quality" in workflow
    assert "- run: make postgres-gate" in workflow
    assert "python scripts/quality_gate.py --deterministic-wheel" not in workflow
    assert "python scripts/postgres_gate.py" not in workflow


def test_development_bootstrap_is_excluded_from_runtime_release() -> None:
    path = ROOT / "scripts" / "build_release_archive.py"
    spec = importlib.util.spec_from_file_location("build_release_archive", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    included = {item.relative_to(ROOT).as_posix() for item in module.included_files(ROOT)}
    assert "AGENTS.md" not in included
    assert "GEMINI.md" not in included
    assert not any(item.startswith(".githooks/") for item in included)


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
        "pyproject.toml",
        "scripts/postgres_gate.py",
        "scripts/skill_gate.py",
        "tests/test_development_governance.py",
    }
    assert expected <= protected
