"""Giving a new organisation the full workflow (spec 2026-10-09 §6–§7): its own chain account now; its seeded
campaign in provision(). Org1 and org2 keep their chain keys in .env (Hardhat accounts #1 and #2)."""
from __future__ import annotations

import threading
from functools import lru_cache


from eth_account import Account

from services.api import repo as core
from services.api import seal
from services.api.db import bind_org, unbind_org
from services.api.repos import admin as repo_admin
from services.api.repos import platform as repo
from services.config import SETTINGS


@lru_cache(maxsize=1)
def brand_sectors() -> dict[str, str]:
    """Brand name -> sector, from the brand list (the order of the file is kept)."""
    from services.ingest.brands import load_brands
    return {b.name: b.sector for b in load_brands(SETTINGS.brands_file).brands}


def default_brand(category: str) -> str | None:
    """The first brand of the sector in the brand list (an organisation in 'other' must name one)."""
    return next((name for name, sector in brand_sectors().items() if sector == category), None)


def seed_kwargs(slug: str, org_id: int, brand: str) -> dict:
    """A ~60-domain campaign imitating the brand. Documentation IPs offset per organisation (org1 uses 10+,
    org2 100+), so two organisations' demo infrastructure never looks shared by accident."""
    return dict(label=f"{slug}-kit", domains=60, ips=6, asns=2, nameservers=3, registrars=3, brands=[brand],
                ip_base=130 + (org_id * 6) % 110)


def seed_and_queue(c, org_id: int, slug: str, brand: str, *, evidence_dir, signing_key_hex: str) -> dict:
    out = repo_admin.seed(c, org=org_id, evidence_dir=evidence_dir, signing_key_hex=signing_key_hex,
                          **seed_kwargs(slug, org_id, brand))
    bind_org(c, org_id)
    try:  # published as this organisation, so another organisation's kit lookup finds it
        core.enqueue_anchor(c, "campaign", {"campaign_id": out["campaign_id"]})
    finally:
        unbind_org(c)
    return out


def provision(c, ledger, slug: str, *, evidence_dir, signing_key_hex: str) -> dict:
    """Everything a new organisation needs to work like Bank One: its chain account and a seeded campaign in its
    sector, queued for the ledger."""
    o = repo.org(c, slug)
    chain = "registered" if o.chain_address else provision_chain(c, ledger, slug, o.name)
    brand = o.demo_brand or default_brand(o.category)
    seeded = seed_and_queue(c, o.id, slug, brand, evidence_dir=evidence_dir, signing_key_hex=signing_key_hex) \
        if brand else None
    return {"chain": chain, "seeded": seeded}


def provision_in_background(slug: str) -> None:
    """Creation answers at once; seeding takes a while on a slow link. Its own connection and transaction; a
    failure is written to the ops log, never lost."""
    def run():
        from services.api.db import engine
        from services.api.deps import get_ledger
        try:
            with engine().begin() as c:
                provision(c, get_ledger(), slug, evidence_dir=SETTINGS.evidence_dir,
                          signing_key_hex=SETTINGS.collector_private_key)
        except Exception as e:  # noqa: BLE001
            try:
                with engine().begin() as c:
                    core.log(c, "platform", f"provisioning {slug} failed: {type(e).__name__}: {e}"[:500], severity=3)
            except Exception:  # noqa: BLE001 - the database itself is unreachable: nothing more to do here
                pass
    threading.Thread(target=run, name=f"provision-{slug}", daemon=True).start()


def chain_key(c, slug: str) -> str | None:
    blob = repo.chain_key_sealed(c, slug)
    if blob is None:
        return None
    try:
        return seal.unseal(blob)
    except Exception:  # a missing or wrong secret: no key, so the organisation cannot sign (reported upstream)
        return None


def provision_chain(c, ledger, slug: str, name: str) -> str:
    """Create, seal and store the organisation's signing account; fund and register it when the chain is up.
    Returns 'registered', 'pending' (chain down: `scripts.superadmin chain` registers it later) or 'none'
    (no KEY_SEAL_SECRET: the key could not be kept, so no account was made)."""
    acct = Account.create()
    sealed = seal.seal(acct.key.hex())
    if sealed is None:
        return "none"
    repo.set_chain_account(c, slug, acct.address, sealed)
    if not ledger.available():
        return "pending"
    try:
        ledger.register_org(acct.address, name)
    except Exception:  # noqa: BLE001 - the next `scripts.superadmin chain` retries
        return "pending"
    return "registered"


def register_all(c, ledger) -> int:
    """Register every active organisation's account that this chain does not know yet (a fresh demo chain forgets
    them). Returns how many were registered; 0 when all were already active."""
    n = 0
    for slug, name, address in repo.chain_accounts(c):
        if not ledger.is_registered(address):
            ledger.register_org(address, name)
            n += 1
    return n
