"""Platform-admin routes (admin key only; for any other key these routes do not exist: 404).

The admin key reads NO org-owned data: it can seed a named org and switch the shared ingest's mode,
nothing else. This is the only router allowed to depend on the privileged connection directly.
"""
from __future__ import annotations

from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from services.api.deps import get_conn, get_evidence_dir, get_redis, get_signing_key, require_admin
from services.api.models import ModeRequest, SeedRequest, StreamState
from services.api.repos import admin as repo_admin
from services.api.routes.stream import MODE_REQ, read_state

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class AdminSeedRequest(SeedRequest):
    org: Literal["org1", "org2"] = "org1"
    # deliberately shared infrastructure (the consortium demo: org2's campaign overlaps org1's)
    ip_base: int = Field(10, ge=1, le=200)
    shared_ips: list[str] = Field(default_factory=list, max_length=10)
    shared_nameservers: list[str] = Field(default_factory=list, max_length=10)


@router.post("/seed")
def seed(body: AdminSeedRequest, c: sa.Connection = Depends(get_conn), evidence_dir=Depends(get_evidence_dir),
         key=Depends(get_signing_key)):
    """Synthetic, labelled source='seed' on every row; reserved .example names only (services/api/seed.py)."""
    oid = repo_admin.org_id(c, body.org)
    if oid is None:
        raise HTTPException(404, f"org {body.org} not found")
    if body.ip_base + body.ips > 250:
        raise HTTPException(422, "ip_base + ips must stay inside the documentation /24 ranges")
    try:
        ack = repo_admin.seed(c, org=oid, evidence_dir=evidence_dir, signing_key_hex=key, label=body.label,
                              domains=body.domains, ips=body.ips, asns=body.asns, nameservers=body.nameservers,
                              registrars=body.registrars, brands=body.brands, ip_base=body.ip_base,
                              shared_ips=body.shared_ips, shared_nameservers=body.shared_nameservers)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {**ack, "org": body.org}


@router.post("/reset")
def reset(c: sa.Connection = Depends(get_conn), evidence_dir=Depends(get_evidence_dir), key=Depends(get_signing_key)):
    """Restore the known-good demo state for both organisations in one transaction (demo data only; live CT data
    and its verdicts are kept). The demo CHAIN is reset separately (DEMO.md): chain state is not transactional."""
    return repo_admin.reset_demo(c, evidence_dir=evidence_dir, signing_key_hex=key)


@router.post("/stream/mode", response_model=StreamState)
async def stream_mode(body: ModeRequest, r=Depends(get_redis)):
    """The shared ingest process watches this key and switches source. The UI labels replay at all times."""
    await r.hset(MODE_REQ, mapping={"mode": body.mode, "speed": str(body.speed)})
    return await read_state(r)
