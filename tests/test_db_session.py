import threading
import time

from ai_layer.db import session as db_session


def test_get_engine_initializes_single_pool_under_concurrency(monkeypatch):
    sentinel = object()
    calls = []

    class Settings:
        database_url = "sqlite:///:memory:"

    def fake_create_engine(*args, **kwargs):
        calls.append((args, kwargs))
        time.sleep(0.03)
        return sentinel

    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_SessionLocal", None)
    monkeypatch.setattr(db_session, "get_settings", lambda: Settings())
    monkeypatch.setattr(db_session, "create_engine", fake_create_engine)
    monkeypatch.setattr(db_session, "sessionmaker", lambda **kwargs: ("factory", kwargs["bind"]))

    results = []
    errors = []

    def worker():
        try:
            results.append(db_session.get_engine())
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(calls) == 1
    assert results == [sentinel] * 12
    assert db_session._SessionLocal == ("factory", sentinel)
