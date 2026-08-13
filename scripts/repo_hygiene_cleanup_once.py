from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


def replace_all(path: str, old: str, new: str, *, minimum: int = 1) -> None:
    text = read(path)
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(f"{path}: expected at least {minimum} occurrences, found {count}: {old!r}")
    write(path, text.replace(old, new))


def edit_function(path: str, name: str, transform) -> None:
    text = read(path)
    match = re.search(rf"(?m)^def {re.escape(name)}\b", text)
    if not match:
        raise RuntimeError(f"{path}: function {name} not found")
    next_match = re.search(r"(?m)^def \w+\b", text[match.end() :])
    end = match.end() + next_match.start() if next_match else len(text)
    block = text[match.start() : end]
    changed = transform(block)
    if changed == block:
        raise RuntimeError(f"{path}: transform made no change in {name}")
    write(path, text[: match.start()] + changed + text[end:])


# One source for integration/bootstrap compatibility versions.
replace_once(
    "src/ai_layer/integrations/global_install.py",
    "from ai_layer.skills.native import remove_global_native_skills, sync_global_native_skills\n\nINTEGRATION_TEMPLATE_VERSION = 23\nGLOBAL_BOOTSTRAP_VERSION = 13\nGLOBAL_BOOTSTRAP_MARKER = f\"<!-- AI-LAYER GLOBAL BOOTSTRAP v{GLOBAL_BOOTSTRAP_VERSION} -->\"\n",
    "from ai_layer.skills.native import remove_global_native_skills, sync_global_native_skills\nfrom ai_layer.integrations.versioning import (\n    GLOBAL_BOOTSTRAP_MARKER,\n    GLOBAL_BOOTSTRAP_VERSION,\n    INTEGRATION_TEMPLATE_VERSION,\n)\n",
)
replace_once(
    "src/ai_layer/integrations/service.py",
    "from ai_layer.integrations.global_install import (\n    GLOBAL_BOOTSTRAP_MARKER,\n    _cursor_plugin_owned,\n    _merge_codex_config,\n)\n",
    "from ai_layer.integrations.global_install import (\n    _cursor_plugin_owned,\n    _merge_codex_config,\n)\n",
)
replace_once(
    "src/ai_layer/integrations/service.py",
    "from ai_layer.skills.native import (\n    remove_legacy_project_bridge,\n    remove_project_native_skills,\n    sync_project_native_skills,\n)\n\nINTEGRATION_TEMPLATE_VERSION = 23\nGLOBAL_BOOTSTRAP_VERSION = 13\n",
    "from ai_layer.skills.native import (\n    remove_legacy_project_bridge,\n    remove_project_native_skills,\n    sync_project_native_skills,\n)\nfrom ai_layer.integrations.versioning import (\n    GLOBAL_BOOTSTRAP_MARKER,\n    GLOBAL_BOOTSTRAP_VERSION,\n    INTEGRATION_TEMPLATE_VERSION,\n)\n",
)

