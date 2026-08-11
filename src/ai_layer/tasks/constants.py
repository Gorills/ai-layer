from __future__ import annotations

from ai_layer.domain.workflow import STAGE_DEFINITIONS

OPEN_TASK_STATUSES = {"active", "blocked"}
MUTATING_STAGES = {kind for kind, item in STAGE_DEFINITIONS.items() if item.mutating}
READ_ONLY_STAGES = {kind for kind, item in STAGE_DEFINITIONS.items() if item.readonly}
TERMINAL_TASK_STATUSES = {"completed", "cancelled"}
TASK_STATE_SCHEMA = 6
MAX_AUTOMATIC_FIX_ROUNDS = 2
HUMAN_ATTENTION_PREFIX = "human_attention_required:"
MAX_CHANGE_PATHS = 200
MAX_STAGE_HISTORY = 40
MAX_FINDINGS = 100
MICRO_MAX_CHANGED_LINES = 12
INLINE_MICRO_WORKER_ID = "inline:orchestrator"
MAX_TASK_GOAL_CHARS = 8_000
MAX_TASK_LIST_ITEMS = 50
MAX_TASK_ITEM_CHARS = 2_000
MAX_STAGE_SUMMARY_CHARS = 8_000
MAX_STAGE_CHECKS = 50
MAX_STAGE_CHECK_CHARS = 2_000
MAX_EXTERNAL_ACTIONS = 50
MAX_EXTERNAL_TARGET_CHARS = 512
MAX_EXTERNAL_TEXT_CHARS = 2_000
MAX_FINDING_PATH_CHARS = 1_000
MAX_FINDING_TEXT_CHARS = 4_000
MAX_VERIFICATION_EVIDENCE_CHARS = 4_000
MAX_RESULT_DATA_BYTES = 64_000
MAX_WORKER_ID_CHARS = 128
DEFAULT_WORKER_LEASE_SECONDS = 4 * 60 * 60
MIN_WORKER_LEASE_SECONDS = 5 * 60
MAX_WORKER_LEASE_SECONDS = 24 * 60 * 60

HIGH_RISK_TERMS = {
    "security",
    "auth",
    "authentication",
    "authorization",
    "permission",
    "payment",
    "billing",
    "migration",
    "schema",
    "database",
    "data deletion",
    "delete data",
    "drop table",
    "destructive",
    "production",
    "deploy",
    "secret",
    "encryption",
    "concurrency",
    "locking",
    "storage",
    "webhook",
    "oauth",
    "безопас",
    "авториза",
    "аутенти",
    "платеж",
    "миграц",
    "схема базы",
    "база данных",
    "базы данных",
    "удаление данных",
    "удалить данные",
    "продакш",
    "боевой сервер",
    "деплой",
    "секрет",
}
DISCOVERY_TERMS = {
    "investigate",
    "analyse",
    "analyze",
    "audit",
    "review first",
    "study",
    "understand",
    "explore",
    "before implementing",
    "before implementation",
    "start with review",
    "first review",
    "research",
    "discovery",
    "изуч",
    "исслед",
    "разбер",
    "проанализ",
    "аудит",
    "ревью перед",
    "ревью текущ",
    "ревью проекта",
    "предварительное ревью",
    "перед реализац",
    "сначала ревью",
    "начать с ревью",
}
MUTATION_INTENT_TERMS = {
    "fix",
    "change",
    "implement",
    "add",
    "remove",
    "update",
    "refactor",
    "build",
    "create",
    "replace",
    "исправ",
    "помен",
    "измен",
    "реализ",
    "добав",
    "удал",
    "обнов",
    "рефактор",
    "созда",
    "замен",
}
MICRO_TERMS = {
    "one line",
    "single line",
    "tiny",
    "trivial",
    "typo",
    "small fix",
    "minor fix",
    "rename label",
    "copy change",
    "text change",
    "одну строк",
    "одна строк",
    "мелк",
    "опечат",
    "небольшое исправ",
    "поправить текст",
    "переименовать подпись",
}
SENSITIVE_PATH_TERMS = {
    "auth",
    "security",
    "permission",
    "payment",
    "billing",
    "migration",
    "migrations",
    "schema",
    "docker",
    "compose",
    "deploy",
    "production",
    "secret",
    "credential",
    "oauth",
    "webhook",
    "database",
    "storage",
}
FALLBACK_IGNORE_DIRS = {
    ".git",
    ".ai-layer",
    ".idea",
    ".vscode",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
REVIEW_VERDICT_ALIASES = {
    "pass": "pass",
    "passed": "pass",
    "ok": "pass",
    "approved": "pass",
    "changes_required": "changes_required",
    "changes-required": "changes_required",
    "changes requested": "changes_required",
    "changes_requested": "changes_required",
    "needs_changes": "changes_required",
    "needs-changes": "changes_required",
    "fail": "changes_required",
    "failed": "changes_required",
}
