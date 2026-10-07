"""Evidence bundles, artifact files, verification (names the failing artifact), and the UNSENT report."""
from __future__ import annotations

from pathlib import Path

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from evidence.bundle import verify_contents
from evidence.merkle import leaf_hash, merkle_levels
from services.api.deps import Scope, get_ledger, get_scope
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


def _anchor(ledger, bundle_id: str, anchored_tx: str | None, computed_root: str) -> dict:
    if not anchored_tx:
        return {"status": "not_anchored", "tx": None}
    try:
        if not ledger.available():
            return {"status": "unavailable", "tx": anchored_tx}
        # the chain holds the root as it was anchored; compare it with the root RECOMPUTED from the bytes now
        return {"status": "matches" if ledger.verify_anchor(bundle_id, computed_root) else "mismatch", "tx": anchored_tx}
    except Exception:
        return {"status": "unavailable", "tx": anchored_tx}


def _attestations(ledger, root: str) -> dict[str, str]:
    try:
        return ledger.attestations(root) if ledger.available() else {}
    except Exception:
        return {}


@router.get("/evidence/{bundle_id}/verify", response_model=VerifyOut)  # safe: writes nothing
@router.post("/evidence/{bundle_id}/verify", response_model=VerifyOut)
def verify(bundle_id: str, tamper: str | None = Query(None, max_length=128,
                                                      description="demo: flip one byte of this artifact IN MEMORY"),
           s: Scope = Depends(get_scope), ledger=Depends(get_ledger)):
    b, arts = _bundle_or_404(s, bundle_id)
    expected = {a["name"]: a["sha256"] for a in arts}
    d = Path(b["artifact_dir"])
    contents = {name: (d / name).read_bytes() for name in expected if (d / name).is_file()}
    if tamper is not None:
        if tamper not in contents:
            raise HTTPException(422, f"tamper: {tamper!r} is not an artifact of this bundle")
        data = contents[tamper]
        contents[tamper] = (bytes([data[0] ^ 0x01]) + data[1:]) if data else b"\x01"
    r = verify_contents(contents, b["bundle_root"], b["signature"], b["collector_pk"], expected)
    hashes = {n: (hashlib.sha256(contents[n]).hexdigest() if n in contents else "00" * 32) for n in sorted(expected)}
    leaves = [leaf_hash(n, bytes.fromhex(hashes[n])) for n in sorted(expected)]
    atts = _attestations(ledger, b["bundle_root"])
    return {"valid": r.valid, "root_matches": r.root_matches, "signature_valid": r.signature_valid,
            "expected_root": r.expected_root, "computed_root": r.computed_root,
            "failures": [f.__dict__ for f in r.failures],
            "anchor": _anchor(ledger, bundle_id, b["anchored_tx"], r.computed_root),
            "tree": {"leaves": [{"name": n, "leaf": lf.hex()} for n, lf in zip(sorted(expected), leaves)],
                     "levels": [[x.hex() for x in lvl] for lvl in merkle_levels(leaves)]},
            "attestations": atts, "disputed": len(set(atts.values())) > 1 or "disputed" in atts.values(),
            "simulated_tamper": tamper}


@router.get("/evidence/{bundle_id}/report", response_model=ReportOut)
def report(bundle_id: str, s: Scope = Depends(get_scope)):
    r = repo_evidence.latest_report(s, bundle_id)  # org-filtered: another org's bundle has no report here
    if r is None:
        raise HTTPException(404, f"no report for bundle {bundle_id}")
    assert r["sent"] is False  # the schema forbids anything else; this is belt and braces
    return {"bundle_id": bundle_id, "recipient": r["recipient"], "body": r["body"], "generated_at": r["created_at"]}