# Current Knowledge naming inside application transport; keep old names only as aliases.
replace_once(
    "src/ai_layer/application/context.py",
    "from ai_layer.memory.service import decision_search, memory_search\n\n\ndef project_details",
    "from ai_layer.memory.service import decision_search, memory_search\n\nLEGACY_CONTEXT_EPIC_OPEN_LIMIT = 8\nLEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT = 2\nLEGACY_CONTEXT_SUMMARY_MAX_CHARS = 700\nLEGACY_CONTEXT_SOURCE_POINTER_LIMIT = 6\n\n\ndef project_details",
)
replace_once(
    "src/ai_layer/application/context.py",
    "def search_memory(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:\n    with session_scope() as db:\n        project = get_project(db, project_root)\n        return memory_search(db, project, query, limit)\n",
    "def search_knowledge(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:\n    with session_scope() as db:\n        project = get_project(db, project_root)\n        return memory_search(db, project, query, limit)\n\n\ndef search_memory(project_root: str | Path, query: str, limit: int = 8) -> list[dict]:\n    \"\"\"Backward-compatible application alias for search_knowledge.\"\"\"\n    return search_knowledge(project_root, query, limit)\n",
)
replace_once("src/ai_layer/application/context.py", "for item in open_rows[:8]", "for item in open_rows[:LEGACY_CONTEXT_EPIC_OPEN_LIMIT]")
replace_once("src/ai_layer/application/context.py", 'str(item.get("summary") or "")[:700]', 'str(item.get("summary") or "")[:LEGACY_CONTEXT_SUMMARY_MAX_CHARS]')
replace_once("src/ai_layer/application/context.py", 'list(item.get("source_pointers") or [])[:6]', 'list(item.get("source_pointers") or [])[:LEGACY_CONTEXT_SOURCE_POINTER_LIMIT]')
replace_once("src/ai_layer/application/context.py", 'list(brief.get("verified_knowledge") or [])[:2]', 'list(brief.get("verified_knowledge") or [])[:LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT]')
replace_once(
    "src/ai_layer/application/transport.py",
    "def memory_search(\n    _scope: ApplicationScope, project: ProjectRef, query: str, limit: int\n) -> list[dict]:\n    return context_uc.search_memory(project.root_path, query, limit)\n",
    "def knowledge_search(\n    _scope: ApplicationScope, project: ProjectRef, query: str, limit: int\n) -> list[dict]:\n    return context_uc.search_knowledge(project.root_path, query, limit)\n\n\ndef memory_search(\n    _scope: ApplicationScope, project: ProjectRef, query: str, limit: int\n) -> list[dict]:\n    \"\"\"Backward-compatible transport alias for knowledge_search.\"\"\"\n    return knowledge_search(_scope, project, query, limit)\n",
)
replace_once(
    "src/ai_layer/mcp/tools/project_context.py",
    "from ai_layer.application.transport import memory_search as search_memory\n",
    "from ai_layer.application.transport import knowledge_search as search_knowledge\n",
)
replace_all("src/ai_layer/mcp/tools/project_context.py", "result = search_memory(db, project, query, bounded_limit)", "result = search_knowledge(db, project, query, bounded_limit)", minimum=2)

# QA flow must validate the current control-plane start, not require legacy memory_context.
audit = read("src/ai_layer/audit/service.py")
marker = "def check_latest_flow(project_root: str | Path, limit: int = 200) -> dict:\n"
start = audit.index(marker)
new_check = '''def check_latest_flow(project_root: str | Path, limit: int = 200) -> dict:\n    \"\"\"Verify the latest completed MCP flow against the current control-plane contract.\"\"\"\n    events = read_audit(project_root, limit=max(10, limit))\n\n    def terminal_kind(event: dict) -> str | None:\n        if not event.get(\"ok\", False):\n            return None\n        if event.get(\"tool\") == \"session_save\":\n            return \"session_save\"\n        metrics = event.get(\"metrics\") or {}\n        if (\n            event.get(\"tool\")\n            in {\n                \"task_stage_complete\",\n                \"task_implementation_complete\",\n                \"task_review_complete\",\n                \"task_fix_complete\",\n            }\n            and metrics.get(\"status\") == \"completed\"\n        ):\n            return \"managed_task\"\n        if event.get(\"tool\") == \"task_cancel\":\n            return \"cancelled_task\"\n        return None\n\n    completion_index = None\n    completion_kind = None\n    for index in range(len(events) - 1, -1, -1):\n        kind = terminal_kind(events[index])\n        if kind is not None:\n            completion_index = index\n            completion_kind = kind\n            break\n\n    boundary = completion_index if completion_index is not None else len(events)\n    previous_terminal = -1\n    for index in range(boundary - 1, -1, -1):\n        if terminal_kind(events[index]) is not None:\n            previous_terminal = index\n            break\n    segment_end = completion_index + 1 if completion_index is not None else len(events)\n    segment = events[previous_terminal + 1 : segment_end]\n\n    start_offset = next(\n        (\n            index\n            for index, event in enumerate(segment)\n            if event.get(\"ok\", False)\n            and event.get(\"tool\") in {\"project_status\", \"memory_context\"}\n        ),\n        None,\n    )\n    if start_offset is None:\n        return {\n            \"ok\": False,\n            \"reason\": \"no project_status or legacy memory_context start event found in latest flow\",\n            \"events\": len(segment),\n        }\n\n    flow = segment[start_offset:]\n    tools = [str(item.get(\"tool\")) for item in flow]\n    start_tool = tools[0]\n    failures = [\n        {\"tool\": item.get(\"tool\"), \"error_type\": item.get(\"error_type\")}\n        for item in flow\n        if not item.get(\"ok\", False)\n    ]\n    project_status_calls = sum(1 for tool in tools if tool == \"project_status\")\n    legacy_context_calls = sum(1 for tool in tools if tool == \"memory_context\")\n    duplicate_context = legacy_context_calls > 1\n    warnings: list[dict] = []\n    if start_tool == \"memory_context\":\n        warnings.append(\n            {\n                \"code\": \"legacy_flow_start\",\n                \"message\": (\n                    \"Latest flow started through legacy memory_context. Refresh installed AI Layer bootstrap \"\n                    \"instructions so registered-project work starts with project_status.\"\n                ),\n            }\n        )\n    if duplicate_context:\n        warnings.append(\n            {\n                \"code\": \"tool_economy\",\n                \"message\": (\n                    f\"legacy memory_context was called {legacy_context_calls} times in one completed flow; \"\n                    \"prefer focused Project Intelligence tools instead of repeating the compatibility payload.\"\n                ),\n            }\n        )\n\n    handoff_written = False\n    if completion_index is not None:\n        completion_metrics = events[completion_index].get(\"metrics\") or {}\n        handoff_written = completion_kind == \"session_save\" or bool(\n            completion_metrics.get(\"handoff_written\")\n        )\n    successful_terminal = completion_kind in {\"session_save\", \"managed_task\"}\n    versions = sorted(\n        {str(item.get(\"server_version\")) for item in flow if item.get(\"server_version\")}\n    )\n    current_start = start_tool == \"project_status\"\n    return {\n        \"ok\": successful_terminal and handoff_written and current_start and not failures,\n        \"tools\": tools,\n        \"flow_start_tool\": start_tool,\n        \"current_contract_start\": current_start,\n        \"session_saved\": handoff_written,\n        \"terminal_checkpoint\": completion_kind,\n        \"managed_task\": completion_kind == \"managed_task\",\n        \"project_status_calls\": project_status_calls,\n        \"memory_context_calls\": legacy_context_calls,\n        \"memory_context_count_scope\": \"ai_layer_server_audit_events_only\",\n        \"host_tool_schema_discovery_counted\": False,\n        \"duplicate_memory_context\": duplicate_context,\n        \"warnings\": warnings,\n        \"failures\": failures,\n        \"server_versions\": versions,\n        \"event_count\": len(flow),\n    }\n'''
write("src/ai_layer/audit/service.py", audit[:start] + new_check)
replace_once(
    "src/ai_layer/cli/commands/operations.py",
    '    \"\"\"Verify the latest memory_context -> ... -> session_save MCP flow for QA.\"\"\"',
    '    \"\"\"Verify the latest completed MCP flow against the current project_status-first contract.\"\"\"',
)
replace_once(
    "src/ai_layer/observability/context_report.py",
    '                        \"memory_context was delivered more than once in one MCP session; verify that \"\n                        \"task goal or external repository state actually changed.\"',
    '                        \"Legacy memory_context was delivered more than once in one MCP session; prefer \"\n                        \"project_status plus focused Project Intelligence tools unless compatibility is required.\"',
)

