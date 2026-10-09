"""Platform accounts (spec 2026-10-09 §3–§4): the super admin's login, organisations by category, their keys.
Privileged connection only, like repos/admin.py: these rows belong to the platform, not to an organisation."""
from __future__ import annotations

import sqlalchemy as sa

from services.api import auth, seal


def super_admin_hash(c: sa.Connection, email: str) -> str | None:
    return c.execute(sa.text("select password_hash from super_admins where lower(email) = lower(:e)"),
                     {"e": email}).scalar()


def key_expiry(c: sa.Connection, token: str):
    return c.execute(sa.text("select expires_at from api_keys where key_hash = :h"), {"h": auth.hash_key(token)}).scalar()


def revoke_key(c: sa.Connection, key_id: int) -> None:
    c.execute(sa.text("update api_keys set revoked_at = now() where id = :i"), {"i": key_id})


def _unseal(blob) -> str | None:
    if blob is None:
        return None
    try:
        return seal.unseal(blob)
    except Exception:  # a missing or wrong secret shows no key, never an error page
        return None


def public_orgs(c: sa.Connection) -> list[dict]:
    """Active organisations and their read-only key. Never an org, admin or session key."""
    rows = c.execute(sa.text("""
        select o.slug, o.name, o.category,
               (select k.token_sealed from api_keys k
                 where k.org_id = o.id and k.kind = 'demo' and k.revoked_at is null and k.token_sealed is not null
                 order by k.id desc limit 1) as sealed
        from organisations o where o.active order by o.category, o.name""")).all()
    return [{"slug": r.slug, "name": r.name, "category": r.category, "demo_key": _unseal(r.sealed)} for r in rows]


def list_orgs(c: sa.Connection) -> list[dict]:
    rows = c.execute(sa.text("""
        select o.slug, o.name, o.category, o.active, o.created_at, o.chain_address,
               (select count(*) from api_keys k where k.org_id = o.id and k.revoked_at is null) as live_keys,
               (select count(*) from campaigns x where x.org_id = o.id) as campaigns
        from organisations o order by o.id""")).all()
    return [{"slug": r.slug, "name": r.name, "category": r.category, "active": r.active,
             "created_at": r.created_at.isoformat() if r.created_at else None, "live_keys": r.live_keys,
             "campaigns": r.campaigns, "chain_address": r.chain_address} for r in rows]


def org(c: sa.Connection, slug: str):
    return c.execute(sa.text("""select id, slug, name, category, active, demo_brand, chain_address
                                from organisations where slug = :s"""), {"s": slug}).first()


def name_taken(c: sa.Connection, slug: str, name: str) -> bool:
    return c.execute(sa.text("select 1 from organisations where slug = :s or lower(name) = lower(:n)"),
                     {"s": slug, "n": name}).first() is not None


def insert_org(c: sa.Connection, slug: str, name: str, category: str, demo_brand: str | None = None) -> None:
    c.execute(sa.text("insert into organisations (slug, name, category, demo_brand) values (:s, :n, :c, :b)"),
              {"s": slug, "n": name, "c": category, "b": demo_brand})


def current_key(c: sa.Connection, org_id: int, kind: str) -> str | None:
    return _unseal(c.execute(sa.text("""select token_sealed from api_keys
                                        where org_id = :o and kind = :k and revoked_at is null
                                          and token_sealed is not null
                                        order by id desc limit 1"""), {"o": org_id, "k": kind}).scalar())


def revoke_kind(c: sa.Connection, org_id: int, kind: str) -> None:
    c.execute(sa.text("update api_keys set revoked_at = now() where org_id = :o and kind = :k and revoked_at is null"),
              {"o": org_id, "k": kind})


def deactivate(c: sa.Connection, org_id: int) -> None:
    c.execute(sa.text("update organisations set active = false where id = :o"), {"o": org_id})


def set_chain_account(c: sa.Connection, slug: str, address: str, sealed_key: bytes) -> None:
    c.execute(sa.text("update organisations set chain_address = :a, chain_key_sealed = :k where slug = :s"),
              {"a": address, "k": sealed_key, "s": slug})


def chain_key_sealed(c: sa.Connection, slug: str):
    return c.execute(sa.text("select chain_key_sealed from organisations where slug = :s and active"), {"s": slug}).scalar()


def chain_accounts(c: sa.Connection) -> list[tuple[str, str, str]]:
    """(slug, name, address) of every active organisation with its own chain account."""
    return [tuple(r) for r in c.execute(sa.text(
        "select slug, name, chain_address from organisations where active and chain_address is not null order by id")).all()]


def created_orgs(c: sa.Connection) -> list[tuple[int, str]]:
    """(id, slug) of every active organisation other than the two demo banks, oldest first."""
    return [tuple(r) for r in c.execute(sa.text(
        "select id, slug from organisations where active and slug not in ('org1', 'org2') order by id")).all()]
