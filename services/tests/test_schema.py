import pytest
import json
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


def _domain(db, name):
    return db.execute(sa.text("insert into domains(name, etld1) values (:n, :n) returning id"), {"n": name}).scalar()


def test_confirmed_without_reasons_rejected(db):
    d = _domain(db, "a.top")
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into domain_verdicts(domain_id, status) values (:d, 'confirmed')"), {"d": d})


def test_confirmed_with_two_strong_accepted(db):
    d = _domain(db, "b.top")
    db.execute(sa.text(
        "insert into domain_verdicts(domain_id, status, confirm_reasons) values (:d, 'confirmed', "
        "'{\"signals\":[{\"name\":\"x\",\"strength\":\"strong\"},{\"name\":\"y\",\"strength\":\"strong\"}]}')"),
        {"d": d})


def test_shared_domains_table_carries_no_verdict(db):
    """Refinement: a shared candidate row must never reveal that a particular org confirmed it."""
    cols = set(db.execute(sa.text("select * from domains limit 0")).keys())
    assert not cols & {"status", "confirm_reasons", "confidence", "confirmed_at", "campaign_id", "verdict_at"}


def test_confirmed_on_one_strong_signal_rejected_by_db(db):
    """CLAUDE.md non-negotiable, enforced in code AND database: confirmed needs >= 2 strong signals."""
    reasons = ('{"signals":[{"name":"a","strength":"strong"},{"name":"b","strength":"moderate"},'
               '{"name":"c","strength":"moderate"},{"name":"d","strength":"moderate"}]}')
    d = _domain(db, "c.top")
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into domain_verdicts(domain_id, status, confirm_reasons) "
                           "values (:d, 'confirmed', cast(:r as jsonb))"), {"r": reasons, "d": d})


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


# ---- S3b in the database: the same independence rule as confirm.independent_strong ------------------------------
def _confirm(db, name, signals):
    d = _domain(db, name)
    db.execute(sa.text("insert into domain_verdicts(domain_id, status, confirm_reasons) "
                       "values (:d, 'confirmed', cast(:r as jsonb))"), {"d": d, "r": json.dumps({"signals": signals})})


def _s(name, *arts):
    return {"name": name, "strength": "strong", "detail": "x", "artifacts": list(arts)}


def test_db_rejects_two_strong_signals_on_one_artifact(db):
    """One POST to api.telegram.org seen by S1 and S2 is one piece of evidence: the database refuses to confirm."""
    with pytest.raises(sa.exc.IntegrityError):
        _confirm(db, "tg.top", [_s("credential_exfil_endpoint", "endpoint:telegram.org"),
                                _s("credential_post_foreign_origin_js", "endpoint:telegram.org")])


def test_db_rejects_two_instances_of_one_detector(db):
    with pytest.raises(sa.exc.IntegrityError):
        _confirm(db, "two.top", [_s("credential_exfil_endpoint", "endpoint:telegram.org"),
                                 _s("credential_exfil_endpoint", "endpoint:discord.com")])


def test_db_accepts_independent_strong_signals(db):
    _confirm(db, "ok.top", [_s("credential_exfil_endpoint", "endpoint:telegram.org"),
                            _s("credential_post_foreign_origin_js", "endpoint:telegram.org"),
                            _s("credential_post_foreign_origin_js", "endpoint:evil.top")])


def test_db_tolerates_a_non_array_artifacts_value(db):
    _confirm(db, "legacy.top", [{"name": "a", "strength": "strong", "artifacts": None},
                                {"name": "b", "strength": "strong"}])
