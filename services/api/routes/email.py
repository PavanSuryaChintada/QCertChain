"""Email-header analysis endpoints (API_CONTRACT §9). Paste or upload only — no mailbox is ever connected."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.api.deps import Scope, get_redis, get_scope
from services.api.repos import email as repo_email
from services.ingest.triage import _brands

router = APIRouter()
MAX_BYTES = 2 * 1024 * 1024


def _row_out(r: dict) -> dict:
    return {"id": r["id"], "source": r["source"], "verdict": r["verdict"], "strong_count": r["strong_count"],
            "from_addr": r["from_addr"], "from_etld1": r["from_etld1"], "reply_to_etld1": r["reply_to_etld1"],
            "return_path_etld1": r["return_path_etld1"], "auth": r["auth_results"], "received": r["received_hops"],
            "urls": r["urls"] or [], "signals": r["signals"], "linked_campaign_ids": r["linked_campaign_ids"] or [],
            "linked_domain_ids": r["linked_domain_ids"] or [], "received_at": r["received_at"]}


@router.post("/email/analyze")
async def analyze_email(request: Request, s: Scope = Depends(get_scope), r=Depends(get_redis)):
    ctype = request.headers.get("content-type", "")
    source: Literal["analyst", "sample"] = "analyst"
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        f = form.get("eml")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(422, "multipart upload needs a file field named 'eml'")
        raw = await f.read(MAX_BYTES + 1)
    else:
        body = await request.body()
        if len(body) > MAX_BYTES + 4096:
            raise HTTPException(413, "email larger than 2 MB")
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(422, "send JSON {\"raw\": ..., \"source\": ...} or multipart field 'eml'") from None
        if not isinstance(data, dict):
            raise HTTPException(422, "send a JSON object {\"raw\": ..., \"source\": ...}")
        raw = data.get("raw")
        if not isinstance(raw, str):
            raise HTTPException(422, "raw: a string with headers or a full .eml is required")
        source = data.get("source", "analyst")
        if source not in ("analyst", "sample"):
            raise HTTPException(422, "source must be 'analyst' or 'sample'")
        raw = raw.encode("utf-8", errors="replace")
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "email larger than 2 MB")
    v, aid, new_ids = repo_email.analyze_and_store(s, raw, source, _brands())
    for d in new_ids:  # private candidates go through the same evidence gate as CT ones, for THIS org
        await r.lpush("enrich:queue", f"{s.org_id}:{d}")
    p = v.parsed
    return {"id": aid, "source": source, "verdict": v.verdict, "strong_count": v.strong_count,
            "from_addr": p.from_addr, "from_etld1": p.from_etld1, "reply_to_etld1": p.reply_to_etld1,
            "return_path_etld1": p.return_path_etld1, "auth": p.auth, "received": p.received, "urls": p.urls,
            "signals": [s.__dict__ for s in v.signals], "linked_campaigns": v.linked_campaigns,
            "linked_domain_ids": v.linked_domain_ids, "new_candidate_ids": new_ids, "absent": p.absent}


@router.get("/email/analyses")
def list_analyses(verdict: Literal["malicious", "suspicious", "clean"] | None = None,
                  limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), s: Scope = Depends(get_scope)):
    rows = repo_email.list_(s, verdict=verdict, limit=limit, offset=offset)
    return {"items": [_row_out(x) for x in rows], "total": rows[0]["total"] if rows else 0,
            "limit": limit, "offset": offset}


@router.get("/email/analyses/{analysis_id}")
def get_analysis(analysis_id: str, s: Scope = Depends(get_scope)):
    r = repo_email.get(s, analysis_id)
    if r is None:
        raise HTTPException(404, f"analysis {analysis_id} not found")
    return _row_out(r)