# Smoke the current control plane instead of the superseded composite-context workflow.
smoke = read("scripts/smoke.sh")
old_smoke_start = 'from ai_layer.application.context import get_memory_context, search_memory\n'
old_start = smoke.index(old_smoke_start)
old_end_marker = 'print("bootstrap/policy/context smoke PASS")\n'
old_end = smoke.index(old_end_marker, old_start) + len(old_end_marker)
new_smoke = '''from ai_layer.application.context import search_knowledge\nfrom ai_layer.application.knowledge import status as knowledge_status\nfrom ai_layer.application.project_intelligence import project_status\n\nroot = Path(os.environ[\"DEMO_ROOT\"])\nstate = knowledge_status(root)\nassert state[\"verified\"] == 0, state\nassert state[\"baseline_ready\"] is False, state\nassert state[\"onboarding_recommended\"] is True, state\nassert search_knowledge(root, \"FastAPI health endpoint\") == [], \"scan must not index current source as Project Knowledge\"\n\nstatus_payload = project_status(root)\nassert status_payload[\"agent_contract\"][\"startup\"][\"tool\"] == \"project_status\", status_payload\nassert status_payload[\"guidance\"][\"execution_owner\"] == \"host-native agent runtime\", status_payload\nassert status_payload[\"work\"][\"continuation\"][\"kind\"] == \"none\", status_payload[\"work\"]\nassert status_payload[\"guidance\"][\"project_map\"][\"read\"][\"tool\"] == \"project_search\", status_payload\nassert status_payload[\"guidance\"][\"project_map\"][\"update\"][\"tool\"] == \"project_map_reconcile\", status_payload\nprint(\"bootstrap/policy/project-intelligence smoke PASS\")\n'''
write("scripts/smoke.sh", smoke[:old_start] + new_smoke + smoke[old_end:])

