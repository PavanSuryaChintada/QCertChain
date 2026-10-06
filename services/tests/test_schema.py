import pytest
import sqlalchemy as sa

from scripts.apply_schema import apply
from services.tests.conftest import TEST_URL

pytestmark = pytest.mark.db


def test_all_tables_have_rls(db):
    rows = db.execute(sa.text(
        "select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relkind='r' and not c.relrowsecurity")).all()
    assert rows == []


def test_abuse_report_cannot_be_sent(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into abuse_reports(body, sent) values ('x', true)"))


def test_confirmed_without_reasons_rejected(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into domains(name, etld1, status) values ('a.top','a.top','confirmed')"))


def test_confirmed_with_two_strong_accepted(db):
    db.execute(sa.text(
        "insert into domains(name, etld1, status, confirm_reasons) values ('b.top','b.top','confirmed', "
        "'{\"signals\":[{\"name\":\"x\",\"strength\":\"strong\"},{\"name\":\"y\",\"strength\":\"strong\"}]}')"))


def test_confirmed_on_one_strong_signal_rejected_by_db(db):
    """CLAUDE.md non-negotiable, enforced in code AND database: confirmed needs >= 2 strong signals."""
    reasons = ('{"signals":[{"name":"a","strength":"strong"},{"name":"b","strength":"moderate"},'
               '{"name":"c","strength":"moderate"},{"name":"d","strength":"moderate"}]}')
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into domains(name, etld1, status, confirm_reasons) "
                           "values ('c.top','c.top','confirmed', cast(:r as jsonb))"), {"r": reasons})


def test_email_malicious_needs_two_strong(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into email_analyses(source, signals, strong_count, verdict) "
                           "values ('sample','[]',1,'malicious')"))


def test_registrar_node_kind_and_sources(db):
    db.execute(sa.text("insert into infra_nodes(kind, value) values ('registrar','Registrar A (seed)')"))
    for src in ("certstream", "replay", "seed", "email", "sample"):
        db.execute(sa.text("insert into domains(name, etld1, source) values (:n, :n, :s)"),
                   {"n": f"{src}.top", "s": src})


def test_certificate_fingerprint_unique(db):
    db.execute(sa.text("insert into certificates(fingerprint) values ('ab')"))
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into certificates(fingerprint) values ('ab')"))


def test_takedown_route_restricted(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into plan_targets(takedown_route) values ('ca')"))


def test_schema_is_idempotent(db_engine):
    apply(TEST_URL)
