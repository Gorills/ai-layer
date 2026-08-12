from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing expected fragment in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/ai_layer/mcp/context.py",
    '"Pass the exact canonical `project_root` returned by the relevant memory_context/task response. "\n                "Do not use shell cwd or bypass Task Layer."',
    '"Pass the exact canonical `project_root` returned by project_status or another successful "\n                "project-scoped AI Layer response. Do not use shell cwd or guess between projects."',
)
replace(
    "src/ai_layer/mcp/context.py",
    '"project_info/memory_context/task response. Do not derive it from MCP cwd and do not bypass Task Layer."',
    '"project_status/project_info or another successful project-scoped response. Do not derive it from MCP cwd."',
)
replace(
    "src/ai_layer/agents/policy.py",
    '"Follow the supplied delegation contract exactly. Do not mutate Task Layer state, do not broaden scope, "',
    '"Follow the supplied delegation contract exactly. Do not mutate managed Task state, do not broaden scope, "',
)
replace(
    "src/ai_layer/mcp/tools/tasks.py",
    '"""WHEN: substantive repository edits already happened outside Task Layer and must now be reviewed honestly.',
    '"""WHEN: substantive repository edits already happened outside a managed Task and the user/agent now explicitly wants AI Layer managed review/remediation.',
)
replace(
    "src/ai_layer/tasks/views.py",
    '"message": "Adopted unmanaged changes passed the managed review/remediation gates; original implementation was not claimed as Task Layer work.",',
    '"message": "Adopted unmanaged changes passed the managed review/remediation gates; original implementation was not claimed as managed Task implementation.",',
)
replace(
    "src/ai_layer/tasks/views.py",
    '''"next_action": {
                "action": "create_task",
                "message": "Create a task before implementation, review, debugging, or other substantive repository work.",
            },''',
    '''"next_action": {
                "action": "host_native",
                "tool": None,
                "message": (
                    "No managed Task is active. Ordinary repository work may continue through the host-native "
                    "agent runtime; create a Task only when durable or strict managed execution is useful."
                ),
                "managed_option": {"tool": "task_create", "required": ["goal"]},
            },''',
)
replace(
    "src/ai_layer/tasks/navigation.py",
    '"assurance": "current repository state exactly matches the last completed Task Layer terminal state",',
    '"assurance": "current repository state exactly matches the last completed managed Task terminal state",',
)
old_inactive = '''    message = "Create the managed task before substantive repository or external mutations."
    if preexisting:
        message = (
            f"Repository already has {int(preexisting.get('total') or 0)} pre-existing changed path(s). "
            "task_create is allowed: AI Layer will capture the exact current worktree as the immutable task baseline "
            "and measure only later managed changes against it. Use task_adopt only when the existing edits themselves "
            "are the implementation you want reviewed. Do not stash/reset/restore/commit merely to create the task."
        )
    payload = {
        **runtime,
        "state": "idle_with_preexisting_changes" if preexisting else runtime.get("state"),
        "project_root": str(root),
        "preexisting_changes": preexisting,
        "next_action": {
            "action": "create_task",
            "tool": "task_create",
            "required": ["goal"],
            "optional": ["acceptance_criteria", "constraints", "workflow", "risk", "cost_policy"],
            "forbidden": [
                "edit repository before task_create",
                "stash/reset/restore/commit solely to make the worktree clean for AI Layer",
            ],
            "alternative": (
                "Use task_adopt only if the pre-existing dirty changes are themselves the work for the intended task."
                if preexisting
                else None
            ),
            "message": message,
        },
    }'''
