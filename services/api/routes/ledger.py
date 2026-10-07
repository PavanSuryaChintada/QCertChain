"""Ledger endpoints. Writes are QUEUED (202) — never a synchronous contract call inside a request.
Reads (the inheritance query) go to the chain; if it is down: 503 with the queue depth, nothing else blocks.

Two trust boundaries: the chain is public to every member (hashes, counts, reporter, timestamp); local rows
are org-scoped. The signing org of every write is the API key's org — there is no `as_org` field to forge.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from services.api import cursor
from services.api.deps import Scope, get_ledger, get_scope
from services.api.ledger_service import b32_id
from services.api.repos import ledger as repo_ledger
from services.api.routes.campaigns import campaign_or_404

router = APIRouter()
HEX32 = r"^(0x)?[0-9a-fA-F]{64}$"


class AttestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # an `as_org` field is rejected, not silently ignored
    subject_hash: str = Field(..., pattern=HEX32)
    verdict: Literal["confirmed", "dismissed", "disputed"]


def _queued(s: Scope, kind: str, payload: dict, **extra) -> dict:
    repo_ledger.enqueue(s, kind, payload)
    return {"queued": True, "queue_position": repo_ledger.queue_depth(s), "as_org": s.org_slug, **extra}


@router.post("/ledger/publish/{campaign_id}", status_code=202)
def publish(campaign_id: str, s: Scope = Depends(get_scope)):
    camp = campaign_or_404(s, campaign_id)
    if not camp["kit_hash"]:
        raise HTTPException(409, "Campaign has no kit fingerprint — nothing to publish by kit hash.")
    return _queued(s, "campaign", {"campaign_id": campaign_id}, campaign_id=campaign_id)


@router.post("/ledger/attest", status_code=202)
def attest(body: AttestRequest, s: Scope = Depends(get_scope)):
    subject = body.subject_hash.lower().removeprefix("0x")
    return _queued(s, "attest", {"subject_hash": subject, "verdict": body.verdict}, subject_hash=subject)


@router.post("/ledger/corroborate/{chain_campaign_id}", status_code=202)
def corroborate(chain_campaign_id: str, s: Scope = Depends(get_scope)):
    """Corroborate a campaign found ON CHAIN (typically another org's). Takes the chain id from /ledger/by-kit,
    not a local campaign id: the corroborating org never needs, or gets, the reporter's local rows."""
    h = chain_campaign_id.lower().removeprefix("0x")
    if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
        raise HTTPException(422, "chain_campaign_id must be 32 bytes of hex (from /ledger/by-kit)")
    return _queued(s, "corroborate", {"chain_campaign_id": h}, chain_campaign_id=h)


@router.get("/ledger/events")
def events(limit: int = cursor.LimitQ, cursor_: str | None = Query(None, alias="cursor", max_length=512),
           s: Scope = Depends(get_scope)):
    """What THIS organisation anchored, published, attested and corroborated (its local index of the chain)."""
    rows = repo_ledger.events(s, limit=limit, after=cursor.decode(cursor_, 1))
    return cursor.page(rows, limit, lambda r: [r["id"]])


@router.get("/ledger/status")
def status(s: Scope = Depends(get_scope), ledger=Depends(get_ledger)):
    up = ledger.available()
    orgs = {k: {"address": a.address, "name": ledger.org_name(a.address) if up else None}
            for k, a in ledger.accounts.items()}
    return {"available": up, "queue_depth": repo_ledger.queue_depth(s), "orgs": orgs, "you": s.org_slug,
            "reason": getattr(ledger, "reason", None) if not up else None}


@router.get("/ledger/by-kit/{kit_hash}")
def by_kit(kit_hash: str, s: Scope = Depends(get_scope), ledger=Depends(get_ledger)):
    """THE INHERITANCE QUERY. The second organisation receives commitments and provenance — never telemetry."""
    h = kit_hash.lower().removeprefix("0x")
    if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
        raise HTTPException(422, "kit_hash must be 32 bytes of hex")
    if not ledger.available():
        raise HTTPException(503, f"Ledger unreachable — queued writes: {repo_ledger.queue_depth(s)}")
    own = {("0x" + b32_id(x).hex()): x for x in repo_ledger.published_subjects(s)}
    out = []
    for x in ledger.find_by_kit(h):
        out.append({**x, "campaign_id": own.get(x["chain_campaign_id"]),  # set only for THIS org's campaigns
                    "yours": x["chain_campaign_id"] in own,
                    "published_at": datetime.fromtimestamp(x["published_at"], timezone.utc).isoformat(),
                    "corroborations": [{**k, "at": datetime.fromtimestamp(k["at"], timezone.utc).isoformat()}
                                       for k in x["corroborations"]]})
    return {"kit_hash": h, "campaigns": out, "local_telemetry_received": False}
