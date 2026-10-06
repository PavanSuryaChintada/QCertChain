"""Evidence bundles, artifact files, verification (names the failing artifact), and the UNSENT report."""
from __future__ import annotations

import uuid
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from evidence.bundle import verify_bundle
from services.api.deps import get_conn
from services.api.models import EvidenceOut, ReportOut, VerifyOut

router = APIRouter()


def _bundle_or_404(c: sa.Connection, bundle_id: str):
    try:
        uuid.UUID(bundle_id)
    except ValueError:
        raise HTTPException(404, f"bundle {bundle_id} not found") from None
    b = c.execute(sa.text("""select id::text, domain_id, campaign_id::text, bundle_root, signature, collector_pk,
                             artifact_dir, partial, created_at, anchored_tx, anchored_at
                             from evidence_bundles where id = :id"""), {"id": bundle_id}).mappings().one_or_none()
    if b is None:
        raise HTTPException(404, f"bundle {bundle_id} not found")
    arts = c.execute(sa.text("select name, sha256, size_bytes from evidence_artifacts where bundle_id = :id order by name"),
                     {"id": bundle_id}).mappings().all()
    return b, arts


@router.get("/evidence/{bundle_id}", response_model=EvidenceOut)
def get_bundle(bundle_id: str, c=Depends(get_conn)):
    b, arts = _bundle_or_404(c, bundle_id)
    return {**{k: v for k, v in b.items() if k != "artifact_dir"},
            "artifacts": [{**a, "url": f"/evidence/{bundle_id}/artifacts/{a['name']}"} for a in arts]}


@router.get("/evidence/{bundle_id}/artifacts/{name}")
def get_artifact(bundle_id: str, name: str, c=Depends(get_conn)):
    b, arts = _bundle_or_404(c, bundle_id)
    if name not in {a["name"] for a in arts}:  # only recorded artifact names: no path traversal possible
        raise HTTPException(404, f"no artifact {name!r} in bundle {bundle_id}")
    path = Path(b["artifact_dir"]) / name
    if not path.is_file():
        raise HTTPException(404, "Artifacts no longer on disk — hashes retained.")
    media = {"png": "image/png", "html": "text/plain; charset=utf-8", "json": "application/json",
             "pem": "application/x-pem-file"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
    return FileResponse(path, media_type=media)  # served as text: a captured phishing page is never rendered


@router.post("/evidence/{bundle_id}/verify", response_model=VerifyOut)
def verify(bundle_id: str, c=Depends(get_conn)):
    b, arts = _bundle_or_404(c, bundle_id)
    r = verify_bundle(Path(b["artifact_dir"]), b["bundle_root"], b["signature"], b["collector_pk"],
                      {a["name"]: a["sha256"] for a in arts})
    return {"valid": r.valid, "root_matches": r.root_matches, "signature_valid": r.signature_valid,
            "expected_root": r.expected_root, "computed_root": r.computed_root,
            "failures": [f.__dict__ for f in r.failures]}


@router.get("/evidence/{bundle_id}/report", response_model=ReportOut)
def report(bundle_id: str, c=Depends(get_conn)):
    _bundle_or_404(c, bundle_id)
    r = c.execute(sa.text("select recipient, body, created_at, sent from abuse_reports where bundle_id = :id "
                          "order by created_at desc limit 1"), {"id": bundle_id}).mappings().one_or_none()
    if r is None:
        raise HTTPException(404, f"no report for bundle {bundle_id}")
    assert r["sent"] is False  # the schema forbids anything else; this is belt and braces
    return {"bundle_id": bundle_id, "recipient": r["recipient"], "body": r["body"], "generated_at": r["created_at"]}