# Tests should protect semantics, not accidental catalog/rule/package counts or bootstrap byte sizes.
replace_once("tests/test_policy.py", '    assert len(STATIC_POLICY_RULES) == 10\n', '    assert len(STATIC_POLICY_RULES) == len(set(STATIC_POLICY_RULES))\n')
replace_once("tests/test_policy.py", '    assert "`memory_search` is not a substitute" in low\n', '    assert "`knowledge_search` is for reviewed project facts/invariants" in low\n    assert "with `decision_search`" in low\n')
replace_once("tests/test_policy.py", '    assert "your own edits do not justify refreshing it" in low\n', '    assert "do not call legacy `memory_context` mechanically" in low\n    assert "current ai layer runtime/tool contracts define current procedure" in low\n')
replace_once(
    "tests/test_policy.py",
    '    # The static engineering floor is allowed to spend enough tokens to remain unambiguous to weak\n    # models, while procedure/domain knowledge remains progressive.\n    assert len(static_policy_markdown().encode("utf-8")) < 5000\n\n',
    '',
)

replace_once("tests/test_orchestrator_contract.py", '    assert len(global_text.encode("utf-8")) < 9000\n', '')
replace_once("tests/test_orchestrator_contract.py", '    assert "global native bootstrap and MCP Task Layer" in project_text\n', '    assert "global native bootstrap and MCP Project Intelligence/control-plane tools" in project_text\n')
replace_once("tests/test_orchestrator_contract.py", '    assert len(project_text.encode("utf-8")) < 500\n', '    assert "Mandatory engineering discipline" not in project_text\n')

replace_all("tests/test_integrations.py", '        assert len(text.encode("utf-8")) < 9000\n', '', minimum=1)
replace_once("tests/test_integrations.py", 'def test_global_bootstrap_is_small_and_project_text_bridge_is_legacy_only(tmp_path: Path):', 'def test_global_bootstrap_is_complete_and_project_text_bridge_is_legacy_only(tmp_path: Path):')
replace_once(
    "tests/test_integrations.py",
    '    assert len(legacy_bridge.encode("utf-8")) < 500\n    assert len(global_rule.encode("utf-8")) < 9000\n',
    '    assert "project binding (legacy compatibility)" in legacy_bridge\n    assert "Mandatory engineering discipline" not in legacy_bridge\n    assert "## AI Layer control-plane boundary" not in legacy_bridge\n',
)

replace_once("tests/test_skills.py", '        assert len(skills) == 44\n', '        assert skills\n        assert {"ai-layer-workflow", "epics", "architecture", "testing"} <= {\n            skill["slug"] for skill in skills\n        }\n')
replace_once("tests/test_skills.py", '        assert len(results[0]) == 44\n', '        assert len(results[0]) == len(list_skills())\n')

replace_once("tests/test_release_reproducibility.py", '    assert len(pins) >= 70\n', '    assert all(name and version for name, version in pins.items())\n')

replace_once("tests/test_context_trace.py", '    assert "native host reads/edits/tests/subagents" in seen["instructions"]\n', '    assert "Normal execution remains host-native" in seen["instructions"]\n')

replace_once("tests/test_tool_guidance.py", '    assert guidance["recommended_calls"][0]["tool"] == "memory_search"\n', '    assert guidance["recommended_calls"][0]["tool"] == "knowledge_search"\n')
replace_once("tests/test_tool_guidance.py", '    assert [item["tool"] for item in calls] == ["decision_search", "memory_search"]\n', '    assert [item["tool"] for item in calls] == ["decision_search", "knowledge_search"]\n')
replace_once("tests/test_tool_guidance.py", '    assert len(json.dumps(payload)) < 34000\n', '')
replace_once("tests/test_tool_guidance.py", '    assert len(encoded) < 5000, len(encoded)\n', '')

replace_once("tests/test_agent_facing_contracts.py", '    assert "not required" in result["agent_contract"]["managed_work"]["idle"].casefold()\n', '    assert "ordinary host-native work" in result["agent_contract"]["managed_work"]["idle"].casefold()\n')
replace_once("tests/test_agent_facing_contracts.py", '    assert "generic parallel DAG" in epics\n', '    assert "Do not invent parallel execution" in epics\n')

