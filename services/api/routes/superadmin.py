"""The super admin panel (spec 2026-10-09 §4): a super admin session only; for every other key these routes do
not exist (404), like the admin routes. It manages organisations, their categories and keys; it reads no
organisation-owned data. Privileged connection by design (tests/test_tenancy_static.py allows exactly this)."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from services.api import auth
from services.api.deps import get_conn, require_superadmin
from services.api.repos import platform as repo
from services.config import SETTINGS

router = APIRouter(prefix="/superadmin", dependencies=[Depends(require_superadmin)])
sessions = APIRouter(dependencies=[Depends(require_superadmin)])

Category = Literal["banking", "fintech", "ecommerce", "government", "telecom", "brokerage", "insurance", "consumer",
                   "other"]


class NewOrg(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: Category


class Rotate(BaseModel):
    kind: Literal["org", "demo"]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-") or "org"


def _org(c, slug: str):
    row = repo.org(c, slug)
    if row is None:
        raise HTTPException(404, "No such organisation.")
    return row


@sessions.post("/auth/logout", status_code=204)
def logout(p: auth.Principal = Depends(require_superadmin), c=Depends(get_conn)) -> Response:
    repo.revoke_key(c, p.key_id)
    auth.clear_cache()
    return Response(status_code=204)


@router.get("/orgs")
def orgs(c=Depends(get_conn)) -> list[dict]:
    return repo.list_orgs(c)


@router.post("/orgs", status_code=201)
def create_org(body: NewOrg, c=Depends(get_conn)) -> dict:
    name = body.name.strip()
    slug = slugify(name)
    if repo.name_taken(c, slug, name):
        raise HTTPException(409, "An organisation with this name already exists.")
    repo.insert_org(c, slug, name, body.category)
    org_key = auth.create_key(c, "org", slug, label=f"{name}: analysts")
    demo_key = auth.create_key(c, "demo", slug, label=f"{name}: read-only, shown on the sign-in page")
    return {"slug": slug, "name": name, "category": body.category, "org_key": org_key, "demo_key": demo_key}


@router.get("/orgs/{slug}/keys")
def keys(slug: str, c=Depends(get_conn)) -> dict:
    o = _org(c, slug)
    return {"org_key": repo.current_key(c, o.id, "org"), "demo_key": repo.current_key(c, o.id, "demo")}


@router.post("/orgs/{slug}/rotate")
def rotate(slug: str, body: Rotate, c=Depends(get_conn)) -> dict:
    o = _org(c, slug)
    repo.revoke_kind(c, o.id, body.kind)
    key = auth.create_key(c, body.kind, slug, label=f"{o.name}: rotated")
    auth.clear_cache()
    return {"kind": body.kind, "key": key}


@router.post("/orgs/{slug}/deactivate")
def deactivate(slug: str, c=Depends(get_conn)) -> dict:
    o = _org(c, slug)
    if slug == SETTINGS.pipeline_org:  # live candidates are confirmed on its behalf
        raise HTTPException(409, "The pipeline organisation cannot be deactivated.")
    repo.deactivate(c, o.id)
    auth.clear_cache()
    return {"slug": slug, "active": False}
