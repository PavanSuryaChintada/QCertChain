"""FastAPI dependencies. Tests override get_conn, get_redis, get_evidence_dir and get_signing_key.

Every route except /health resolves a Principal from the X-API-Key header BEFORE any query. Org routes then
receive a Scope: a connection already switched to role qcc_app with app.org_id set, so row-level security
filters every org-owned table. Route modules never see an unscoped connection (enforced by
services/tests/test_tenancy_static.py).
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

import redis.asyncio as aioredis
import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request

from services.api import auth
from services.api.db import bind_org, engine
from services.config import SETTINGS

READ_METHODS = ("GET", "HEAD", "OPTIONS")


def get_conn() -> Iterator[sa.Connection]:
    """PRIVILEGED transaction provider. Only auth, get_scope and admin routes may depend on it directly."""
    if not SETTINGS.database_url:
        raise HTTPException(503, "The database is not configured (DATABASE_URL).")
    with engine().begin() as c:
        yield c


def require_key_header(request: Request) -> None:
    """Runs before anything touches the database: a request with no key is 401 whatever else is down."""
    if not request.headers.get(auth.HEADER):
        raise HTTPException(401, "Missing or invalid API key (send it in the X-API-Key header).",
                            headers={"WWW-Authenticate": auth.HEADER})


def get_principal(request: Request, c: sa.Connection = Depends(get_conn)) -> auth.Principal:
    p = auth.lookup(c, request.headers.get(auth.HEADER))
    if p is None:
        raise HTTPException(401, "Missing or invalid API key (send it in the X-API-Key header).",
                            headers={"WWW-Authenticate": auth.HEADER})
    if p.kind == "demo" and request.method not in READ_METHODS:
        # The demo key is published for evaluators: it can read, and nothing else. 405 for every other verb.
        raise HTTPException(405, "This is a read-only demo key: only GET requests are allowed.",
                            headers={"Allow": "GET, HEAD"})
    return p


@dataclass(frozen=True)
class Scope:
    """Everything an org route may touch. `conn` is RLS-bound to `org_id`."""
    conn: sa.Connection
    org_id: int
    org_slug: str
    kind: auth.KeyKind


def get_scope(p: auth.Principal = Depends(get_principal), c: sa.Connection = Depends(get_conn)) -> Iterator[Scope]:
    if p.kind == "admin" or p.org_id is None:
        # The admin key holds no org: org data does not exist for it. 404, like any other unknown resource.
        raise HTTPException(404, "Not found")
    bind_org(c, p.org_id)  # reverts with the request's transaction (get_conn); nothing to undo here
    yield Scope(c, p.org_id, p.org_slug or "", p.kind)


def require_admin(p: auth.Principal = Depends(get_principal)) -> auth.Principal:
    if p.kind != "admin":
        raise HTTPException(404, "Not found")  # admin routes do not exist for org keys
    return p


@lru_cache(maxsize=1)
def _redis():
    return aioredis.from_url(SETTINGS.redis_url, decode_responses=True)


def get_redis():
    return _redis()


def get_evidence_dir() -> str:
    return SETTINGS.evidence_dir


def get_signing_key() -> str:
    return SETTINGS.collector_private_key


class UnavailableLedger:
    """Stand-in when the chain or its deployment file is missing: every read reports 'unavailable'."""

    def __init__(self, reason: str):
        self.reason = reason
        self.accounts: dict = {}

    def available(self) -> bool:
        return False


@lru_cache(maxsize=1)
def _ledger():
    from services.api.ledger_service import Ledger
    try:
        return Ledger.from_settings(SETTINGS)
    except Exception as e:  # missing deployments/abi: the API still serves everything else
        return UnavailableLedger(f"{type(e).__name__}: {e}")


def get_ledger():
    return _ledger()


async def rate_limit(p: auth.Principal = Depends(get_principal), r=Depends(get_redis)) -> None:
    """Fixed one-minute window per key, shared across API processes via Redis. If Redis is unreachable the
    request is allowed: a limiter outage must not take the API down."""
    limit = {"demo": SETTINGS.rate_limit_demo, "org": SETTINGS.rate_limit_org,
             "admin": SETTINGS.rate_limit_admin}[p.kind]
    now = time.time()
    key = f"ratelimit:key:{p.key_id}:{int(now // 60)}"
    try:
        n = await r.incr(key)
        if n == 1:
            await r.expire(key, 70)
    except Exception:
        return
    if n > limit:
        retry = max(1, int(60 - now % 60))
        raise HTTPException(429, f"Rate limit: {limit} requests per minute for a {p.kind} key. Retry in {retry} s.",
                            headers={"Retry-After": str(retry)})
