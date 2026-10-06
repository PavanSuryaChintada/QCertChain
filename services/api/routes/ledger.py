"""Ledger endpoints. Writes are QUEUED (202) — never a synchronous contract call inside a request.
Reads (the inheritance query) go to the chain; if it is down: 503 with the queue depth, nothing else blocks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.api import repo
from services.api.deps import get_conn, get_ledger
from services.api.ledger_service import b32_id
from services.api.routes.campaigns import campaign_or_404

router = APIRouter()
HEX32 = r"^(0x)?[0-9a-fA-F]{64}$"
Org = Literal["org1", "org2"]


class AttestRequest(BaseModel):
    subject_hash: str = Field(..., pattern=HEX32)
    verdict: Literal["confirmed", "dismissed", "disputed"]
    as_org: Org = "org1"


class CorroborateRequest(BaseModel):
    as_org: Org = "org2"


def _depth(c: sa.Connection) -> int:
    return c.execute(sa.text("select count(*) from anchor_queue where not done")).scalar_one()


def _queued(c: sa.Connection, kind: str, payload: dict, **extra) -> dict:
    repo.enqueue_anchor(c, kind, payload)
    repo.log(c, "ledger", f"queued {kind}", context=payload)
    return {"queued": True, "queue_position": _depth(c), **extra}


@router.post("/ledger/publish/{campaign_id}", status_code=202)
def publish(campaign_id: str, c=Depends(get_conn)):
    camp = campaign_or_404(c, campaign_id)
    if not camp["kit_hash"]:
        raise HTTPException(409, "Campaign has no kit fingerprint — nothing to publish by kit hash.")
    return _queued(c, "campaign", {"campaign_id": campaign_id, "as_org": "org1"}, campaign_id=campaign_id)


@router.post("/ledger/attest", status_code=202)
def attest(body: AttestRequest, c=Depends(get_conn)):
    subject = body.subject_hash.lower().removeprefix("0x")
    return _queued(c, "attest", {"subject_hash": subject, "verdict": body.verdict, "as_org": body.as_org},
                   subject_hash=subject)


@router.post("/ledger/corroborate/{campaign_id}", status_code=202)
def corroborate(campaign_id: str, body: CorroborateRequest, c=Depends(get_conn)):
    campaign_or_404(c, campaign_id)
    return _queued(c, "corroborate", {"campaign_id": campaign_id, "as_org": body.as_org}, campaign_id=campaign_id)


@router.get("/ledger/status")
def status(c=Depends(get_conn), ledger=Depends(get_ledger)):
    up = ledger.available()
    orgs = {k: {"address": a.address, "name": ledger.org_name(a.address) if up else None}
            for k, a in ledger.accounts.items()}
    return {"available": up, "queue_depth": _depth(c), "orgs": orgs,
            "reason": getattr(ledger, "reason", None) if not up else None}


@router.get("/ledger/by-kit/{kit_hash}")
def by_kit(kit_hash: str, c=Depends(get_conn), ledger=Depends(get_ledger)):
    """THE INHERITANCE QUERY. The second organisation receives commitments and provenance — never telemetry."""
    h = kit_hash.lower().removeprefix("0x")
    if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
        raise HTTPException(422, "kit_hash must be 32 bytes of hex")
    if not ledger.available():
        raise HTTPException(503, f"Ledger unreachable — queued writes: {_depth(c)}")
    local = {("0x" + b32_id(s).hex()): s for s in c.execute(sa.text(
        "select subject from ledger_events where kind = 'campaign_published'")).scalars()}
    out = []
    for x in ledger.find_by_kit(h):
        out.append({**x, "campaign_id": local.get(x["chain_campaign_id"], x["chain_campaign_id"]),
                    "published_at": datetime.fromtimestamp(x["published_at"], timezone.utc).isoformat(),
                    "corroborations": [{**k, "at": datetime.fromtimestamp(k["at"], timezone.utc).isoformat()}
                                       for k in x["corroborations"]]})
    return {"kit_hash": h, "campaigns": out, "local_telemetry_received": False}
