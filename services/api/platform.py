"""Giving a new organisation the full workflow (spec 2026-10-09 §6–§7): its own chain account now; its seeded
campaign in provision(). Org1 and org2 keep their chain keys in .env (Hardhat accounts #1 and #2)."""
from __future__ import annotations

from eth_account import Account

from services.api import seal
from services.api.repos import platform as repo


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
