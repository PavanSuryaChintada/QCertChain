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
        select o.slug, o.name, o.category, o.active, o.created_at,
               (select count(*) from api_keys k where k.org_id = o.id and k.revoked_at is null) as live_keys
        from organisations o order by o.id""")).all()
    return [{"slug": r.slug, "name": r.name, "category": r.category, "active": r.active,
             "created_at": r.created_at.isoformat() if r.created_at else None, "live_keys": r.live_keys} for r in rows]


def org(c: sa.Connection, slug: str):
    return c.execute(sa.text("select id, slug, name, category, active from organisations where slug = :s"),
                     {"s": slug}).first()


def name_taken(c: sa.Connection, slug: str, name: str) -> bool:
    return c.execute(sa.text("select 1 from organisations where slug = :s or lower(name) = lower(:n)"),
                     {"s": slug, "n": name}).first() is not None


def insert_org(c: sa.Connection, slug: str, name: str, category: str) -> None:
    c.execute(sa.text("insert into organisations (slug, name, category) values (:s, :n, :c)"),
              {"s": slug, "n": name, "c": category})


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
