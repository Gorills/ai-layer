from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ai_layer.db.models import RuntimeEvent


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_timestamp(value: datetime | None) -> str | None:
    return utc_timestamp(value).isoformat() if value is not None else None


def public_activity_filters(filters: dict[str, Any]) -> dict[str, str | None]:
    return {
        key: (
            iso_timestamp(value)
            if isinstance(value, datetime)
            else str(value)
            if isinstance(value, UUID)
            else value
        )
        for key, value in filters.items()
    }


def activity_filter_fingerprint(filters: dict[str, Any]) -> str:
    raw = json.dumps(public_activity_filters(filters), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def encode_activity_cursor(event: RuntimeEvent, fingerprint: str) -> str:
    payload = {
        "v": 1,
        "occurred_at": iso_timestamp(event.created_at),
        "event_id": str(event.id),
        "filters": fingerprint,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def decode_activity_cursor(value: str, fingerprint: str) -> tuple[datetime, UUID]:
    if not value or len(value) > 1024:
        raise ValueError("cursor is invalid")
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "occurred_at",
            "event_id",
            "filters",
        }:
            raise ValueError
        canonical = (
            base64.urlsafe_b64encode(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            .decode("ascii")
            .rstrip("=")
        )
        if canonical != value:
            raise ValueError
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]))
        event_id = UUID(str(payload["event_id"]))
        if payload.get("v") != 1 or payload.get("filters") != fingerprint:
            raise ValueError
        if occurred_at.tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor is invalid or does not match the current filters") from exc
    return utc_timestamp(occurred_at), event_id