new_inactive = '''    if preexisting:
        message = (
            f"No managed Task is active and the repository already has {int(preexisting.get('total') or 0)} "
            "pre-existing changed path(s). Ordinary host-native work remains allowed. If strict/durable managed "
            "execution is explicitly useful, task_create can baseline the exact current worktree and measure only "
            "later managed changes; use task_adopt only when the existing edits themselves should enter managed "
            "review/remediation. Never stash/reset/restore/commit merely to satisfy AI Layer."
        )
    else:
        message = (
            "No managed Task is active. Continue ordinary work through the host-native agent runtime; create a "
            "managed Task only when durable state, strict review/remediation, or explicit user intent makes it useful."
        )
    payload = {
        **runtime,
        "state": "idle_with_preexisting_changes" if preexisting else runtime.get("state"),
        "project_root": str(root),
        "preexisting_changes": preexisting,
        "next_action": {
            "action": "host_native",
            "tool": None,
            "message": message,
            "managed_option": {
                "tool": "task_create",
                "required": ["goal"],
                "optional": ["acceptance_criteria", "constraints", "workflow", "risk", "cost_policy"],
            },
            "alternative": (
                "Use task_adopt only if the pre-existing dirty changes are themselves the work to review/manage."
                if preexisting
                else None
            ),
            "worktree_rule": "Do not stash/reset/restore/commit solely to satisfy AI Layer.",
        },
    }'''
replace("src/ai_layer/tasks/navigation.py", old_inactive, new_inactive)

replace(
    "src/ai_layer/integrations/global_install.py",
    'GLOBAL_BOOTSTRAP_VERSION = 13\n\n_ANSI_ESCAPE_RE',
    'GLOBAL_BOOTSTRAP_VERSION = 13\nGLOBAL_BOOTSTRAP_MARKER = f"<!-- AI-LAYER GLOBAL BOOTSTRAP v{GLOBAL_BOOTSTRAP_VERSION} -->"\n\n_ANSI_ESCAPE_RE',
)
replace(
    "src/ai_layer/integrations/global_install.py",
    '    workflow = _global_bootstrap_workflow()\n',
    '    workflow = GLOBAL_BOOTSTRAP_MARKER + "\\n" + _global_bootstrap_workflow()\n',
)
replace(
    "src/ai_layer/integrations/service.py",
    'from ai_layer.integrations.global_install import (\n    _cursor_plugin_owned,\n    _merge_codex_config,\n)',
    'from ai_layer.integrations.global_install import (\n    GLOBAL_BOOTSTRAP_MARKER,\n    _cursor_plugin_owned,\n    _merge_codex_config,\n)',
)
replace(
    "src/ai_layer/integrations/service.py",
    '        integration_template_version=INTEGRATION_TEMPLATE_VERSION,\n        project_integration_paths=PROJECT_INTEGRATION_PATHS,',
    '        integration_template_version=INTEGRATION_TEMPLATE_VERSION,\n        global_bootstrap_marker=GLOBAL_BOOTSTRAP_MARKER,\n        project_integration_paths=PROJECT_INTEGRATION_PATHS,',
)
replace(
    "src/ai_layer/integrations/status.py",
    '    integration_template_version: int\n    project_integration_paths: tuple[str, ...]',
    '    integration_template_version: int\n    global_bootstrap_marker: str\n    project_integration_paths: tuple[str, ...]',
)
replace(
    "src/ai_layer/integrations/status.py",
    '''def _bootstrap_file_status(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        return deps.managed_start in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
''',
    '''def _bootstrap_file_status(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
        return deps.managed_start in text and deps.global_bootstrap_marker in text
    except (OSError, UnicodeDecodeError):
        return False


def _bootstrap_version_current(path: Path, deps: IntegrationStatusDependencies) -> bool:
    if not path.exists():
        return False
    try:
        return deps.global_bootstrap_marker in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
''',
)
replace(
    "src/ai_layer/integrations/status.py",
    '''            "ready": deps.cursor_plugin_owned(plugin)
            and cursor_manifest.exists()
            and cursor_rule.exists(),''',
    '''            "ready": deps.cursor_plugin_owned(plugin)
            and cursor_manifest.exists()
            and _bootstrap_version_current(cursor_rule, deps),''',
)
