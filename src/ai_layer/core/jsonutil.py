from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID


def default_json(value):
    if isinstance(value, (datetime, UUID, Path)):
        return str(value)
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=default_json)
