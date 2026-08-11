from __future__ import annotations

import json

from ai_layer.agents.policy import COST_POLICIES, load_policy, stage_policy
from ai_layer.core.redaction import redact_secrets
from ai_layer.db.models import Project, Task, TaskStage
from ai_layer.tasks.constants import (
    DISCOVERY_TERMS,
    HIGH_RISK_TERMS,
    MAX_RESULT_DATA_BYTES,
    MAX_TASK_ITEM_CHARS,
    MAX_TASK_LIST_ITEMS,
    MICRO_TERMS,
    MUTATION_INTENT_TERMS,
)

COMPLEXITY_TERMS = {
    "architecture",
    "refactor",
    "migration",
    "integration",
    "concurrency",
    "distributed",
    "state machine",
    "workflow",
    "multiple modules",
    "cross-cutting",
    "архитектур",
    "рефактор",
    "миграц",
    "интеграц",
    "конкурент",
}
UNCERTAINTY_TERMS = {
    "investigate",
    "unknown",
    "unfamiliar",
    "root cause",
    "diagnose",
    "why",
    "discover",
    "uncertain",
    "legacy",
    "исслед",
    "неизвест",
    "причин",
    "диагност",
    "разобраться",
    "легаси",
}


def _task_text(goal: str, acceptance_criteria: list[str], constraints: list[str]) -> str:
    return " ".join([goal, *acceptance_criteria, *constraints]).casefold()


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _bounded_text(
    value: object, *, field: str, max_chars: int, required: bool = False, redact: bool = False
) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > max_chars:
        raise ValueError(f"{field} exceeds the {max_chars}-character limit.")
    return redact_secrets(text) if redact else text


def _bounded_text_list(
    values: list[str] | None,
    *,
    field: str,
    max_items: int = MAX_TASK_LIST_ITEMS,
    max_chars: int = MAX_TASK_ITEM_CHARS,
    redact: bool = False,
) -> list[str]:
    raw = list(values or [])
    if len(raw) > max_items:
        raise ValueError(f"{field} exceeds the {max_items}-item limit.")
    result: list[str] = []
    for index, value in enumerate(raw, start=1):
        text = _bounded_text(value, field=f"{field}[{index}]", max_chars=max_chars, redact=redact)
        if text:
            result.append(text)
    return result


def _redact_json_strings(value: object) -> object:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_redact_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json_strings(item) for key, item in value.items()}
    return value


def _bounded_result_data(value: dict | None) -> dict:
    payload = dict(value or {})
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("task stage result_data must be JSON-serializable.") from exc
    if len(encoded) > MAX_RESULT_DATA_BYTES:
        raise ValueError(f"task stage result_data exceeds the {MAX_RESULT_DATA_BYTES}-byte limit.")
    redacted = _redact_json_strings(payload)
    assert isinstance(redacted, dict)
    return redacted


def _classify_risk(
    *,
    text: str,
    fragility: str,
    explicit_micro: bool,
    requested: str,
    reasons: list[str],
) -> tuple[str, bool]:
    high_risk_domain = _contains_any(text, HIGH_RISK_TERMS)
    if requested != "auto":
        reasons.append(f"risk explicitly requested as {requested}")
        return requested, high_risk_domain
    if high_risk_domain:
        reasons.append("task touches a high-risk domain")
        return "high", True
    if fragility in {"medium", "high"}:
        reasons.append(f"project scanner reports {fragility} change fragility")
        return "normal", False
    if explicit_micro:
        reasons.append(
            "host selected micro; final repository delta must prove the low-risk micro envelope"
        )
        return "low", False
    if _contains_any(text, MICRO_TERMS) and fragility == "low":
        reasons.append("task wording identifies a localized low-risk micro correction")
        return "low", False
    return "normal", False


def _classify_complexity(
    *, text: str, acceptance_criteria: list[str], explicit_micro: bool, requested: str
) -> str:
    if requested != "auto":
        return requested
    if _contains_any(text, COMPLEXITY_TERMS) or len(acceptance_criteria) >= 6:
        return "high"
    if (explicit_micro or _contains_any(text, MICRO_TERMS)) and len(acceptance_criteria) <= 2:
        return "low"
    return "normal"


def _classify_uncertainty(
    *, text: str, fragility: str, explicit_micro: bool, has_discovery: bool, requested: str
) -> str:
    if requested != "auto":
        return requested
    if has_discovery or _contains_any(text, UNCERTAINTY_TERMS):
        return "high"
    if explicit_micro or (_contains_any(text, MICRO_TERMS) and fragility == "low"):
        return "low"
    return "normal"


def _select_workflow_profile(
    *,
    requested: str,
    text: str,
    has_discovery: bool,
    has_mutation: bool,
    risk_level: str,
    fragility: str,
) -> str:
    if requested != "auto":
        return requested
    if has_discovery and has_mutation:
        return "discovery_first"
    if has_discovery:
        return "analysis_only"
    if risk_level == "low" and fragility == "low" and _contains_any(text, MICRO_TERMS):
        return "micro"
    return "standard"


