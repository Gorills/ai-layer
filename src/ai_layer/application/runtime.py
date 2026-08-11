"""Machine runtime queries exposed to transports without leaking persistence adapters."""

from ai_layer.db.session import database_status


def database_health() -> dict:
    return database_status()
