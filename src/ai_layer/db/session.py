from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.core.config import get_settings
from ai_layer.core.request_context import interactive_request

_engine = None
_SessionLocal = None
_ENGINE_LOCK = threading.Lock()
_CIRCUIT_LOCK = threading.Lock()
_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_LAST_ERROR: str | None = None
INTERACTIVE_CONNECT_TIMEOUT_SECONDS = 2
INTERACTIVE_POOL_TIMEOUT_SECONDS = 2
INTERACTIVE_STATEMENT_TIMEOUT_MS = 5_000
CIRCUIT_BREAK_SECONDS = 5.0


def _engine_options(database_url: str) -> dict:
    options: dict = {"pool_pre_ping": True, "pool_timeout": INTERACTIVE_POOL_TIMEOUT_SECONDS}
    try:
        url = make_url(database_url)
    except Exception:
        return options
    if url.drivername.startswith("postgresql"):
        options["connect_args"] = {"connect_timeout": INTERACTIVE_CONNECT_TIMEOUT_SECONDS}
    return options


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        with _ENGINE_LOCK:
            if _engine is None:
                settings = get_settings()
                engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
                session_factory = sessionmaker(bind=engine, expire_on_commit=False)
                _engine = engine
                _SessionLocal = session_factory
    return _engine


def _circuit_open() -> bool:
    with _CIRCUIT_LOCK:
        return time.monotonic() < _CIRCUIT_OPEN_UNTIL


def _trip_circuit(exc: Exception) -> None:
    global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_LAST_ERROR
    with _CIRCUIT_LOCK:
        _CIRCUIT_OPEN_UNTIL = time.monotonic() + CIRCUIT_BREAK_SECONDS
        _CIRCUIT_LAST_ERROR = f"{type(exc).__name__}: {exc}"[:300]


def _close_circuit() -> None:
    global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_LAST_ERROR
    with _CIRCUIT_LOCK:
        _CIRCUIT_OPEN_UNTIL = 0.0
        _CIRCUIT_LAST_ERROR = None


def database_circuit_status() -> dict:
    with _CIRCUIT_LOCK:
        remaining = max(0.0, _CIRCUIT_OPEN_UNTIL - time.monotonic())
        return {
            "open": remaining > 0,
            "retry_after_seconds": round(remaining, 2),
            "last_error": _CIRCUIT_LAST_ERROR,
        }


@contextmanager
def session_scope():
    get_engine()
    assert _SessionLocal is not None
    interactive = interactive_request()
    if interactive and _circuit_open():
        state = database_circuit_status()
        raise RuntimeError(
            "AI_LAYER_DATABASE_UNAVAILABLE: database circuit is open after a recent connection failure; "
            f"retry in {state['retry_after_seconds']}s."
        )
    db: Session = _SessionLocal()
    try:
        if interactive and db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text(f"SET LOCAL statement_timeout = '{INTERACTIVE_STATEMENT_TIMEOUT_MS}ms'"))
        yield db
        db.commit()
        if interactive:
            _close_circuit()
    except (OperationalError, DBAPIError) as exc:
        db.rollback()
        if interactive:
            _trip_circuit(exc)
        raise RuntimeError(f"AI_LAYER_DATABASE_UNAVAILABLE: {type(exc).__name__}: {exc}") from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def database_status() -> dict:
    if _circuit_open():
        return {"connected": False, "pgvector": False, "circuit": database_circuit_status()}
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            vector = False
            if engine.dialect.name == "postgresql":
                vector = bool(conn.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")))
            _close_circuit()
            return {
                "connected": True,
                "pgvector": vector if engine.dialect.name == "postgresql" else None,
                "circuit": database_circuit_status(),
            }
    except Exception as exc:
        _trip_circuit(exc)
        return {"connected": False, "pgvector": False, "error": str(exc), "circuit": database_circuit_status()}


def database_ready() -> bool:
    return bool(database_status()["connected"])
