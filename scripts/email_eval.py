"""Measure the email gate on the labelled sample set, cold vs warm. Writes reports/email_eval.json.

cold: empty database — the two "already confirmed" strong signals cannot fire.
warm: the domains in samples/warm_confirmed.json are confirmed (as if the CT pipeline had caught them first).
Truth labels are phishing | legit. Recall = phishing samples rated `malicious`.
"""
import json
from datetime import datetime, timezone

from services.config import ROOT
from services.email.analyze import DomainLookup, analyze
from services.ingest.triage import _brands, warm

S = ROOT / "services/email/samples"


def run(lookup):
    labels = json.loads((S / "labels.json").read_text(encoding="utf-8"))
    rows = []
    for f, lab in labels.items():
        v = analyze((S / f).read_bytes(), brands=_brands(), lookup=lookup)
        rows.append({"sample": f, "truth": lab["truth"], "scenario": lab["scenario"], "verdict": v.verdict,
                     "strong": v.strong_count, "signals": [f"{s.strength}:{s.name}" for s in v.signals]})
    ph = [r for r in rows if r["truth"] == "phishing"]
    lg = [r for r in rows if r["truth"] == "legit"]
    return {"recall_malicious": f"{sum(r['verdict'] == 'malicious' for r in ph)}/{len(ph)}",
            "phishing_rated_suspicious": f"{sum(r['verdict'] == 'suspicious' for r in ph)}/{len(ph)}",
            "phishing_rated_clean": f"{sum(r['verdict'] == 'clean' for r in ph)}/{len(ph)}",
            "legit_rated_malicious": f"{sum(r['verdict'] == 'malicious' for r in lg)}/{len(lg)}",
            "legit_rated_suspicious": f"{sum(r['verdict'] == 'suspicious' for r in lg)}/{len(lg)}",
            "rows": rows}


if __name__ == "__main__":
    warm()
    confirmed = set(json.loads((S / "warm_confirmed.json").read_text(encoding="utf-8")))
    none = lambda d: DomainLookup(None, None, None, None)  # noqa: E731
    known = lambda d: DomainLookup(1, "confirmed", "c-warm", "CAMP-WARM") if d in confirmed else none(d)  # noqa: E731
    out = {"measured_at": datetime.now(timezone.utc).isoformat(), "n_samples": 13,
           "note": "synthetic labelled sample set (services/email/samples); small n — directional, not a benchmark",
           "cold": run(none), "warm": run(known)}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/email_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for cond in ("cold", "warm"):
        o = out[cond]
        print(f"{cond:5} recall(malicious) {o['recall_malicious']}  phishing->suspicious {o['phishing_rated_suspicious']}"
              f"  phishing->clean {o['phishing_rated_clean']}  legit->malicious {o['legit_rated_malicious']}"
              f"  legit->suspicious {o['legit_rated_suspicious']}")
        for r in o["rows"]:
            print(f"   {r['truth']:8} {r['verdict']:10} strong={r['strong']} {r['sample']:44} {', '.join(r['signals'])}")
