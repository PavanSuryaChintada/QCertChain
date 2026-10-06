"""Ledger: non-blocking anchor queue (unit, fake ledger), routes, and the real chain (needs a Hardhat node)."""
import uuid

import pytest
import sqlalchemy as sa

from services.api import repo
from services.api.workers.anchor_worker import process_due


class FakeLedger:
    def __init__(self, fail: Exception | None = None):
        self.fail, self.calls = fail, []

    def available(self):
        return self.fail is None

    def _go(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        if self.fail:
            raise self.fail
        return "0x" + "ab" * 32

    def anchor_evidence(self, *a, **kw):
        return self._go("anchor_evidence", *a, **kw)

    def publish_campaign(self, *a, **kw):
        return self._go("publish_campaign", *a, **kw)

    def attest(self, *a, **kw):
        return self._go("attest", *a, **kw)

    def corroborate(self, *a, **kw):
        return self._go("corroborate", *a, **kw)


@pytest.mark.db
def test_chain_down_keeps_item_queued_with_backoff(db):
    qid = repo.enqueue_anchor(db, "evidence", {"bundle_id": str(uuid.uuid4()), "bundle_root": "00" * 32, "campaign_id": None})
    n = process_due(db, FakeLedger(ConnectionError("connection refused")))
    row = db.execute(sa.text("select done, attempts, last_error, next_attempt_at > now() as later "
                             "from anchor_queue where id=:i"), {"i": qid}).one()
    assert n == 0 and not row.done and row.attempts == 1 and "refused" in row.last_error and row.later
    assert process_due(db, FakeLedger()) == 0  # not due yet: backoff respected


@pytest.mark.db
def test_success_marks_done_and_records_tx(db):
    camp = db.execute(sa.text("insert into campaigns (label, kit_hash, ioc_root, domain_count, confidence) "
                              "values ('CAMP-1', :k, :r, 3, 0.9) returning id::text"),
                      {"k": "aa" * 32, "r": "bb" * 32}).scalar()
    bid = db.execute(sa.text("insert into evidence_bundles (bundle_root, signature, collector_pk, artifact_dir) "
                             "values (:r, 's', 'pk', '/tmp') returning id::text"), {"r": "cc" * 32}).scalar()
    repo.enqueue_anchor(db, "evidence", {"bundle_id": bid, "bundle_root": "cc" * 32, "campaign_id": camp})
    repo.enqueue_anchor(db, "campaign", {"campaign_id": camp})
    led = FakeLedger()
    assert process_due(db, led) == 2
    assert db.execute(sa.text("select anchored_tx from evidence_bundles where id=:b"), {"b": bid}).scalar().startswith("0x")
    assert db.execute(sa.text("select published_tx from campaigns where id=:c"), {"c": camp}).scalar().startswith("0x")
    kinds = set(db.execute(sa.text("select kind from ledger_events")).scalars())
    assert kinds == {"evidence_anchored", "campaign_published"}
    assert [c[0] for c in led.calls] == ["anchor_evidence", "publish_campaign"]


@pytest.mark.db
def test_already_anchored_is_idempotent_success(db):
    class Already(Exception):
        pass
    repo.enqueue_anchor(db, "evidence", {"bundle_id": str(uuid.uuid4()), "bundle_root": "00" * 32, "campaign_id": None})
    assert process_due(db, FakeLedger(Already("execution reverted: AlreadyAnchored()"))) == 1
    assert db.execute(sa.text("select done from anchor_queue")).scalar() is True


# ---- routes -----------------------------------------------------------------------------------------
@pytest.fixture
def api_ledger(api):
    from services.api import deps, main
    led = FakeLedger()
    main.app.dependency_overrides[deps.get_ledger] = lambda: led
    api.fake_ledger = led
    return api


@pytest.mark.db
def test_publish_is_queued_not_blocking(api_ledger, seeded):
    r = api_ledger.post(f"/ledger/publish/{seeded}")
    assert r.status_code == 202 and r.json()["queued"] is True and r.json()["queue_position"] >= 1
    assert api_ledger.fake_ledger.calls == []  # nothing touched the chain inside the request


@pytest.mark.db
def test_attest_and_corroborate_validate_and_queue(api_ledger, seeded):
    assert api_ledger.post("/ledger/attest", json={"subject_hash": "0x" + "ab" * 32, "verdict": "disputed",
                                                    "as_org": "org2"}).status_code == 202
    assert api_ledger.post("/ledger/attest", json={"subject_hash": "nothex", "verdict": "disputed"}).status_code == 422
    assert api_ledger.post("/ledger/attest", json={"subject_hash": "0x" + "ab" * 32, "verdict": "maybe"}).status_code == 422
    assert api_ledger.post(f"/ledger/corroborate/{seeded}", json={"as_org": "org2"}).status_code == 202


@pytest.mark.db
def test_by_kit_chain_down_is_503_with_queue_depth(api, seeded, db):
    from services.api import deps, main
    main.app.dependency_overrides[deps.get_ledger] = lambda: FakeLedger(ConnectionError("down"))
    api.post(f"/ledger/publish/{seeded}")
    depth = db.execute(sa.text("select count(*) from anchor_queue where not done")).scalar()
    assert depth == 61  # 60 seeded evidence anchors + the campaign publish
    r = api.get("/ledger/by-kit/" + "aa" * 32)
    assert r.status_code == 503 and f"queued writes: {depth}" in r.json()["detail"]


# ---- real chain (Hardhat node + deployments/localhost.json) ------------------------------------------
def _real_ledger():
    from services.api.ledger_service import Ledger
    from services.config import SETTINGS
    led = Ledger.from_settings(SETTINGS)
    if not led.available():
        pytest.skip("no Hardhat node at CHAIN_RPC")
    return led


@pytest.mark.chain
def test_real_inheritance_by_kit_with_reporter_and_corroboration():
    led = _real_ledger()
    cid, kit, root = str(uuid.uuid4()), uuid.uuid4().hex * 2, uuid.uuid4().hex * 2
    tx = led.publish_campaign(cid, root, kit, 400, 94, as_org="org1")
    assert tx.startswith("0x")
    led.corroborate(cid, as_org="org2")
    found = led.find_by_kit(kit)
    assert len(found) == 1
    c = found[0]
    assert c["reporter"]["name"] == "Bank One SOC" and c["domain_count"] == 400 and c["confidence"] == 94
    assert c["ioc_root"] == root and c["tx_hash"] == tx
    assert [x["name"] for x in c["corroborations"]] == ["Bank Two SOC"]
    assert led.find_by_kit(uuid.uuid4().hex * 2) == []


@pytest.mark.chain
def test_real_anchor_verify_and_tamper():
    led = _real_ledger()
    bid, root = str(uuid.uuid4()), uuid.uuid4().hex * 2
    led.anchor_evidence(bid, root, None, as_org="org1")
    assert led.verify_anchor(bid, root) is True
    assert led.verify_anchor(bid, "00" * 32) is False
    with pytest.raises(Exception, match="AlreadyAnchored"):
        led.anchor_evidence(bid, root, None, as_org="org2")


@pytest.mark.chain
def test_real_dispute_attestation():
    led = _real_ledger()
    subject = uuid.uuid4().hex * 2
    led.attest(subject, "confirmed", as_org="org1")
    led.attest(subject, "disputed", as_org="org2")
    assert led.attestations(subject) == {"Bank One SOC": "confirmed", "Bank Two SOC": "disputed"}


@pytest.mark.chain
@pytest.mark.db
def test_end_to_end_org2_inherits_seeded_campaign_from_chain(api, seeded, db):
    """Seed -> publish (queued) -> anchor worker -> org2's inheritance query returns it with provenance."""
    from services.api import deps, main
    led = _real_ledger()
    main.app.dependency_overrides[deps.get_ledger] = lambda: led
    camp = api.get(f"/campaigns/{seeded}").json()
    assert api.post(f"/ledger/publish/{seeded}").status_code == 202
    db.execute(sa.text("delete from anchor_queue where kind = 'evidence'"))  # keep this test to the campaign write
    assert process_due(db, led) == 1
    r = api.get(f"/ledger/by-kit/{camp['kit_hash']}").json()
    mine = [x for x in r["campaigns"] if x["campaign_id"] == seeded]
    assert len(mine) == 1 and r["local_telemetry_received"] is False
    assert mine[0]["reporter"]["name"] == "Bank One SOC" and mine[0]["domain_count"] == 60
    assert api.get(f"/campaigns/{seeded}").json()["published_tx"] == mine[0]["tx_hash"]
