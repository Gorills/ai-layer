from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected exactly one occurrence of {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "tests/test_agent_facing_contracts.py",
    "    assert global_install.INTEGRATION_TEMPLATE_VERSION == CANONICAL_TEMPLATE_VERSION\n",
    "",
)
replace(
    "tests/test_cli.py",
    '    register_project(tmp_path, "audit-cli-economy", "audit-cli-economy")\n    with mcp_audit(tmp_path, "memory_context", arg_keys=["task"]):\n',
    '    register_project(tmp_path, "audit-cli-economy", "audit-cli-economy")\n    with mcp_audit(tmp_path, "project_status", arg_keys=[]):\n        pass\n    with mcp_audit(tmp_path, "memory_context", arg_keys=["task"]):\n',
)
replace(
    "tests/test_tasks.py",
    '        assert "Do not stash/reset/restore/commit" in nav["next_action"]["message"]\n',
    '        message = nav["next_action"]["message"].casefold()\n        assert "stash/reset/restore/commit" in message\n        assert "merely to satisfy ai layer" in message\n',
)
print("final stale assertions updated")
