from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _gate_module():
    path = ROOT / "scripts" / "architecture_gate.py"
    spec = importlib.util.spec_from_file_location("ai_layer_architecture_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the module through sys.modules while decorating.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _policy(**overrides):
    data = {
        "schema": 2,
        "limits": {
            "module_lines": 500,
            "composition_root_lines": 550,
            "module_bytes": 36000,
            "composition_root_bytes": 42000,
            "function_lines": 120,
            "function_statements": 80,
            "cyclomatic_complexity": 24,
            "nesting_depth": 5,
        },
        "composition_roots": [],
        "facades": {},
        "ratchets": {},
        "capabilities": [{"prefix": "ai_layer", "capability": "Foundation"}],
        "forbidden_capability_dependencies": [],
    }
    data.update(overrides)
    return data


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "src" / "ai_layer"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    return root


def test_current_production_architecture_passes_hard_gate():
    gate = _gate_module()
    result = gate.run_gate(ROOT)
    assert result["ok"] is True, result["errors"]
    assert result["metrics"]["import_cycles"] == 0


def test_gate_rejects_oversized_production_module(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    (source / "oversized.py").write_text("x = 1\n" * 501, encoding="utf-8")
    result = gate.analyze(source, _policy())
    assert result["ok"] is False
    assert any("exceeds module limit 500" in error for error in result["errors"])




def test_legacy_composition_root_requires_ratchet_to_exceed_normal_limit(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    cli = source / "cli"
    cli.mkdir()
    (cli / "__init__.py").write_text("", encoding="utf-8")
    (cli / "app.py").write_text("x = 1\n" * 551, encoding="utf-8")
    policy = _policy(composition_roots=["src/ai_layer/cli/app.py"])
    result = gate.analyze(source, policy)
    assert result["ok"] is False
    assert any("exceeds module limit 550" in error for error in result["errors"])

    policy["ratchets"] = {
        "src/ai_layer/cli/app.py": {"max_lines": 551, "target_lines": 550}
    }
    result = gate.analyze(source, policy)
    assert result["ok"] is False
    assert any("exceeds absolute hard limit 550" in error for error in result["errors"])

def test_gate_rejects_source_packing_that_evades_line_limit(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    (source / "packed.py").write_text('PAYLOAD = "' + ('x' * 36050) + '"\n', encoding="utf-8")
    result = gate.analyze(source, _policy())
    assert result["ok"] is False
    assert any("source bytes exceeds module byte limit" in error for error in result["errors"])


def test_gate_rejects_too_many_function_statements(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    body = "\n".join(f"    x{i} = {i}" for i in range(81))
    (source / "statements.py").write_text("def overloaded():\n" + body + "\n", encoding="utf-8")
    result = gate.analyze(source, _policy())
    assert result["ok"] is False
    assert any("statements exceeds 80" in error for error in result["errors"])

def test_gate_rejects_no_growth_ratchet_violation(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    target = source / "owner.py"
    target.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    result = gate.analyze(
        source,
        _policy(ratchets={"src/ai_layer/owner.py": {"max_lines": 2, "target_lines": 1}}),
    )
    assert result["ok"] is False
    assert any("no-growth ratchet violated" in error for error in result["errors"])


def test_gate_rejects_internal_import_cycle(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    (source / "a.py").write_text("from ai_layer import b\n", encoding="utf-8")
    (source / "b.py").write_text("from ai_layer import a\n", encoding="utf-8")
    result = gate.analyze(source, _policy())
    assert result["ok"] is False
    assert any("internal import cycle" in error for error in result["errors"])


def test_gate_rejects_business_logic_inside_declared_facade(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    package = source / "tasks"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text("def do_work():\n    return 1\n", encoding="utf-8")
    result = gate.analyze(
        source,
        _policy(facades={"src/ai_layer/tasks/service.py": 120}),
    )
    assert result["ok"] is False
    assert any("facade must not own function/class definitions" in error for error in result["errors"])



def test_gate_forces_ratchet_ceiling_down_after_owner_shrinks(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    (source / "owner.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    result = gate.analyze(
        source,
        _policy(ratchets={"src/ai_layer/owner.py": {"max_lines": 3, "target_lines": 1}}),
    )
    assert result["ok"] is False
    assert any("ratchet ceiling is stale" in error for error in result["errors"])


def test_committed_ratchet_cannot_be_raised():
    gate = _gate_module()
    previous = {"src/ai_layer/cli/app.py": {"max_lines": 100}}
    current = {"ratchets": {"src/ai_layer/cli/app.py": {"max_lines": 101}}}
    errors = gate._ratchet_increase_errors(current, previous)
    assert any("ratchet ceiling increased from committed 100 to 101" in error for error in errors)

def test_policy_cannot_raise_built_in_hard_ceiling(tmp_path: Path):
    gate = _gate_module()
    source = _source(tmp_path)
    policy = _policy()
    policy["limits"]["module_lines"] = gate.HARD_MAX_MODULE_LINES + 1
    result = gate.analyze(source, policy)
    assert result["ok"] is False
    assert any("exceeds built-in hard ceiling" in error for error in result["errors"])
