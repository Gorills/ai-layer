"""Compatibility facade for the observability API.

Storage/event mechanics live in ``events``; live state aggregation lives in ``snapshot``.
"""

from ai_layer.observability.events import event_path, emit_event, observed_operation, read_events
from ai_layer.observability.snapshot import observability_snapshot, resolve_registered_root

__all__ = [
    "emit_event",
    "event_path",
    "observability_snapshot",
    "observed_operation",
    "read_events",
    "resolve_registered_root",
]
