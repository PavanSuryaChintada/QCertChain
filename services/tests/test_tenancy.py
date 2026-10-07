"""Tenant isolation. Two trust boundaries, both documented here in code:

  (a) ON CHAIN — public to every member, on purpose. Org 2 CAN see org 1's anchored campaign: its IOC root, kit
      hash, domain count, confidence, reporter and timestamp. Hashes and counts only. This is the consortium
      point: one org's detection protects the next without sharing its telemetry.
  (b) API / DATABASE — strictly org-scoped. Org 2 CANNOT read org 1's campaigns, campaign graph, domains,
      evidence, artifacts, reports, email analyses or takedown plans. A cross-org request is a 404, never a
      403: the response must not reveal that the resource exists.

Shared by design: public CT-feed candidates (each org sees its OWN verdict on them, never another org's).
"""
import uuid

import pytest
import sqlalchemy as sa

from services.api import repo
from services.api.db import set_org_context
from services.enrich.confirm import ConfirmResult, Signal
from services.ingest.triage import triage

SPOOF = open("services/email/samples/p01_display_spoof_dmarc_fail.eml", "rb").read()


@pytest.fixture
def org1_world(api, seeded, db):
    """Everything org 1 owns, created through org 1's own key."""
    graph = api.get(f"/campaigns/{seeded}/graph").json()
    domain_id = int(next(n["data"]["id"] for n in graph["elements"]["nodes"] if n["data"]["kind"] == "domain")[2:])
    detail = api.get(f"/domains/{domain_id}").json()
    bundle = detail["evidence_bundle_id"]
    art = api.get(f"/evidence/{bundle}").json()["artifacts"][0]["name"]
    plan = api.post(f"/campaigns/{seeded}/interdict", json={"k": 3, "backend": "greedy"}).json()["plan_id"]
    email = api.post("/email/analyze", json={"raw": SPOOF.decode(), "source": "analyst"}).json()["id"]
    return {"campaign": seeded, "domain": domain_id, "bundle": bundle, "artifact": art, "plan": plan, "email": email}


# ---- (b) API: org 2 gets 404 on every org-1 resource ------------------------------------------------------
@pytest.mark.db
def test_org2_cannot_read_any_org1_resource_and_gets_404_not_403(api, org1_world):
    w = org1_world
    org2 = api.as_("org2")
    reads = [f"/campaigns/{w['campaign']}", f"/campaigns/{w['campaign']}/graph", f"/domains/{w['domain']}",
             f"/evidence/{w['bundle']}", f"/evidence/{w['bundle']}/artifacts/{w['artifact']}",
             f"/evidence/{w['bundle']}/report", f"/email/analyses/{w['email']}", f"/plans/{w['plan']}"]
    for path in reads:
        assert api.get(path).status_code == 200, f"org1 must read its own {path}"
        r = api.get(path, headers=org2)
        assert r.status_code == 404, (path, r.status_code, r.text[:200])
    writes = [(f"/campaigns/{w['campaign']}/interdict", {"k": 2, "backend": "greedy"}),
              (f"/evidence/{w['bundle']}/verify", None), (f"/plans/{w['plan']}/benchmark", None),
              (f"/ledger/publish/{w['campaign']}", None), (f"/domains/{w['domain']}/confirm", None)]
    for path, body in writes:
        r = api.post(path, json=body, headers=org2)
        assert r.status_code == 404, (path, r.status_code, r.text[:200])


@pytest.mark.db
def test_org2_listings_contain_nothing_of_org1(api, org1_world):
    org2 = api.as_("org2")
    assert api.get("/campaigns", headers=org2).json()["total"] == 0
    assert api.get("/email/analyses", headers=org2).json()["total"] == 0
    names = {c["name"] for c in api.get("/candidates?limit=500", headers=org2).json()["items"]}
    assert not any(n.endswith(".example") for n in names), "org1's seeded (private) domains leaked"
    m = api.get("/metrics", headers=org2).json()
    assert m["campaigns_active"] == 0 and m["domains_confirmed"] == 0
    logs = api.get("/ops/log?limit=1000", headers=org2).json()["items"]
    assert not any(w in x["message"] for x in logs for w in ("seeded campaign", "email ", "plan ")), logs[:3]


