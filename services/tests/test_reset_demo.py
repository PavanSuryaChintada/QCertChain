"""Item 9: "Reset demo" (admin) restores the known-good demo state in ONE transaction and touches nothing else."""
import pytest
import sqlalchemy as sa

from services.api import repo
from services.enrich.confirm import ConfirmResult, Signal
from services.ingest.triage import triage

pytestmark = pytest.mark.db


def _snapshot(api):
    out = {}
    for org in ("org1", "org2"):
        cs = api.get("/campaigns", headers=api.as_(org)).json()["items"]
        out[org] = sorted((c["label"], c["domain_count"], c["kit_hash"]) for c in cs)
    return out


def test_reset_restores_both_orgs_deterministically(api, db):
    admin = api.as_("admin")
    r1 = api.post("/admin/reset", headers=admin)
    assert r1.status_code == 200, r1.text
    first = _snapshot(api)
    assert [n for _, n, _ in first["org1"]] == [470] and [n for _, n, _ in first["org2"]] == [50]  # 400 + 40 tail + 30 unreachable
    assert first["org1"][0][2] == first["org2"][0][2]  # same kit: the consortium overlap is part of the demo state

    cid = api.get("/campaigns").json()["items"][0]["id"]
    api.post(f"/campaigns/{cid}/interdict", json={"k": 2})       # demo leaves traces
    api.post("/email/analyze", json={"raw": "From: a@b.example\n\nx", "source": "sample"})
    r2 = api.post("/admin/reset", headers=admin)
    assert r2.status_code == 200 and _snapshot(api) == first
    assert api.get("/email/analyses").json()["items"] == []
    assert not api.get("/campaigns").json()["items"][0]["has_plan"]
    assert r2.json()["removed"]["campaigns"] >= 2 and "org1" in r2.json()["seeded"]


def test_reset_keeps_live_ct_data_and_its_verdicts(api, db):
    t = triage("sbi-kyc-verify-update.top")
    did, _ = repo.upsert_candidate(db, name="sbi-kyc-verify-update.top", etld1=t.etld1, cert_id=None, triage=t,
                                   source="certstream", ct_seen_at=None)
    repo.set_confirmation(db, did, ConfirmResult("dismissed", 0.1, [Signal("x", "weak", "y")], 0))
    api.post("/admin/reset", headers=api.as_("admin"))
    assert db.execute(sa.text("select status from org_domains where id = :d"), {"d": did}).scalar() == "dismissed"


def test_only_the_admin_key_can_reset(api):
    for who in ("org1", "org2", "demo1"):
        assert api.post("/admin/reset", headers=api.as_(who)).status_code in (404, 405)


def test_reset_reseeds_every_organisation_the_super_admin_created(api, db):
    """Spec 2026-10-09 §6: reset restores each organisation's own seeded campaign, not only Bank One's and Two's."""
    from services.api import auth
    db.execute(sa.text("insert into organisations (slug, name, category) values ('telco-watch', 'Telco Watch', 'telecom')"))
    key = auth.create_key(db, "org", "telco-watch")
    assert api.post("/admin/reset", headers=api.as_("admin")).status_code == 200
    camps = api.get("/campaigns", headers={auth.HEADER: key}).json()["items"]
    assert len(camps) == 1 and "Jio" in camps[0]["brands"]
    assert api.post("/admin/reset", headers=api.as_("admin")).status_code == 200  # and again: still exactly one
    assert len(api.get("/campaigns", headers={auth.HEADER: key}).json()["items"]) == 1
