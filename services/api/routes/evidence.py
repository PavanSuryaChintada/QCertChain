"""Evidence bundles, artifact files, verification (names the failing artifact), and the UNSENT report."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from evidence.bundle import verify_bundle
from services.api.deps import Scope, get_scope
from services.api.models import EvidenceOut, ReportOut, VerifyOut
from services.api.repos import evidence as repo_evidence

router = APIRouter()


def _bundle_or_404(s: Scope, bundle_id: str):
    got = repo_evidence.bundle(s, bundle_id)
    if got is None:
        raise HTTPException(404, f"bundle {bundle_id} not found")
    return got


@router.get("/evidence/{bundle_id}", response_model=EvidenceOut)
def get_bundle(bundle_id: str, s: Scope = Depends(get_scope)):
    b, arts = _bundle_or_404(s, bundle_id)
    return {**{k: v for k, v in b.items() if k != "artifact_dir"},
            "artifacts": [{**a, "url": f"/evidence/{bundle_id}/artifacts/{a['name']}"} for a in arts]}


@router.get("/evidence/{bundle_id}/artifacts/{name}")
def get_artifact(bundle_id: str, name: str, s: Scope = Depends(get_scope)):
    b, arts = _bundle_or_404(s, bundle_id)
    if name not in {a["name"] for a in arts}:  # only recorded artifact names: no path traversal possible
        raise HTTPException(404, f"no artifact {name!r} in bundle {bundle_id}")
    path = Path(b["artifact_dir"]) / name
    if not path.is_file():
        raise HTTPException(404, "Artifacts no longer on disk — hashes retained.")
    media = {"png": "image/png", "html": "text/plain; charset=utf-8", "json": "application/json",
             "pem": "application/x-pem-file"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
    return FileResponse(path, media_type=media)  # served as text: a captured phishing page is never rendered


@router.get("/evidence/{bundle_id}/verify", response_model=VerifyOut)  # safe: writes nothing
@router.post("/evidence/{bundle_id}/verify", response_model=VerifyOut)
def verify(bundle_id: str, s: Scope = Depends(get_scope)):
    b, arts = _bundle_or_404(s, bundle_id)
    r = verify_bundle(Path(b["artifact_dir"]), b["bundle_root"], b["signature"], b["collector_pk"],
                      {a["name"]: a["sha256"] for a in arts})
    return {"valid": r.valid, "root_matches": r.root_matches, "signature_valid": r.signature_valid,
            "expected_root": r.expected_root, "computed_root": r.computed_root,
            "failures": [f.__dict__ for f in r.failures]}


@router.get("/evidence/{bundle_id}/report", response_model=ReportOut)
def report(bundle_id: str, s: Scope = Depends(get_scope)):
    r = repo_evidence.latest_report(s, bundle_id)  # org-filtered: another org's bundle has no report here
    if r is None:
        raise HTTPException(404, f"no report for bundle {bundle_id}")
    assert r["sent"] is False  # the schema forbids anything else; this is belt and braces
    return {"bundle_id": bundle_id, "recipient": r["recipient"], "body": r["body"], "generated_at": r["created_at"]}