def _enforce_micro_eligibility(
    *,
    profile: str,
    risk_level: str,
    fragility: str,
    complexity_level: str,
    uncertainty_level: str,
    high_risk_domain: bool,
    reasons: list[str],
) -> tuple[str, str]:
    if profile != "micro":
        return profile, risk_level
    if high_risk_domain:
        reasons.append(
            "micro request escalated because high-risk domains require independent review"
        )
        return "standard", "high"
    if risk_level != "low":
        reasons.append("micro request escalated because risk is not low")
        return "standard", risk_level
    if fragility in {"medium", "high"}:
        reasons.append(f"micro request escalated because project fragility is {fragility}")
        return "standard", risk_level
    if complexity_level != "low":
        reasons.append("micro request escalated because complexity is not low")
        return "standard", risk_level
    if uncertainty_level != "low":
        reasons.append("micro request escalated because uncertainty is not low")
        return "standard", risk_level
    return profile, risk_level


def _classify_task(
    project: Project,
    *,
    goal: str,
    acceptance_criteria: list[str],
    constraints: list[str],
    workflow: str = "auto",
    risk: str = "auto",
    complexity: str = "auto",
    uncertainty: str = "auto",
    cost_policy: str = "auto",
) -> dict:
    workflow = (workflow or "auto").strip().lower().replace("-", "_")
    if workflow not in {"auto", "micro", "standard", "discovery_first", "analysis_only"}:
        raise ValueError(
            "task_create workflow must be auto|micro|standard|discovery_first|analysis_only."
        )
    risk = (risk or "auto").strip().lower()
    if risk not in {"auto", "low", "normal", "high"}:
        raise ValueError("task_create risk must be auto|low|normal|high.")
    complexity = (complexity or "auto").strip().lower()
    if complexity not in {"auto", "low", "normal", "high"}:
        raise ValueError("task_create complexity must be auto|low|normal|high.")
    uncertainty = (uncertainty or "auto").strip().lower()
    if uncertainty not in {"auto", "low", "normal", "high"}:
        raise ValueError("task_create uncertainty must be auto|low|normal|high.")
    requested_cost = (cost_policy or "auto").strip().lower()
    if requested_cost == "auto":
        cost_policy = str(load_policy().get("default_cost_policy") or "economy").strip().lower()
    else:
        cost_policy = requested_cost
    if cost_policy not in COST_POLICIES:
        raise ValueError("task_create cost_policy must be auto|economy|balanced|quality.")

    text = _task_text(goal, acceptance_criteria, constraints)
    legacy = dict((project.project_intelligence or {}).get("legacy") or {})
    fragility = str(legacy.get("level") or "unknown").lower()
    explicit_micro = workflow == "micro"
    reasons: list[str] = []
    risk_level, high_risk_domain = _classify_risk(
        text=text,
        fragility=fragility,
        explicit_micro=explicit_micro,
        requested=risk,
        reasons=reasons,
    )
    has_discovery = _contains_any(text, DISCOVERY_TERMS)
    has_mutation = _contains_any(text, MUTATION_INTENT_TERMS)
    complexity_level = _classify_complexity(
        text=text,
        acceptance_criteria=acceptance_criteria,
        explicit_micro=explicit_micro,
        requested=complexity,
    )
    uncertainty_level = _classify_uncertainty(
        text=text,
        fragility=fragility,
        explicit_micro=explicit_micro,
        has_discovery=has_discovery,
        requested=uncertainty,
    )
    profile = _select_workflow_profile(
        requested=workflow,
        text=text,
        has_discovery=has_discovery,
        has_mutation=has_mutation,
        risk_level=risk_level,
        fragility=fragility,
    )
    profile, risk_level = _enforce_micro_eligibility(
        profile=profile,
        risk_level=risk_level,
        fragility=fragility,
        complexity_level=complexity_level,
        uncertainty_level=uncertainty_level,
        high_risk_domain=high_risk_domain,
        reasons=reasons,
    )
    return {
        "workflow_version": 3,
        "workflow_profile": profile,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "complexity_level": complexity_level,
        "uncertainty_level": uncertainty_level,
        "cost_policy": cost_policy,
        "project_fragility": fragility,
    }


def _configure_stage_agent(task: Task, stage: TaskStage) -> None:
    policy = stage_policy(
        stage_kind=stage.kind,
        workflow_profile=task.workflow_profile or "standard",
        risk_level=task.risk_level or "normal",
        complexity_level=task.complexity_level or "normal",
        uncertainty_level=task.uncertainty_level or "normal",
        cost_policy=task.cost_policy or "economy",
    )
    stage.agent_tier = policy["tier"]
    stage.agent_profile = policy["profile"]
    stage.agent_model = policy["cursor_model"]
    stage.agent_policy_reason = policy["reason"]
    stage.readonly_required = bool(policy["readonly"])


def _stage_agent_policy(stage: TaskStage) -> dict:
    return {
        "tier": stage.agent_tier or None,
        "profile": stage.agent_profile or None,
        "reason": stage.agent_policy_reason or None,
        "readonly": bool(stage.readonly_required),
        "cursor_model": stage.agent_model or "inherit",
        "actual_model_assurance": "requested-only; host execution identity/model is not authenticated by MCP",
    }
