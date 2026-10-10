"""A connection that drops in the middle of an anchoring batch left the worker failing with "Can't reconnect until
invalid transaction is rolled back" on every loop until it was restarted (2026-10-10: anchoring stalled twice). After
a database error the worker now starts again from fresh connections, as a restart would. No database: stand-ins."""
from contextlib import contextmanager

import sqlalchemy.exc as sa_exc

from services.api.workers import anchor_worker


class Engine:
    def __init__(self, fail_times: int):
        self.fail_times, self.disposed, self.calls = fail_times, 0, 0

    @contextmanager
    def begin(self):
        self.calls += 1
        if self.calls <= self.fail_times and not self.disposed:
            raise sa_exc.PendingRollbackError("Can't reconnect until invalid transaction is rolled back", None, None)
        yield "conn"

    def dispose(self):
        self.disposed += 1


def test_after_a_database_error_the_next_loop_uses_fresh_connections(monkeypatch):
    eng = Engine(fail_times=1000)  # without a fresh pool it would never recover
    monkeypatch.setattr(anchor_worker, "engine", lambda: eng)
    monkeypatch.setattr(anchor_worker, "process_due", lambda c, ledger: 3)
    assert anchor_worker.run_once("ledger") == 0
    assert eng.disposed == 1
    assert anchor_worker.run_once("ledger") == 3


def test_a_good_loop_keeps_its_pool(monkeypatch):
    eng = Engine(fail_times=0)
    monkeypatch.setattr(anchor_worker, "engine", lambda: eng)
    monkeypatch.setattr(anchor_worker, "process_due", lambda c, ledger: 2)
    assert anchor_worker.run_once("ledger") == 2 and eng.disposed == 0
