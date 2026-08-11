from __future__ import annotations

from ai_layer.memory.presentation import is_continuation_intent

DECISION_DOMAIN_HINTS = (
    "architecture",
    "provider",
    "api",
    "contract",
    "migration",
    "schema",
    "concurrency",
    "security",
    "auth",
    "database",
    "persistence",
    "integration",
    "архитект",
    "провайдер",
    "api",
    "контракт",
    "миграц",
    "схем",
    "конкурент",
    "безопас",
    "авторизац",
    "баз",
    "персист",
    "интеграц",
)
DECISION_ACTION_HINTS = (
    "choose",
    "select",
    "decide",
    "design",
    "redesign",
    "replace",
    "introduce",
    "tradeoff",
    "alternative",
    "approach",
    "new architecture",
    "выбер",
    "реши",
    "спроектир",
    "перепроектир",
    "замен",
    "введ",
    "вариант",
    "альтернатив",
    "подход",
    "новую архитект",
)


def should_recommend_decision_search(task: str) -> bool:
    low = task.casefold()
    return any(hint in low for hint in DECISION_DOMAIN_HINTS) and any(
        hint in low for hint in DECISION_ACTION_HINTS
    )


def build_tool_guidance(task: str, project_root: str, memory: list[dict]) -> dict:
    """Only task-specific follow-up hints. Static workflow invariants live in the native bootstrap."""
    continuation = is_continuation_intent(task)
    calls: list[dict] = []
    if continuation:
        calls.append(
            {
                "tool": "session_restore",
                "when": "continuation depends on prior work",
                "args": {"session_id": "latest", "project_root": project_root},
            }
        )
    if should_recommend_decision_search(task):
        calls.append(
            {
                "tool": "decision_search",
                "required": True,
                "when": "before a consequential design choice among plausible alternatives",
                "args": {"query": task[:240], "project_root": project_root},
            }
        )
    top_score = max((float(item.get("score", 0.0)) for item in memory), default=0.0)
    if not continuation and (not memory or top_score < 0.35):
        calls.append(
            {
                "tool": "memory_search",
                "when": "one concrete reviewed project fact is still missing",
                "args": {"query": task[:240], "project_root": project_root},
            }
        )
    return {
        "recommended_calls": calls[:2],
        "project_context": {"canonical_root": project_root},
    }
