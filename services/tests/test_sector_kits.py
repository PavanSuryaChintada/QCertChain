"""Each sector's seeded campaigns share one phishing kit, and no two sectors share one (owner request 2026-10-10: an
e-commerce organisation's demo campaign must not turn up in a bank's kit-hash lookup). Banking keeps its original
kit, so the reports already on the ledger stay findable."""
import pytest
import sqlalchemy as sa

from services.api.seed import kit_for, seed_campaign

SECTORS = ("banking", "fintech", "ecommerce", "government", "telecom", "brokerage", "insurance", "consumer")
BANKING_KIT = "c9c69097bd87d4386220b7fa449aa41de107113b93def97671fb14346883da73"  # on the demo ledger since 2026-10-08


def test_banking_keeps_the_kit_already_on_the_ledger():
    assert kit_for("banking") == BANKING_KIT


def test_no_two_sectors_share_a_kit():
    kits = {s: kit_for(s) for s in SECTORS}
    assert all(kits.values()) and len(set(kits.values())) == len(SECTORS), kits


@pytest.mark.db
def test_a_seeded_ecommerce_campaign_carries_the_ecommerce_kit_and_is_still_confirmed(db, tmp_path):
    cid = seed_campaign(db, label="shop-kit", domains=12, brands=["Flipkart"], evidence_dir=tmp_path)
    kit = db.execute(sa.text("select kit_hash from campaigns where id = :c"), {"c": cid}).scalar_one()
    assert kit == kit_for("ecommerce") != BANKING_KIT
    rows = db.execute(sa.text("select confirm_reasons from org_domains where source='seed'")).scalars().all()
    assert len(rows) == 12 and all(sum(s["strength"] == "strong" for s in r["signals"]) >= 2 for r in rows)
