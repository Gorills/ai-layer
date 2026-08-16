from __future__ import annotations

from uuid import UUID

from ai_layer.core.redaction import redact_secrets
from ai_layer.db.work_models import WORK_ASSURANCE

WORK_PATH_LIMIT = 120
WORK_PATH_MAX_CHARS = 512
WORK_CHECK_LIMIT = 40
WORK_ASSURANCE_VALUES = frozenset(WORK_ASSURANCE)
WORK_CHECK_STATUSES = frozenset({"passed", "failed", "skipped", "blocked", "not_run"})
WORK_CHECK_FIELDS = frozenset({"name", "status", "summary"})
MAP_DISPOSITION_FIELDS = frozenset({"status", "scope", "scope_paths", "reason", "event_id"})
REPOSITORY_DELTA_FIELDS = frozenset(
    {
        "base_revision",
        "final_revision",
        "changed_files",
        "insertions",
        "deletions",
        "dirty",
        "assurance",
    }
)


def normalized_text(value: object, *, field: str, max_chars: int, required: bool = False) -> str:
    result = " ".join(str(value or "").strip().split())
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > max_chars:
        raise ValueError(f"{field} exceeds {max_chars} characters")
    return result


def safe_metadata_text(value: object, *, field: str, max_chars: int, required: bool = False) -> str:
    return redact_secrets(
        normalized_text(value, field=field, max_chars=max_chars, required=required)
    )


def project_paths(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > WORK_PATH_LIMIT:
        raise ValueError(f"{field} exceeds {WORK_PATH_LIMIT} paths")
    result: list[str] = []
    for raw in value:
        path = str(raw or "").strip().replace("\\", "/")
        if (
            not path
            or path.startswith("/")
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise ValueError(f"{field} contains a non-project-relative path")
        if len(path) > WORK_PATH_MAX_CHARS:
            raise ValueError(f"{field} contains a path exceeding {WORK_PATH_MAX_CHARS} characters")
        if path not in result:
            result.append(path)
    return result


def check_evidence(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("checks must be a list")
    if len(value) > WORK_CHECK_LIMIT:
        raise ValueError(f"checks exceeds {WORK_CHECK_LIMIT} items")
    result: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each check must be an object")
        unknown = sorted(set(item) - WORK_CHECK_FIELDS)
        if unknown:
            raise ValueError(f"checks contains unsupported fields: {', '.join(unknown)}")
        result.append(
            {
                "name": safe_metadata_text(
                    item.get("name"),
                    field="checks.name",
                    max_chars=240,
                    required=True,
                ),
                "status": _check_status(item.get("status")),
                "summary": safe_metadata_text(
                    item.get("summary"), field="checks.summary", max_chars=500
                ),
            }
        )
    return result


def _check_status(value: object) -> str:
    status = normalized_text(value, field="checks.status", max_chars=32, required=True).casefold()
    if status not in WORK_CHECK_STATUSES:
        allowed = ", ".join(sorted(WORK_CHECK_STATUSES))
        raise ValueError(f"checks.status must be one of: {allowed}")
    return status


def assurance_source(value: object) -> str:
    assurance = normalized_text(value, field="assurance", max_chars=32, required=True).casefold()
    if assurance not in WORK_ASSURANCE_VALUES:
        allowed = ", ".join(sorted(WORK_ASSURANCE_VALUES))
        raise ValueError(f"assurance must be one of: {allowed}")
    return assurance


def repository_delta(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("repository_delta must be an object")
    unknown = sorted(set(value) - REPOSITORY_DELTA_FIELDS)
    if unknown:
        raise ValueError(f"repository_delta contains unsupported fields: {', '.join(unknown)}")

    result: dict[str, object] = {}
    for field in ("base_revision", "final_revision"):
        if field in value:
            result[field] = safe_metadata_text(
                value[field], field=f"repository_delta.{field}", max_chars=128
            )
    for field in ("changed_files", "insertions", "deletions"):
        if field not in value:
            continue
        count = value[field]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"repository_delta.{field} must be a non-negative integer")
        result[field] = count
    if "dirty" in value:
        if not isinstance(value["dirty"], bool):
            raise ValueError("repository_delta.dirty must be a boolean")
        result["dirty"] = value["dirty"]
    if "assurance" in value:
        result["assurance"] = assurance_source(value["assurance"])
    return result


def _disposition_scope(value: dict) -> list[str]:
    raw_scope = value.get("scope")
    raw_alias = value.get("scope_paths")
    has_scope = raw_scope not in (None, [])
    has_alias = raw_alias not in (None, [])
    if has_scope and has_alias:
        scope = project_paths(raw_scope, field="map_disposition.scope")
        alias = project_paths(raw_alias, field="map_disposition.scope_paths")
        if scope != alias:
            raise ValueError("map_disposition.scope and map_disposition.scope_paths must match")
        return scope
    if has_alias:
        return project_paths(raw_alias, field="map_disposition.scope")
    return project_paths(raw_scope or [], field="map_disposition.scope")


def map_disposition(value: object) -> dict:
    if value is None:
        return {"status": "pending"}
    if not isinstance(value, dict):
        raise ValueError("map_disposition must be an object")
    unknown = sorted(set(value) - MAP_DISPOSITION_FIELDS)
    if unknown:
        raise ValueError(f"map_disposition contains unsupported fields: {', '.join(unknown)}")
    status = normalized_text(
        value.get("status"), field="map_disposition.status", max_chars=32, required=True
    )
    allowed = {"reconciled", "checked_no_change", "not_applicable", "deferred", "pending"}
    if status not in allowed:
        raise ValueError(
            "map_disposition.status must be reconciled, checked_no_change, not_applicable, deferred or pending"
        )
    scope = _disposition_scope(value)
    reason = safe_metadata_text(value.get("reason"), field="map_disposition.reason", max_chars=500)
    event_id = normalized_text(
        value.get("event_id"), field="map_disposition.event_id", max_chars=64
    )
    if status == "checked_no_change" and (not scope or not reason):
        raise ValueError(
            "checked_no_change requires map_disposition.scope and map_disposition.reason"
        )
    if status == "reconciled" and (not scope or not event_id):
        raise ValueError("reconciled requires map_disposition.scope and map_disposition.event_id")
    if status == "reconciled":
        try:
            UUID(event_id)
        except ValueError as exc:
            raise ValueError("reconciled map_disposition.event_id must be a UUID") from exc
    if status in {"not_applicable", "deferred"} and not reason:
        raise ValueError(f"{status} requires map_disposition.reason")
    return {"status": status, "scope": scope, "reason": reason, "event_id": event_id or None}
