"""Copy compiled ABIs from contracts/artifacts into contracts/abi/ (committed) so the API image needs no Node build."""
import json

from services.config import ROOT

NAMES = ("OrgRegistry", "CampaignRegistry", "EvidenceAnchor", "Attestation")
out = ROOT / "contracts/abi"
out.mkdir(exist_ok=True)
for n in NAMES:
    art = json.loads((ROOT / f"contracts/artifacts/contracts/{n}.sol/{n}.json").read_text(encoding="utf-8"))
    (out / f"{n}.json").write_text(json.dumps(art["abi"], indent=1), encoding="utf-8")
print("exported", ", ".join(NAMES))
