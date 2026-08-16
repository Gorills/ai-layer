from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID


def wire_value(value: Any) -> Any:
    """Convert nested Pydantic models into JSON-native dict/list payloads."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return wire_value(dump(exclude_none=True))
    if isinstance(value, dict):
        return {key: wire_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [wire_value(item) for item in value]
    return value


def default_json(value):
    if isinstance(value, (datetime, UUID, Path)):
        return str(value)
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=default_json)
