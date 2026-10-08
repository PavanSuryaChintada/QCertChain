"""A transient DNS or connection blip while opening a database connection must not become a 500 on screen: one
retry, then a clear 503."""
import contextlib

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from services.api import deps


class _Conn:
    closed = False

    @contextlib.contextmanager
    def begin(self):
        yield

    def close(self):
        self.closed = True


class _Engine:
    def __init__(self, fail_times):
        self.fail_times, self.calls = fail_times, 0

    def connect(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise sa.exc.OperationalError("connect", {}, Exception("getaddrinfo failed"))
        return _Conn()


@pytest.fixture(autouse=True)
def _db_configured(monkeypatch):
    import dataclasses
    monkeypatch.setattr(deps, "SETTINGS", dataclasses.replace(deps.SETTINGS, database_url="postgresql://x/y"))
    monkeypatch.setattr(deps.time, "sleep", lambda s: None)


def test_one_transient_failure_is_retried(monkeypatch):
    eng = _Engine(fail_times=1)
    monkeypatch.setattr(deps, "engine", lambda: eng)
    gen = deps.get_conn()
    conn = next(gen)
    assert isinstance(conn, _Conn) and eng.calls == 2
    with pytest.raises(StopIteration):
        next(gen)
    assert conn.closed


def test_a_persistent_failure_is_a_clear_503_not_a_500(monkeypatch):
    monkeypatch.setattr(deps, "engine", lambda: _Engine(fail_times=5))
    with pytest.raises(HTTPException) as e:
        next(deps.get_conn())
    assert e.value.status_code == 503 and "unreachable" in e.value.detail
