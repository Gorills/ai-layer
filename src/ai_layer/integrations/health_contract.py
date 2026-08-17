from __future__ import annotations

HEALTH_READY = "ready"
HEALTH_DEGRADED = "degraded"
HEALTH_NOT_INSTALLED = "not_installed"
STATUS_CONTRACT_VERSION = 2
RUNTIME_VERIFIED = "verified"
RUNTIME_UNVERIFIED = "unverified"
RUNTIME_BLOCKED = "blocked"
OPERATIONAL_CONFIGURED_UNVERIFIED = "configured_unverified"


def runtime_assurance(state: str, evidence: str, reason: str | None = None) -> dict:
    return {"state": state, "evidence": evidence, "reason": reason}


def operational_status(health: str, assurance: dict) -> str:
    if health == HEALTH_NOT_INSTALLED:
        return HEALTH_NOT_INSTALLED
    if health != HEALTH_READY or assurance.get("state") == RUNTIME_BLOCKED:
        return HEALTH_DEGRADED
    if assurance.get("state") == RUNTIME_UNVERIFIED:
        return OPERATIONAL_CONFIGURED_UNVERIFIED
    return HEALTH_READY


def apply_status_contract(state: dict, *, health: str, runtime_assurance: dict) -> dict:
    configuration_ready = health == HEALTH_READY
    state["status_contract_version"] = STATUS_CONTRACT_VERSION
    state["status"] = health
    state["configuration_ready"] = configuration_ready
    state["ready"] = configuration_ready
    state["ready_semantics"] = "configuration"
    state["runtime_assurance"] = runtime_assurance
    state["operational_status"] = operational_status(health, runtime_assurance)
    return state


def _presence(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return bool(value.get("ready"))
    return bool(value)


def provider_install_status(*parts: object) -> str:
    present = [_presence(part) for part in parts]
    if present and all(present):
        return HEALTH_READY
    if any(present):
        return HEALTH_DEGRADED
    return HEALTH_NOT_INSTALLED
