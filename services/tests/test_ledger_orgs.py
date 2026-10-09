"""Every organisation signs on the ledger with its own account (spec 2026-10-09 §7). Runs on the TEST chain (:8546),
never the demo chain. The chain admin is Hardhat account #0 (public, demo chains only)."""
import dataclasses
import uuid

import pytest
import sqlalchemy as sa

from services.api import platform, seal

HARDHAT_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

pytestmark = [pytest.mark.db, pytest.mark.chain]


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(seal, "SETTINGS", dataclasses.replace(seal.SETTINGS, key_seal_secret="33" * 32))


def ledger_for(db):
    from services.api.ledger_service import Ledger
    from services.config import SETTINGS
    s = dataclasses.replace(SETTINGS, chain_rpc=SETTINGS.test_chain_rpc, chain_admin_private_key=HARDHAT_0)
    led = Ledger.from_settings(s, key_loader=lambda slug: platform.chain_key(db, slug))
    if not led.available():
        pytest.skip(f"no Hardhat test node at {SETTINGS.test_chain_rpc}")
    return led


def new_org(db, name="Telco Watch", slug=None):
    slug = slug or f"telco-{uuid.uuid4().hex[:8]}"
    db.execute(sa.text("insert into organisations (slug, name, category) values (:s, :n, 'telecom')"), {"s": slug, "n": name})
    return slug


def test_a_new_organisation_signs_on_the_chain_under_its_own_name(db):
    led = ledger_for(db)
    slug = new_org(db)
    assert platform.provision_chain(db, led, slug, "Telco Watch") == "registered"
    address, sealed = db.execute(sa.text("select chain_address, chain_key_sealed from organisations where slug = :s"),
                                 {"s": slug}).one()
    assert address.startswith("0x") and sealed is not None and led.is_registered(address)
    cid, kit, root = str(uuid.uuid4()), uuid.uuid4().hex * 2, uuid.uuid4().hex * 2
    led.publish_campaign(cid, root, kit, 60, 80, as_org=slug)
    assert led.find_by_kit(kit)[0]["reporter"]["name"] == "Telco Watch"


def test_registering_everyone_again_changes_nothing(db):
    led = ledger_for(db)
    slug = new_org(db)
    platform.provision_chain(db, led, slug, "Telco Watch")
    assert platform.register_all(db, led) == 0


def test_with_the_chain_down_the_account_waits_and_is_registered_later(db):
    led = ledger_for(db)
    slug = new_org(db)

    class Down:
        def available(self):
            return False

    assert platform.provision_chain(db, Down(), slug, "Telco Watch") == "pending"
    address = db.execute(sa.text("select chain_address from organisations where slug = :s"), {"s": slug}).scalar()
    assert not led.is_registered(address)
    assert platform.register_all(db, led) >= 1
    assert led.is_registered(address)