# Named compact-context bounds remain real contracts, but tests consume named constants rather than magic values.
replace_once(
    "tests/test_project_intelligence_control_plane.py",
    'from ai_layer.application.context import _compact_legacy_context\n',
    'from ai_layer.application.context import (\n    LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT,\n    LEGACY_CONTEXT_SOURCE_POINTER_LIMIT,\n    LEGACY_CONTEXT_SUMMARY_MAX_CHARS,\n    _compact_legacy_context,\n)\n',
)
replace_once("tests/test_project_intelligence_control_plane.py", '    assert len(compact["knowledge_hints"][0]["summary"]) == 700\n', '    assert len(compact["knowledge_hints"]) == LEGACY_CONTEXT_KNOWLEDGE_HINT_LIMIT - 1\n    assert len(compact["knowledge_hints"][0]["summary"]) == LEGACY_CONTEXT_SUMMARY_MAX_CHARS\n')
replace_once("tests/test_project_intelligence_control_plane.py", '    assert len(compact["knowledge_hints"][0]["source_pointers"]) == 6\n', '    assert len(compact["knowledge_hints"][0]["source_pointers"]) == LEGACY_CONTEXT_SOURCE_POINTER_LIMIT\n')

# Idle managed-work tests should verify the optional managed choice, not restore create_task as a permission gate.
for func_name in [
    "test_task_create_accepts_unknown_dirty_git_worktree_as_captured_baseline",
    "test_verified_terminal_dirty_state_is_allowed_as_next_task_baseline",
    "test_dashboard_state_exposes_create_task_navigation_when_only_historical_task_remains",
]:
    def transform(block: str) -> str:
        block = re.sub(r'(\["next_action"\]\["action"\]\s*==\s*)"create_task"', r'\1"host_native"', block)
        block = re.sub(
            r'(?m)^(\s*)assert (\w+)\["next_action"\]\["tool"\] == "task_create"$',
            r'\1assert \2["next_action"]["managed_option"]["tool"] == "task_create"',
            block,
        )
        return block
    edit_function("tests/test_tasks.py", func_name, transform)

# Audit tests now exercise project_status-first flows; legacy memory_context remains explicit compatibility telemetry.
def audit_requires(block: str) -> str:
    return block.replace('"memory_context"', '"project_status"', 1).replace('"memory_search"', '"knowledge_search"').replace('["memory_context", "memory_search", "session_save"]', '["project_status", "knowledge_search", "session_save"]')
edit_function("tests/test_audit.py", "test_audit_check_requires_completion_save", audit_requires)

def audit_duplicate(block: str) -> str:
    anchor = '    register_project(project, "audit-test", project.name)\n'
    block = block.replace(anchor, anchor + '    with mcp_audit(project, "project_status", arg_keys=[]):\n        pass\n', 1)
    block = block.replace('    assert result["memory_context_calls"] == 2\n', '    assert result["flow_start_tool"] == "project_status"\n    assert result["project_status_calls"] == 1\n    assert result["memory_context_calls"] == 2\n')
    old_warning = '            "message": "server-side memory_context was called 2 times in one completed flow; reuse returned context unless state changed materially.",\n'
    new_warning = '            "message": "legacy memory_context was called 2 times in one completed flow; prefer focused Project Intelligence tools instead of repeating the compatibility payload.",\n'
    block = block.replace(old_warning, new_warning)
    return block
edit_function("tests/test_audit.py", "test_audit_check_detects_duplicate_memory_context_in_same_flow", audit_duplicate)
for func_name in [
    "test_audit_check_fails_when_tool_error_occurs_inside_completed_flow",
    "test_audit_check_accepts_completed_managed_task_with_automatic_handoff",
    "test_audit_check_accepts_stage_specific_terminal_completion",
]:
    edit_function(
        "tests/test_audit.py",
        func_name,
        lambda block: block.replace('"memory_context"', '"project_status"', 1),
    )
replace_once("tests/test_audit.py", '    assert current.stat().st_size < 1400\n    assert previous.stat().st_size < 1400\n', '    assert current.stat().st_size < 2 * audit.MAX_AUDIT_BYTES\n    assert previous.stat().st_size < 2 * audit.MAX_AUDIT_BYTES\n')

edit_function(
    "tests/test_cli.py",
    "test_audit_check_cli_validates_latest_completed_flow",
    lambda block: block.replace('"memory_context"', '"project_status"', 1).replace('    assert payload["memory_context_calls"] == 1\n', '    assert payload["flow_start_tool"] == "project_status"\n    assert payload["project_status_calls"] == 1\n    assert payload["memory_context_calls"] == 0\n'),
)

print("repository hygiene cleanup applied")
