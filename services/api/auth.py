"""API keys and the request principal.

Three kinds:
  org    read/write within its own org, plus read of shared public-feed candidates
  demo   one org, read-only (GET; plus POST /evidence/{id}/verify, which writes nothing)
  admin  platform reset / seed / stream mode only. Holds NO org: through the normal routes it can read nothing.

A key is `qcc_<kind>_<43 url-safe chars>` (256 random bits). Only its SHA-256 is stored, so a database leak
yields no usable key; a fast hash is right here because the input is high-entropy, not a password. The token
is printed once at creation and never logged.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa

KeyKind = Literal["org", "demo", "admin"]
HEADER = "X-API-Key"
CACHE_TTL_S = 30.0  # a revoked key stops working within this window


@dataclass(frozen=True)
class Principal:
    key_id: int
    kind: KeyKind
    org_id: int | None
    org_slug: str | None


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_key(kind: KeyKind) -> str:
    return f"qcc_{kind}_{secrets.token_urlsafe(32)}"


def create_key(c: sa.Connection, kind: KeyKind, org_slug: str | None, label: str | None = None) -> str:
    """Returns the plaintext token (the only time it exists). Privileged connection."""
    if (kind == "admin") != (org_slug is None):
        raise ValueError("admin keys have no org; org and demo keys need one")
    org_id = None
    if org_slug is not None:
        org_id = c.execute(sa.text("select id from organisations where slug = :s"), {"s": org_slug}).scalar()
        if org_id is None:
            raise ValueError(f"unknown org {org_slug!r}")
    token = generate_key(kind)
    c.execute(sa.text("insert into api_keys (org_id, kind, key_hash, prefix, label) values (:o, :k, :h, :p, :l)"),
              {"o": org_id, "k": kind, "h": hash_key(token), "p": token[:12], "l": label})
    return token


_cache: dict[str, tuple[float, Principal]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def lookup(c: sa.Connection, token: str | None) -> Principal | None:
    """Privileged lookup, cached for CACHE_TTL_S (Supabase is ~100 ms per round trip; auth must not be)."""
    if not token or len(token) > 200:
        return None
    h = hash_key(token)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(h)
    if hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    r = c.execute(sa.text("""select k.id, k.kind, k.org_id, o.slug from api_keys k
                             left join organisations o on o.id = k.org_id
                             where k.key_hash = :h and k.revoked_at is null"""), {"h": h}).first()
    if r is None:
        return None  # negatives are not cached: a key created a moment ago must work at once
    p = Principal(r.id, r.kind, r.org_id, r.slug)
    with _lock:
        if len(_cache) > 10_000:
            _cache.clear()
        _cache[h] = (now, p)
    return p
