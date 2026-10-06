"""Train the triage logistic regression and evaluate it honestly (MODELS.md §2, §7).

- Splits: TEMPORAL (headline) and CAMPAIGN-DISJOINT. Never random.
- Reported: AUC (both splits), recall at threshold, PRECISION AT A 1:1000 BASE RATE, hard-negative FP rate,
  threshold sweep 0.20-0.80, coefficients. Balanced-set precision is never computed.
- Adoption gate: the model is used by triage ONLY if every MODELS.md §7 hard check passes AND the triage
  release-gate cases (services/tests/test_triage.py LEGIT/PHISH) still hold. Otherwise rules stay.
Feature values come from services/ml/features.py — the SAME code triage runs.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from services.config import ROOT, SETTINGS
from services.ingest.brands import load_brands
from services.ml.features import FEATURE_ORDER, extract
from services.ml.split import campaign_disjoint_split, temporal_split

DATA, ART = ROOT / "data/ml", ROOT / "services/ml/artifacts"
BASE_RATE = 1 / 1000  # MODELS.md §0: ~0.1% of the CT firehose is phishing-related
THRESHOLD = SETTINGS.triage_threshold


def load():
    with open(DATA / "positives.csv", encoding="utf-8") as f:
        pos = [{"etld1": r["etld1"], "seen": datetime.fromisoformat(r["seen"])} for r in csv.DictReader(f)]
    neg = [d for d in (DATA / "negatives.txt").read_text(encoding="utf-8").split() if d]
    hard = [d for d in (DATA / "hard_negatives.txt").read_text(encoding="utf-8").split() if d]
    return pos, neg, hard


def tld_rates(pos_names: list[str], neg_names: list[str]) -> dict[str, float]:
    """Empirical phishing rate per TLD from TRAINING data only (no test leakage), Laplace-smoothed."""
    from collections import Counter
    tl = lambda d: d.rsplit(".", 1)[-1]  # noqa: E731
    p, n = Counter(map(tl, pos_names)), Counter(map(tl, neg_names))
    return {t: (p[t] + 1) / (p[t] + n[t] + 2) for t in set(p) | set(n)}


def matrix(names: list[str], idx, rates) -> np.ndarray:
    # feed domains carry no certificate: san_count=1, issuer=None for every class (constant -> no signal)
    return np.array([extract(d, None, 1, idx, tld_rates=rates).vector() for d in names], dtype=float)


def fit(Xtr, ytr):
    base = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000))
    model = CalibratedClassifierCV(base, method="isotonic", cv=5)
    model.fit(Xtr, ytr)
    return model


def coefficients(model) -> list[float]:
    cs = [c.estimator.named_steps["logisticregression"].coef_[0] for c in model.calibrated_classifiers_]
    return np.mean(cs, axis=0).tolist()


def metrics(model, Xp, Xn, Xh) -> dict:
    sp, sn, sh = model.predict_proba(Xp)[:, 1], model.predict_proba(Xn)[:, 1], model.predict_proba(Xh)[:, 1]
    auc = roc_auc_score(np.r_[np.ones(len(sp)), np.zeros(len(sn))], np.r_[sp, sn])
    sweep = []
    for t in np.round(np.arange(0.20, 0.81, 0.05), 2):
        tpr, fpr = float((sp >= t).mean()), float((sn >= t).mean())
        prec = tpr * BASE_RATE / (tpr * BASE_RATE + fpr * (1 - BASE_RATE)) if tpr + fpr else 0.0
        sweep.append({"threshold": float(t), "recall": round(tpr, 4), "fpr": round(fpr, 6),
                      "precision_at_1_in_1000": round(prec, 4), "hard_negative_fp_rate": round(float((sh >= t).mean()), 4),
                      "candidates_per_min_at_200k_certs": round((tpr * BASE_RATE + fpr * (1 - BASE_RATE)) * 200_000, 1)})
    at = next(s for s in sweep if abs(s["threshold"] - THRESHOLD) < 1e-9)
    return {"auc": round(float(auc), 4), "n_test_pos": len(sp), "n_test_neg": len(sn), "n_test_hard": len(sh),
            "at_threshold": at, "sweep": sweep}


def main() -> int:
    idx = load_brands(SETTINGS.brands_file)
    pos, neg, hard = load()
    rng = random.Random(7)
    rng.shuffle(neg)
    rng.shuffle(hard)
    neg_tr, neg_te = neg[: int(len(neg) * 0.7)], neg[int(len(neg) * 0.7):]
    hard_tr, hard_te = hard[: len(hard) // 2], hard[len(hard) // 2:]

    report = {"trained_at": datetime.now().isoformat(), "features": list(FEATURE_ORDER), "base_rate": "1:1000",
              "threshold": THRESHOLD, "splits": {}}
    seen = sorted(r["seen"] for r in pos)
    cutoff = seen[int(len(seen) * 0.67)]
    splits = {"temporal": temporal_split(pos, cutoff), "campaign_disjoint": campaign_disjoint_split(pos, 0.3, seed=7)}
    final = None
    for name, (ptr, pte) in splits.items():
        rates = tld_rates([r["etld1"] for r in ptr], neg_tr)
        Xtr = np.vstack([matrix([r["etld1"] for r in ptr], idx, rates), matrix(neg_tr, idx, rates), matrix(hard_tr, idx, rates)])
        ytr = np.r_[np.ones(len(ptr)), np.zeros(len(neg_tr) + len(hard_tr))]
        model = fit(Xtr, ytr)
        m = metrics(model, matrix([r["etld1"] for r in pte], idx, rates), matrix(neg_te, idx, rates), matrix(hard_te, idx, rates))
        m.update(n_train_pos=len(ptr), cutoff=cutoff.isoformat() if name == "temporal" else None)
        report["splits"][name] = m
        if name == "temporal":
            final = (model, rates)
        print(f"{name:18} AUC {m['auc']}  at {THRESHOLD}: recall {m['at_threshold']['recall']}  "
              f"precision@1:1000 {m['at_threshold']['precision_at_1_in_1000']}  "
              f"hard-neg FP {m['at_threshold']['hard_negative_fp_rate']}", flush=True)

    model, rates = final
    coefs = coefficients(model)
    share = max(abs(c) for c in coefs) / sum(abs(c) for c in coefs)
    report["coefficients"] = dict(zip(FEATURE_ORDER, [round(c, 4) for c in coefs]))
    report["top_coefficient_share"] = round(share, 4)

    # ---- MODELS.md §7 hard checks + the triage release gate ----------------------------------------
    score = lambda d: float(model.predict_proba(matrix([d], idx, rates))[0, 1])  # noqa: E731
    tranco1k = [d for d in (ROOT / SETTINGS.allowlist_file).read_text(encoding="utf-8").split()[:1000]]
    legit = sorted(idx.legit_etld1s)
    from services.tests.test_triage import LEGIT, PHISH
    checks = {
        "1_tranco_top1000_below_threshold": [d for d in tranco1k if score(d) >= THRESHOLD][:20],
        "2_brand_legit_domains_below_0.1": [d for d in legit if score(d) >= 0.1][:20],
        "3_hard_negative_fp_rate_below_5pct": report["splits"]["temporal"]["at_threshold"]["hard_negative_fp_rate"],
        "4_top_coefficient_share_below_0.40": round(share, 4),
        "5_release_gate_phish_missed": [d for d in PHISH if score(d) < THRESHOLD],
        "5_release_gate_legit_flagged": [d for d in LEGIT if score(d) >= THRESHOLD],
    }
    passed = (not checks["1_tranco_top1000_below_threshold"] and not checks["2_brand_legit_domains_below_0.1"]
              and checks["3_hard_negative_fp_rate_below_5pct"] < 0.05 and share < 0.40
              and not checks["5_release_gate_phish_missed"] and not checks["5_release_gate_legit_flagged"])
    report["hard_checks"] = checks
    report["passed_checks"] = passed
    report["decision"] = "model adopted by triage" if passed else "rules stay (provenance 'rules'): a hard check failed"
    ART.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "tld_rates": rates, "features": list(FEATURE_ORDER)}, ART / "triage_lr.joblib")
    (ART / "triage_coefficients.json").write_text(json.dumps(
        {"features": list(FEATURE_ORDER), "coef": [round(c, 4) for c in coefs], "passed_checks": passed}, indent=1),
        encoding="utf-8")
    (ART / "triage_metrics.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    (ART / "threshold_sweep.json").write_text(json.dumps(report["splits"]["temporal"]["sweep"], indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("coefficients", "top_coefficient_share", "hard_checks", "decision")},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
