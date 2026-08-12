from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.domain.agents import AgentRequirement

POLICY_SCHEMA = 1
TIERS = ("economy", "balanced", "strong")
COST_POLICIES = {"economy", "balanced", "quality"}
OWNED_MARKER = "<!-- AI_LAYER_MANAGED_AGENT_PROFILE -->"

DEFAULT_CURSOR_MODELS: dict[str, str] = {
    # Managed workflows may explicitly request a cheap worker. Balanced/strong inherit the
    # host/operator model by default instead of pretending that two identical profiles form a cost tier.
    "economy": "composer-2.5[fast=false]",
    "balanced": "inherit",
    "strong": "inherit",
}
DEFAULT_POLICY: dict[str, object] = {
    "schema": POLICY_SCHEMA,
    "default_cost_policy": "economy",
    "cursor_models": DEFAULT_CURSOR_MODELS,
}


def policy_path() -> Path:
    return get_settings().home / "agent-policy.json"


def ensure_policy_file() -> Path:
    path = policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(
        json.dumps(DEFAULT_POLICY, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_policy() -> dict:
    path = policy_path()
    if not path.exists():
        return dict(DEFAULT_POLICY)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return dict(DEFAULT_POLICY)
    result = dict(DEFAULT_POLICY)
    if isinstance(raw, dict):
        if str(raw.get("default_cost_policy") or "") in COST_POLICIES:
            result["default_cost_policy"] = raw["default_cost_policy"]
        models = raw.get("cursor_models")
        if isinstance(models, dict):
            result["cursor_models"] = {
                tier: str(models.get(tier) or DEFAULT_CURSOR_MODELS[tier]) for tier in TIERS
            }
    return result


def save_policy(policy: dict) -> Path:
    path = policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    default_cost_policy = str(policy.get("default_cost_policy") or "economy")
    raw_models = policy.get("cursor_models")
    configured_models = raw_models if isinstance(raw_models, dict) else {}
    cursor_models: dict[str, str] = {
        tier: str(configured_models.get(tier) or DEFAULT_CURSOR_MODELS[tier]) for tier in TIERS
    }
    if default_cost_policy not in COST_POLICIES:
        raise ValueError("default_cost_policy must be economy|balanced|quality")
    for tier, model in cursor_models.items():
        if not model.strip():
            raise ValueError(f"Cursor model for {tier} must not be empty")
    normalized = {
        "schema": POLICY_SCHEMA,
        "default_cost_policy": default_cost_policy,
        "cursor_models": cursor_models,
    }
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return path


def configure_policy(
    *,
    economy_model: str | None = None,
    balanced_model: str | None = None,
    strong_model: str | None = None,
    default_cost_policy: str | None = None,
) -> dict:
    current = load_policy()
    models = dict(current.get("cursor_models") or {})
    updates = {
        "economy": economy_model,
        "balanced": balanced_model,
        "strong": strong_model,
    }
    for tier, value in updates.items():
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError(f"{tier}_model must not be empty")
            models[tier] = value
    cost = (default_cost_policy or current.get("default_cost_policy") or "economy").strip().lower()
    if cost not in COST_POLICIES:
        raise ValueError("default_cost_policy must be economy|balanced|quality")
    payload = {"schema": POLICY_SCHEMA, "default_cost_policy": cost, "cursor_models": models}
    path = save_policy(payload)
    return {"path": str(path), **load_policy()}


def build_agent_requirement(
    *,
    stage_kind: str,
    workflow_profile: str,
    risk_level: str,
    complexity_level: str,
    uncertainty_level: str,
    cost_policy: str,
) -> AgentRequirement:
    risk = risk_level if risk_level in {"low", "normal", "high"} else "normal"
    complexity = complexity_level if complexity_level in {"low", "normal", "high"} else "normal"
    uncertainty = uncertainty_level if uncertainty_level in {"low", "normal", "high"} else "normal"
    preference = cost_policy if cost_policy in COST_POLICIES else "economy"
    readonly = stage_kind in {"review", "discovery"}
    role = {
        "implement": "implementer",
        "review": "reviewer",
        "fix": "fixer",
        "discovery": "discovery",
    }.get(stage_kind, stage_kind)
    minimum = (
        "advanced"
        if "high" in {risk, complexity, uncertainty}
        else ("standard" if "normal" in {risk, complexity, uncertainty} else "basic")
    )
    context = (
        "deep"
        if complexity == "high" or uncertainty == "high"
        else ("normal" if complexity == "normal" else "focused")
    )
    isolation = "read_only_workspace" if readonly else "managed_repository_write"
    reason = f"{role}: risk={risk}, complexity={complexity}, uncertainty={uncertainty}, preference={preference}"
    return AgentRequirement(
        role=role,
        minimum_capability=minimum,
        risk=risk,
        complexity=complexity,
        uncertainty=uncertainty,
        context_requirement=context,
        readonly=readonly,
        isolation=isolation,
        quality_cost_preference=preference,
        reason=reason,
        metadata={"workflow_profile": workflow_profile},
    )


def requested_tier(
    *,
    stage_kind: str,
    workflow_profile: str,
    risk_level: str,
    complexity_level: str = "normal",
    uncertainty_level: str = "normal",
    cost_policy: str,
) -> tuple[str, str]:
    requirement = build_agent_requirement(
        stage_kind=stage_kind,
        workflow_profile=workflow_profile,
        risk_level=risk_level,
        complexity_level=complexity_level,
        uncertainty_level=uncertainty_level,
        cost_policy=cost_policy,
    )
    risk, complexity, uncertainty = (
        requirement.risk,
        requirement.complexity,
        requirement.uncertainty,
    )
    cost = requirement.quality_cost_preference
    if stage_kind in {"discovery", "review"}:
        tier = {"low": "economy", "normal": "balanced", "high": "strong"}[risk]
    elif stage_kind == "fix":
        tier = "balanced" if risk == "high" else "economy"
    elif workflow_profile == "micro":
        tier = "economy"
    else:
        tier = "balanced" if risk in {"normal", "high"} else "economy"
    if complexity == "high" or uncertainty == "high":
        tier = "balanced" if tier == "economy" else tier
    if risk == "high" and (complexity == "high" or uncertainty == "high"):
        tier = "strong"
    if cost == "balanced" and tier == "economy" and stage_kind != "fix":
        tier = "balanced"
    if cost == "quality":
        if stage_kind in {"review", "discovery"} or risk == "high" or complexity == "high":
            tier = "strong"
        elif tier == "economy":
            tier = "balanced"
    return tier, requirement.reason


def agent_profile(*, tier: str, readonly: bool) -> str:
    suffix = "readonly" if readonly else "write"
    return f"ai-layer-{tier}-{suffix}"


def stage_policy(
    *,
    stage_kind: str,
    workflow_profile: str,
    risk_level: str,
    complexity_level: str = "normal",
    uncertainty_level: str = "normal",
    cost_policy: str,
) -> dict:
    requirement = build_agent_requirement(
        stage_kind=stage_kind,
        workflow_profile=workflow_profile,
        risk_level=risk_level,
        complexity_level=complexity_level,
        uncertainty_level=uncertainty_level,
        cost_policy=cost_policy,
    )
    tier, reason = requested_tier(
        stage_kind=stage_kind,
        workflow_profile=workflow_profile,
        risk_level=risk_level,
        complexity_level=complexity_level,
        uncertainty_level=uncertainty_level,
        cost_policy=cost_policy,
    )
    policy = load_policy()
    requested_model = str((policy.get("cursor_models") or {}).get(tier) or "inherit")
    return {
        "requirement": requirement.to_dict(),
        "tier": tier,
        "profile": agent_profile(tier=tier, readonly=requirement.readonly),
        "readonly": requirement.readonly,
        "reason": reason,
        "cursor_model": requested_model,
        "selection_owner": "managed-workflow-policy",
        "host_native_outside_managed_workflow": True,
        "actual_model_assurance": "requested_unverified",
        "economic_effect_verified": False,
    }


def _profile_text(*, tier: str, readonly: bool, model: str) -> str:
    name = agent_profile(tier=tier, readonly=readonly)
    mode = (
        "read-only discovery/review"
        if readonly
        else "repository-writing implementation/remediation"
    )
    mutation_contract = (
        "You are READ-ONLY. Never edit repository files or perform consequential external mutations. "
        if readonly
        else "You are the delegated WRITABLE stage worker. Repository mutations required by the assigned IMPLEMENT/FIX stage belong to you, not the parent orchestrator. "
    )
    return (
        "---\n"
        f"name: {name}\n"
        f"description: AI Layer managed {mode} worker. Use only when task_next explicitly requests this profile.\n"
        f"model: {model}\n"
        f"readonly: {'true' if readonly else 'false'}\n"
        "---\n\n"
        f"{OWNED_MARKER}\n"
        "CRITICAL ROLE CONTRACT: You are a delegated AI Layer stage worker, never the top-level orchestrator. "
        + mutation_contract
        + "Follow the supplied delegation contract exactly. Do not mutate managed Task state, do not broaden scope, "
        "and return actual stage evidence/results to the orchestrator. If blocked, return the blocker; never ask or rely on the parent orchestrator to perform your stage work.\n"
    )


def install_cursor_profiles(home: Path | None = None) -> dict:
    ensure_policy_file()
    base = (home or Path.home()) / ".cursor" / "agents"
    base.mkdir(parents=True, exist_ok=True)
    policy = load_policy()
    written: list[str] = []
    skipped: list[str] = []
    for tier in TIERS:
        model = str((policy.get("cursor_models") or {}).get(tier) or "inherit")
        for readonly in (True, False):
            name = agent_profile(tier=tier, readonly=readonly)
            path = base / f"{name}.md"
            if path.exists():
                existing = path.read_text(encoding="utf-8", errors="replace")
                if OWNED_MARKER not in existing:
                    skipped.append(str(path))
                    continue
            path.write_text(
                _profile_text(tier=tier, readonly=readonly, model=model), encoding="utf-8"
            )
            written.append(str(path))
    return {"written": written, "skipped_unmanaged": skipped, "restart_may_be_required": True}


def remove_cursor_profiles(home: Path | None = None) -> dict:
    base = (home or Path.home()) / ".cursor" / "agents"
    removed: list[str] = []
    if not base.exists():
        return {"removed": removed}
    for path in base.glob("ai-layer-*-*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if OWNED_MARKER in text:
            path.unlink(missing_ok=True)
            removed.append(str(path))
    return {"removed": removed}
