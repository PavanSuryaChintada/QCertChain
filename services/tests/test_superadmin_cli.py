"""`scripts.superadmin provision <slug>` re-runs a new organisation's setup (chain account and seeded campaign) when
the background run was lost, e.g. the API restarted mid-seed. No database: engine and ledger are stand-ins."""
from contextlib import contextmanager


def test_provision_command_reruns_setup_for_one_organisation(monkeypatch, capsys):
    from scripts import superadmin as script
    from services.api import db, deps, platform

    class Engine:
        @contextmanager
        def begin(self):
            yield "conn"

    calls = []
    monkeypatch.setattr(db, "engine", lambda: Engine())
    monkeypatch.setattr(deps, "get_ledger", lambda: "ledger")
    monkeypatch.setattr(platform, "provision",
                        lambda c, ledger, slug, **kw: calls.append((c, ledger, slug)) or
                        {"chain": "pending", "seeded": {"campaign_id": "c1"}})
    assert script.main(["superadmin", "provision", "amazon"]) == 0
    assert calls == [("conn", "ledger", "amazon")]
    assert "amazon: chain pending" in capsys.readouterr().out


def test_provision_command_needs_a_slug(monkeypatch):
    from scripts import superadmin as script
    from services.api import db

    class Engine:
        @contextmanager
        def begin(self):
            yield "conn"

    monkeypatch.setattr(db, "engine", lambda: Engine())
    assert script.main(["superadmin", "provision"]) == 2