@pytest.mark.db
def test_unknown_and_foreign_ids_are_indistinguishable(api, org1_world):
    """Same status and same body shape for 'exists in another org' and 'never existed'."""
    org2 = api.as_("org2")
    foreign = api.get(f"/campaigns/{org1_world['campaign']}", headers=org2)
    missing = api.get(f"/campaigns/{uuid.uuid4()}", headers=org2)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["title"] == missing.json()["title"]


# ---- shared by design: public candidates, each org's verdict separate ----------------------------------------
@pytest.mark.db
def test_org2_reads_shared_candidates_but_never_org1s_verdict_on_them(api, db):
    t = triage("sbi-kyc-verify-update.top")
    did, _ = repo.upsert_candidate(db, name="sbi-kyc-verify-update.top", etld1=t.etld1, cert_id=None, triage=t,
                                   source="certstream", ct_seen_at=None)  # public CT feed: origin_org_id null
    set_org_context(db, 1)
    strong = [Signal("credential_post_foreign_origin", "strong", "x"), Signal("kit_dom_hash_match", "strong", "y")]
    repo.set_confirmation(db, did, ConfirmResult("confirmed", 0.95, strong, 2))  # org1 confirms it

    own = {c["id"]: c for c in api.get("/candidates?limit=500").json()["items"]}
    other = {c["id"]: c for c in api.get("/candidates?limit=500", headers=api.as_("org2")).json()["items"]}
    assert own[did]["status"] == "confirmed"
    assert did in other, "shared public-feed candidate must be visible to org2"
    assert other[did]["status"] == "candidate" and other[did]["confidence"] is None, \
        "org2 must not learn that org1 confirmed this domain"
    shared_cols = set(db.execute(sa.text("select * from domains limit 0")).keys())
    assert not shared_cols & {"status", "confirm_reasons", "confidence", "campaign_id"}, shared_cols


# ---- (a) chain: public to every member, by design ----------------------------------------------------------
@pytest.mark.chain
@pytest.mark.db
def test_org2_sees_org1_anchored_hashes_on_chain_but_not_its_rows(api, seeded, db):
    from services.api import deps, main
    from services.api.workers.anchor_worker import process_due
    from services.tests.test_ledger import _real_ledger
    led = _real_ledger()
    main.app.dependency_overrides[deps.get_ledger] = lambda: led
    kit = api.get(f"/campaigns/{seeded}").json()["kit_hash"]
    assert api.post(f"/ledger/publish/{seeded}").status_code == 202  # org1 publishes (signs as org1)
    db.execute(sa.text("delete from anchor_queue where kind = 'evidence'"))
    assert process_due(db, led) == 1

    r = api.get(f"/ledger/by-kit/{kit}", headers=api.as_("org2"))
    assert r.status_code == 200
    rec = next(x for x in r.json()["campaigns"] if x["reporter"]["name"] == "Bank One SOC" and x["domain_count"] == 60)
    assert rec["yours"] is False and rec["campaign_id"] is None  # org2 gets the chain id, never org1's local id
    assert set(rec) >= {"chain_campaign_id", "ioc_root", "kit_hash", "domain_count", "confidence", "reporter"}
    assert not any(k in rec for k in ("domains", "names", "ips", "evidence")), "chain must carry no telemetry"
    assert api.get(f"/campaigns/{seeded}", headers=api.as_("org2")).status_code == 404  # but not the rows
    # and org2 can corroborate what it found, by chain id, signed as org2
    c = api.post(f"/ledger/corroborate/{rec['chain_campaign_id']}", headers=api.as_("org2"))
    assert c.status_code == 202 and c.json()["as_org"] == "org2"
