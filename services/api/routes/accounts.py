"""Sign-in routes (spec 2026-10-09 §4). Keyless by design, and only these two: the super admin's password login and
the public organisation list, which shows read-only (demo) keys only. Password guessing is throttled per client and
overall BEFORE any password check (argon2 is deliberately slow)."""
from __future__ import annotations

import nacl.exceptions
import nacl.pwhash
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from services.api import auth
from services.api.deps import get_conn, get_redis
from services.api.repos import platform as repo

router = APIRouter()  # no key

SESSION_S = 12 * 3600
PER_CLIENT, OVERALL, WINDOW_S = 5, 30, 60


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return nacl.pwhash.verify(password_hash.encode("utf-8"), password.encode("utf-8"))
    except (nacl.exceptions.InvalidkeyError, ValueError):
        return False


def _client(request: Request) -> str:
    # Behind the tunnel every request arrives from 127.0.0.1; Cloudflare names the real client. The API listens on
    # 127.0.0.1 only, so nothing but the tunnel and this machine can set the header.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def _check_and_issue(c, email: str, password: str) -> dict | None:
    h = repo.super_admin_hash(c, email)
    if h is None or not verify_password(h, password):
        return None
    token = auth.create_key(c, "superadmin", None, label=f"session {email.lower()}", expires_s=SESSION_S)
    return {"token": token, "expires_at": repo.key_expiry(c, token).isoformat()}


@router.post("/auth/superadmin/login")
async def login(body: LoginIn, request: Request, c=Depends(get_conn), r=Depends(get_redis)):
    per, total = f"login:fail:{_client(request)}", "login:fail:all"
    try:
        n_per, n_total = [int(x or 0) for x in await r.mget(per, total)]
    except Exception:  # fail closed: without the throttle, the password endpoint is not offered
        raise HTTPException(503, "Sign-in is unavailable right now. Retry in a few seconds.") from None
    if n_per >= PER_CLIENT or n_total >= OVERALL:
        retry = max(1, await r.ttl(per if n_per >= PER_CLIENT else total))
        raise HTTPException(429, f"Too many failed sign-ins. Retry in {retry} s.", headers={"Retry-After": str(retry)})
    out = await run_in_threadpool(_check_and_issue, c, body.email.strip(), body.password)
    if out is None:
        for k in (per, total):
            if await r.incr(k) == 1:
                await r.expire(k, WINDOW_S)
        raise HTTPException(401, "Wrong email or password.")
    return out


@router.get("/orgs/public")
def public_orgs(c=Depends(get_conn)) -> list[dict]:
    return repo.public_orgs(c)
