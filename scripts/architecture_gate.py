#!/usr/bin/env python3
"""Fail-closed maintainability gate for Local AI Development Layer production code.

The policy file may tighten these limits but may not loosen the built-in hard ceilings.
This prevents an ordinary feature change from bypassing the gate by simply raising a JSON value.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "release" / "architecture-policy.json"
SOURCE_ROOT = ROOT / "src" / "ai_layer"

# Absolute safety ceilings. release/architecture-policy.json can only make these stricter.
HARD_MAX_MODULE_LINES = 500
HARD_MAX_COMPOSITION_ROOT_LINES = 550
HARD_MAX_MODULE_BYTES = 36_000
HARD_MAX_COMPOSITION_ROOT_BYTES = 42_000
HARD_MAX_FUNCTION_LINES = 120
HARD_MAX_FUNCTION_STATEMENTS = 80
HARD_MAX_CYCLOMATIC_COMPLEXITY = 24
HARD_MAX_NESTING_DEPTH = 5
SOFT_WARN_MODULE_LINES = 300

_CONTROL_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler)
_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)


@dataclass(frozen=True)
class FunctionMetric:
    qualified_name: str
    line: int
    lines: int
    statements: int
    complexity: int
    nesting: int


@dataclass(frozen=True)
class ModuleMetric:
    relpath: str
    module: str
    lines: int
    source_bytes: int
    functions: tuple[FunctionMetric, ...]
    imports: frozenset[str]
    has_definitions: bool


def _physical_lines(text: str) -> int:
    return len(text.splitlines())


def _complexity(node: ast.AST) -> int:
    """Small deterministic McCabe-style score based on control-flow decisions.

    Boolean expression width is intentionally not counted: a linear validation predicate is not
    treated like nested control flow. Nesting is enforced independently.
    """
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _CONTROL_NODES):
            score += 1
        elif isinstance(child, ast.Match):
            score += max(1, len(child.cases))
    return score


def _nesting_depth(node: ast.AST) -> int:
    maximum = 0

    def visit(current: ast.AST, depth: int) -> None:
        nonlocal maximum
        nested = depth + 1 if isinstance(current, _NESTING_NODES) else depth
        maximum = max(maximum, nested)
        for child in ast.iter_child_nodes(current):
            visit(child, nested)

    visit(node, 0)
    return maximum


def _module_name(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_internal_imports(tree: ast.AST, module: str, modules: set[str]) -> set[str]:
    imports: set[str] = set()
    candidates = sorted(modules, key=len, reverse=True)

    def record(target: str) -> None:
        if not target.startswith("ai_layer"):
            return
        for candidate in candidates:
            if target == candidate or target.startswith(candidate + "."):
                imports.add(candidate)
                return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                target = node.module or ""
            else:
                package = module.split(".")[:-1]
                up = node.level - 1
                base = package[: len(package) - up] if up else package
                suffix = (node.module or "").split(".") if node.module else []
                target = ".".join(base + suffix)
            # ``from package import submodule`` semantically imports package.submodule when it exists.
            for alias in node.names:
                submodule = f"{target}.{alias.name}" if target else alias.name
                if submodule in modules:
                    record(submodule)
                else:
                    record(target)
    imports.discard(module)
    return imports


def collect_metrics(source_root: Path) -> dict[str, ModuleMetric]:
    paths = sorted(source_root.rglob("*.py"))
    modules = {_module_name(path, source_root) for path in paths}
    parsed: dict[Path, tuple[str, ast.Module, str]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        parsed[path] = (_module_name(path, source_root), ast.parse(text, filename=str(path)), text)

    result: dict[str, ModuleMetric] = {}
    root = source_root.parents[1]
    for path, (module, tree, text) in parsed.items():
        functions: list[FunctionMetric] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            end = getattr(node, "end_lineno", node.lineno)
            functions.append(
                FunctionMetric(
                    qualified_name=f"{module}.{node.name}",
                    line=node.lineno,
                    lines=end - node.lineno + 1,
                    statements=sum(1 for item in ast.walk(node) if isinstance(item, ast.stmt)) - 1,
                    complexity=_complexity(node),
                    nesting=_nesting_depth(node),
                )
            )
        relpath = path.relative_to(root).as_posix()
        result[module] = ModuleMetric(
            relpath=relpath,
            module=module,
            lines=_physical_lines(text),
            source_bytes=len(text.encode("utf-8")),
            functions=tuple(functions),
            imports=frozenset(_resolve_internal_imports(tree, module, modules)),
            has_definitions=any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for node in tree.body
            ),
        )
    return result


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in graph:
                continue
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] != indexes[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in indexes:
            visit(node)
    return sorted(components)


def _capability_for(module: str, rules: list[dict]) -> str | None:
    matches: list[tuple[int, str]] = []
    for rule in rules:
        prefix = rule.get("prefix") if isinstance(rule, dict) else None
        capability = rule.get("capability") if isinstance(rule, dict) else None
        if not isinstance(prefix, str) or not isinstance(capability, str):
            continue
        if module == prefix or module.startswith(prefix + "."):
            matches.append((len(prefix), capability))
    return max(matches)[1] if matches else None


def _capability_analysis(modules: dict[str, ModuleMetric], policy: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    rules = policy.get("capabilities")
    forbidden = policy.get("forbidden_capability_dependencies")
    if not isinstance(rules, list) or not rules:
        return ["architecture policy capabilities must be a non-empty list"], {}
    if not isinstance(forbidden, list):
        return ["architecture policy forbidden_capability_dependencies must be a list"], {}

    owners: dict[str, str] = {}
    for module in sorted(modules):
        owner = _capability_for(module, rules)
        if owner is None:
            errors.append(f"{module}: no architecture capability owner")
        else:
            owners[module] = owner

    graph: dict[str, set[str]] = {}
    edge_modules: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for module, metric in modules.items():
        source = owners.get(module)
        if source is None:
            continue
        graph.setdefault(source, set())
        for target_module in metric.imports:
            target = owners.get(target_module)
            if target is None or target == source:
                continue
            graph[source].add(target)
            graph.setdefault(target, set())
            edge_modules.setdefault((source, target), []).append((module, target_module))

    for rule in forbidden:
        if not isinstance(rule, dict):
            errors.append("forbidden capability dependency entries must be objects")
            continue
        source = rule.get("from")
        target = rule.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            errors.append("forbidden capability dependency requires string from/to")
            continue
        if target in graph.get(source, set()):
            examples = edge_modules.get((source, target), [])[:3]
            rendered = ", ".join(f"{a} -> {b}" for a, b in examples)
            reason = str(rule.get("reason") or "dependency is forbidden")
            errors.append(
                f"capability dependency {source} -> {target} is forbidden: {reason}; {rendered}"
            )

    cycles = _strongly_connected_components(graph)
    for component in cycles:
        errors.append("capability dependency cycle: " + " -> ".join(component))

    edge_list = [
        f"{source}->{target}" for source in sorted(graph) for target in sorted(graph[source])
    ]
    return errors, {
        "capabilities": sorted(graph),
        "capability_edges": edge_list,
        "capability_cycles": len(cycles),
    }


_EPIC_FORBIDDEN_OWNER_NAMES = frozenset(
    {
        "TaskStage",
        "WorkerLease",
        "ReviewerLifecycle",
        "FixerLifecycle",
        "VerificationLifecycle",
        "RepositorySnapshot",
        "ReviewFinding",
        "RemediationLoop",
    }
)


def _epic_boundary_errors(source_root: Path) -> list[str]:
    """Reject a second Task Engine hidden inside the future Epic package.

    Import boundaries already prevent epics from reaching Task/DB/Workspace/Verification internals.
    This additional owner-name rule catches a copied lifecycle implementation before it has imports.
    """
    errors: list[str] = []
    epic_root = source_root / "epics"
    if not epic_root.exists():
        return ["Epic boundary package is missing"]
    for path in sorted(epic_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(source_root.parents[1]).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            compact = node.name.replace("_", "").casefold()
            for forbidden in _EPIC_FORBIDDEN_OWNER_NAMES:
                if forbidden.replace("_", "").casefold() in compact:
                    errors.append(
                        f"{rel}:{node.lineno}: Epic boundary must not own Task lifecycle primitive `{node.name}` "
                        f"(matches forbidden `{forbidden}`)"
                    )
                    break
    return errors


def _load_policy(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 2:
        raise ValueError("architecture policy must be an object with schema=2")
    return data


def _validated_limits(policy: dict) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    raw = policy.get("limits")
    if not isinstance(raw, dict):
        return {}, ["architecture policy limits must be an object"]
    hard = {
        "module_lines": HARD_MAX_MODULE_LINES,
        "composition_root_lines": HARD_MAX_COMPOSITION_ROOT_LINES,
        "module_bytes": HARD_MAX_MODULE_BYTES,
        "composition_root_bytes": HARD_MAX_COMPOSITION_ROOT_BYTES,
        "function_lines": HARD_MAX_FUNCTION_LINES,
        "function_statements": HARD_MAX_FUNCTION_STATEMENTS,
        "cyclomatic_complexity": HARD_MAX_CYCLOMATIC_COMPLEXITY,
        "nesting_depth": HARD_MAX_NESTING_DEPTH,
    }
    limits: dict[str, int] = {}
    for key, ceiling in hard.items():
        value = raw.get(key)
        if not isinstance(value, int) or value <= 0:
            errors.append(f"architecture policy {key} must be a positive integer")
            continue
        if value > ceiling:
            errors.append(
                f"architecture policy {key}={value} exceeds built-in hard ceiling {ceiling}"
            )
        limits[key] = min(value, ceiling)
    return limits, errors


def analyze(source_root: Path, policy: dict) -> dict:
    limits, errors = _validated_limits(policy)
    if errors:
        return {"ok": False, "errors": errors, "metrics": {}}

    composition = set(policy.get("composition_roots") or [])
    facades = policy.get("facades") or {}
    ratchets = policy.get("ratchets") or {}
    if not isinstance(facades, dict) or not isinstance(ratchets, dict):
        return {"ok": False, "errors": ["facades and ratchets must be objects"], "metrics": {}}

    modules = collect_metrics(source_root)
    by_path = {metric.relpath: metric for metric in modules.values()}
    warnings: list[str] = []

    for relpath, metric in sorted(by_path.items()):
        ratchet_rule = ratchets.get(relpath) if isinstance(ratchets.get(relpath), dict) else None
        if relpath in composition:
            if ratchet_rule and isinstance(ratchet_rule.get("max_lines"), int):
                # Only explicitly ratcheted legacy composition roots may exceed the normal
                # composition-root policy limit, never the absolute built-in ceiling.
                module_limit = max(
                    limits["composition_root_lines"],
                    min(int(ratchet_rule["max_lines"]), HARD_MAX_COMPOSITION_ROOT_LINES),
                )
            else:
                module_limit = limits["composition_root_lines"]
        elif ratchet_rule and isinstance(ratchet_rule.get("max_lines"), int):
            # Existing oversized ordinary owners get a one-way migration ceiling: they may shrink
            # toward the normal policy limit, but they may not grow and no new module gets this exception.
            module_limit = max(
                limits["module_lines"], min(int(ratchet_rule["max_lines"]), HARD_MAX_MODULE_LINES)
            )
        else:
            module_limit = limits["module_lines"]
        if metric.lines > module_limit:
            errors.append(f"{relpath}: {metric.lines} lines exceeds module limit {module_limit}")
        elif (
            metric.lines > SOFT_WARN_MODULE_LINES
            and relpath not in composition
            and ratchet_rule is None
        ):
            warnings.append(
                f"{relpath}: {metric.lines} lines exceeds soft maintainability warning {SOFT_WARN_MODULE_LINES}; "
                "new growth should justify ownership or extract a cohesive seam"
            )
        byte_limit = (
            limits["composition_root_bytes"] if relpath in composition else limits["module_bytes"]
        )
        if metric.source_bytes > byte_limit:
            errors.append(
                f"{relpath}: {metric.source_bytes} source bytes exceeds module byte limit {byte_limit}"
            )
        for function in metric.functions:
            if function.lines > limits["function_lines"]:
                errors.append(
                    f"{relpath}:{function.line} {function.qualified_name}: {function.lines} lines exceeds function limit {limits['function_lines']}"
                )
            if function.statements > limits["function_statements"]:
                errors.append(
                    f"{relpath}:{function.line} {function.qualified_name}: {function.statements} statements exceeds {limits['function_statements']}"
                )
            if function.complexity > limits["cyclomatic_complexity"]:
                errors.append(
                    f"{relpath}:{function.line} {function.qualified_name}: complexity {function.complexity} exceeds {limits['cyclomatic_complexity']}"
                )
            if function.nesting > limits["nesting_depth"]:
                errors.append(
                    f"{relpath}:{function.line} {function.qualified_name}: nesting {function.nesting} exceeds {limits['nesting_depth']}"
                )

    for relpath, max_lines in sorted(facades.items()):
        metric = by_path.get(relpath)
        if metric is None:
            errors.append(f"declared facade is missing: {relpath}")
            continue
        if not isinstance(max_lines, int) or max_lines <= 0 or max_lines > 150:
            errors.append(f"{relpath}: facade ceiling must be an integer <=150")
        elif metric.lines > max_lines:
            errors.append(f"{relpath}: facade grew to {metric.lines} lines; ceiling is {max_lines}")
        if metric.has_definitions:
            errors.append(
                f"{relpath}: compatibility facade must not own function/class definitions"
            )
        package_prefix = metric.module.rsplit(".", 1)[0] + "."
        for importer in modules.values():
            if (
                importer.module.startswith(package_prefix)
                and importer.module != metric.module
                and metric.module in importer.imports
            ):
                errors.append(
                    f"{importer.relpath}: focused module must not import its compatibility facade {metric.module}"
                )

    for relpath, rule in sorted(ratchets.items()):
        metric = by_path.get(relpath)
        if metric is None:
            errors.append(f"ratcheted module is missing: {relpath}")
            continue
        if not isinstance(rule, dict) or not isinstance(rule.get("max_lines"), int):
            errors.append(f"{relpath}: invalid ratchet rule")
            continue
        max_lines = int(rule["max_lines"])
        target = int(rule.get("target_lines", max_lines))
        hard_limit = (
            HARD_MAX_COMPOSITION_ROOT_LINES if relpath in composition else HARD_MAX_MODULE_LINES
        )
        if max_lines > hard_limit:
            errors.append(
                f"{relpath}: ratchet max_lines {max_lines} exceeds absolute hard limit {hard_limit}"
            )
        target_limit = (
            limits["composition_root_lines"] if relpath in composition else limits["module_lines"]
        )
        if target > target_limit:
            errors.append(
                f"{relpath}: ratchet target {target} must reach its normal policy limit {target_limit} or lower"
            )
        if target > max_lines:
            errors.append(f"{relpath}: ratchet target_lines must be <= max_lines")
        if metric.lines > max_lines:
            errors.append(
                f"{relpath}: no-growth ratchet violated ({metric.lines}>{max_lines}); extract a coherent seam before adding code"
            )
        elif metric.lines < max_lines:
            if metric.lines <= target:
                errors.append(
                    f"{relpath}: ratchet target reached ({metric.lines}<={target}); remove the legacy ratchet so the normal module limit owns this file"
                )
            else:
                errors.append(
                    f"{relpath}: ratchet ceiling is stale ({max_lines}>{metric.lines}); lower max_lines to {metric.lines} so removed debt cannot regrow"
                )

    graph = {name: set(metric.imports) for name, metric in modules.items()}
    module_cycles = _strongly_connected_components(graph)
    for component in module_cycles:
        errors.append("internal import cycle: " + " -> ".join(component))

    capability_errors, capability_metrics = _capability_analysis(modules, policy)
    errors.extend(capability_errors)
    epic_errors = _epic_boundary_errors(source_root)
    errors.extend(epic_errors)

    metrics = {
        "modules": len(modules),
        "largest_modules": [
            {"path": item.relpath, "lines": item.lines, "source_bytes": item.source_bytes}
            for item in sorted(modules.values(), key=lambda x: (-x.lines, x.relpath))[:10]
        ],
        "max_function_lines": max(
            (f.lines for m in modules.values() for f in m.functions), default=0
        ),
        "max_function_statements": max(
            (f.statements for m in modules.values() for f in m.functions), default=0
        ),
        "max_complexity": max(
            (f.complexity for m in modules.values() for f in m.functions), default=0
        ),
        "max_nesting": max((f.nesting for m in modules.values() for f in m.functions), default=0),
        "import_cycles": len(module_cycles),
        "soft_module_warning_lines": SOFT_WARN_MODULE_LINES,
        "soft_warnings": warnings,
        "epic_boundary_errors": len(epic_errors),
        **capability_metrics,
    }
    return {"ok": not errors, "errors": errors, "warnings": warnings, "metrics": metrics}


def _committed_ratchets(root: Path) -> dict[str, dict] | None:
    """Read the committed policy when running from a Git checkout.

    Release archives intentionally contain no .git directory, so this is an additional development
    ratchet rather than a prerequisite for release execution.
    """
    if not (root / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "show", "HEAD:release/architecture-policy.json"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    ratchets = data.get("ratchets") if isinstance(data, dict) else None
    return ratchets if isinstance(ratchets, dict) else None


def _ratchet_increase_errors(policy: dict, previous: dict[str, dict] | None) -> list[str]:
    if previous is None:
        return []
    errors: list[str] = []
    current = policy.get("ratchets") or {}
    for relpath, old_rule in previous.items():
        if not isinstance(old_rule, dict) or not isinstance(old_rule.get("max_lines"), int):
            continue
        new_rule = current.get(relpath)
        if new_rule is None:
            continue
        if not isinstance(new_rule, dict) or not isinstance(new_rule.get("max_lines"), int):
            continue
        if int(new_rule["max_lines"]) > int(old_rule["max_lines"]):
            errors.append(
                f"{relpath}: ratchet ceiling increased from committed {old_rule['max_lines']} to {new_rule['max_lines']}; ordinary changes may only keep or lower it"
            )
    return errors


def run_gate(root: Path = ROOT) -> dict:
    policy_path = root / "release" / "architecture-policy.json"
    source_root = root / "src" / "ai_layer"
    try:
        policy = _load_policy(policy_path)
        result = analyze(source_root, policy)
        baseline_errors = _ratchet_increase_errors(policy, _committed_ratchets(root))
        if baseline_errors:
            result["errors"] = [*result.get("errors", []), *baseline_errors]
            result["ok"] = False
        return result
    except Exception as exc:
        return {"ok": False, "errors": [f"architecture gate failed closed: {exc}"], "metrics": {}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_gate()
    print(json.dumps(result, indent=None if args.json else 2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
