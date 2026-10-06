# MODELS — what is trained, what is not, and why

Read before building anything in `services/ingest/triage.py` or `services/enrich/confirm.py`.

---

## 0. The number that shapes this whole document

The certificate firehose is **~200,000 certificates per minute**. Roughly **0.1%** are phishing-related.

So per minute: **~200 phishing, ~199,800 benign.**

Now suppose your classifier is excellent — **99.9% specificity**:

```
false positives  =  199,800 × 0.001  =  ~200 per minute
true positives   =  200 × 0.95       =  ~190 per minute
```

**Precision ≈ 49%.** Half of everything you flag is a legitimate business.

At 99.99% specificity — which nobody achieves on domain names alone — you still get 20 false positives per minute. **288,000 false accusations per day** at the first number, 28,800 at the second.

> **This is the base rate problem, and it is why a classifier alone cannot ship.** No amount of model quality fixes it. The fix is architectural: a cheap recall-oriented filter, followed by a hard evidence gate.

Say this out loud in the pitch. It is the single strongest thing you can say about why everyone else's approach fails.

---

## 1. What we deliberately do not train

| Component | Method | Why not a model |
|---|---|---|
| Kit fingerprint (`dom_structure_hash`) | Deterministic hash | Exact by construction. A model would add error and remove explainability. |
| Campaign clustering | Graph connected components | Deterministic. The edges are facts, not predictions. |
| Interdiction | OR-Tools / QUBO | NP-hard optimisation, no training data exists for "correct takedown sets" |
| Credential POST detection | DOM parsing rule | The strongest single signal, and it is a fact, not a probability |
| Evidence verification | Merkle + Ed25519 | Cryptography |

**Most of this system is not machine learning, and that is a design decision, not a gap.**

The output of this system is an accusation against a real business. A rule that says *"the login form posts credentials to 185.243.115.22, which is not icicibank.com"* is defensible in an abuse report and in court. A model that says *"0.94"* is not.

---

## 2. M1 — Triage scorer

**What it does:** turns a domain name into a 0–1 suspicion score. Runs on every name in the firehose, under 5 ms.

**Model:** logistic regression (scikit-learn). Not a neural network.

**Why logistic regression:**
- ~12 features, all engineered. There is no sequence for an LSTM to exploit and no image for a CNN.
- Must run in under 5 ms at 200k/min. A transformer cannot.
- Coefficients are readable — you can state exactly why a domain scored 0.87.
- Calibrated probability output, which matters because the threshold is an operational lever.

### Features

| Feature | Type | Notes |
|---|---|---|
| `brand_token_exact` | bool | substring match against brand tokens |
| `min_edit_distance` | int | Damerau-Levenshtein to nearest brand token |
| `homoglyph_hit` | bool | NFKC-normalise + confusables map, then re-check |
| `tld_risk` | float | empirical phishing rate per TLD, computed from training data |
| `keyword_count` | int | verify, kyc, secure, login, update, netbanking |
| `hyphen_count` | int | |
| `max_label_len` | int | |
| `digit_ratio` | float | |
| `subdomain_depth` | int | `login.sbi.co.in.attacker.top` is depth 5 |
| `entropy` | float | Shannon entropy of the eTLD+1 |
| `issuer_is_free_ca` | bool | Let's Encrypt, ZeroSSL |
| `san_count` | int | from the certificate |

**Do not add a "domain age" feature.** It requires a WHOIS lookup, which takes 200–2000 ms. That breaks the 5 ms budget. Age belongs in confirmation, not triage.

### Training data

| Class | Source | Volume |
|---|---|---|
| **Positive** | OpenPhish + PhishTank verified, last 90 days | 20,000–50,000 |
| **Negative** | Tranco top 1M, random sample | 200,000 |
| **Hard negatives** | Legitimate domains containing brand tokens — `sbicard.com`, `hdfcsec.com`, `paytmmall.com` | as many as you can find, **this set matters most** |

**The hard negatives are the whole job.** Without them the model learns "contains a bank name = phishing" and flags every legitimate subsidiary, partner and career portal. Spend real time assembling this set by hand.

### The trap that will get you — temporal and campaign leakage

**Do not split randomly.**

Phishing datasets are full of near-duplicates from the same campaign: `sbi-verify-01.top` through `sbi-verify-400.top`. Split randomly and members of the same campaign land in both train and test. The model memorises the campaign, reports 0.99 AUC, and collapses on anything new.

**Split two ways, and report both:**

```python
# 1. TEMPORAL — the honest one
train = phishing[:cutoff_date]      # e.g. everything before day 60
test  = phishing[cutoff_date:]      # the last 30 days

# 2. CAMPAIGN-DISJOINT
#    group by eTLD+1 pattern / shared IP, assign whole groups to folds
```

Expect AUC around **0.90–0.94** with temporal splitting, versus a meaningless **0.99** with random. **Report the lower number.** A team that says "0.92, temporally split, because random splitting leaks campaign members" understands more than one reporting 0.99, and any technical judge will recognise it instantly.

### Threshold, and why it isn't 0.5

The threshold is an **operational lever, not a model output.** We are optimising for **recall at an acceptable candidate volume**, because confirmation is the real gate.

```
threshold 0.30  →  ~95% recall, ~4,000 candidates/min   — too many to confirm
threshold 0.45  →  ~88% recall, ~800 candidates/min     — DEFAULT
threshold 0.60  →  ~70% recall, ~150 candidates/min     — misses too much
```

Tune against your actual confirmation throughput. If enrichment can handle 800/min, use 0.45.

### Reported metrics

| Metric | Why |
|---|---|
| Recall at threshold | Misses are the expensive error here |
| Candidates per minute | The operational constraint |
| **Precision at 1:1000 base rate** | The honest number. Do not report balanced-set precision. |
| Hard-negative FP rate | Measured on the legitimate-brand-token set specifically |
| Coefficients | Printed. Explainability is a deliverable. |

**Never report precision on a balanced test set.** It will say 97% and mean nothing, because the real ratio is 1:1000.

### Fallback if training stalls

Hand-set weights per `docs/TRD.md` §2. Label every score `provenance: rules` in the API and UI. A rule set you can explain beats a model you cannot defend, and the architecture is unchanged.

---

## 3. M2 — Visual brand impersonation

**What it does:** given a screenshot, decide whether it is visually impersonating a known brand's login page.

**Method: embedding similarity against a reference set. No training.**

```
CLIP ViT-B/32  →  512-dim embedding  →  cosine similarity
                  against reference brand login screenshots
```

**Why no training:** you would need thousands of labelled phishing screenshots per brand. They do not exist and you cannot make them in a hackathon. Pretrained visual embeddings already separate "looks like the SBI login page" from "looks like a blog" — that is exactly what they were trained for.

### Reference set — this is the work

For each of ~40 brands, capture **3–5 reference screenshots** of the real login page: desktop, mobile, and any variant. Store embeddings.

```
data/brand_refs/
├── sbi/         onlinesbi_desktop.png  onlinesbi_mobile.png
├── hdfc/        netbanking_desktop.png
└── ...
```

**Assembling this is half a day of manual work and it cannot be skipped.** Budget for it.

### Thresholds

```
cosine ≥ 0.92   strong signal — near-pixel clone
cosine ≥ 0.85   moderate signal
cosine <  0.85  no signal
```

Calibrate by embedding the real pages against each other — different pages of the *same* brand should land around 0.80–0.90, which sets your floor.

### Cheaper alternative if CLIP is heavy

**Perceptual hash (pHash) on the favicon**, plus DOM structure hash. No model, no GPU, runs in milliseconds. Weaker, but it catches the common case — phishing kits almost always reuse the stolen favicon.

**Ship pHash first.** Add CLIP only if there is time. `docs/WORKFLOW.md` cut order applies.

---

## 4. M3 — Kit family clustering *(optional)*

**What it does:** groups DOM structure hashes into kit families, so a kit with minor variants still clusters.

**Method:** MinHash / SimHash over DOM shingles, then agglomerative clustering on Jaccard distance. Unsupervised. No labels.

**Why optional:** exact `dom_structure_hash` matching already catches the dominant case, because kits are copied verbatim. This only helps with modified variants.

**Cut this before anything else.** It is a refinement, not a requirement.

---

## 5. What is NOT a model, restated

The strongest confirmation signals are all rules:

```python
strong_signals = [
    form_posts_to_foreign_origin(dom, page_origin),   # the best signal we have
    dom_structure_hash in known_kit_hashes,
    favicon_hash == brand_favicon_hash,
]
moderate_signals = [
    clip_similarity >= 0.85,
    title_impersonates_brand(title, brand),
    has_obfuscated_js(scripts),
]
weak_signals = [
    registered_within_days(30),
    issuer_is_free_ca,
]

confirmed = count(strong_signals) >= 2
```

**Confirmed requires two independent strong signals.** Never one. Never a moderate-only combination.

And `form_posts_to_foreign_origin` — a login form whose credentials go to an IP that is not the brand — is a **fact**. It appears verbatim in the generated abuse report. No probability can do that work.

---

## 6. Training pipeline

```
services/ml/
├── datasets.py       fetch OpenPhish, PhishTank, Tranco; assemble hard negatives
├── features.py       the 12 triage features — SHARED with triage.py at runtime
├── split.py          temporal + campaign-disjoint splitters
├── train_triage.py   logistic regression, calibration, coefficient export
├── evaluate.py       metrics at realistic base rate, curves, coefficient plot
├── brand_refs.py     capture + embed reference login pages
└── artifacts/
    ├── triage_lr.joblib
    ├── triage_coefficients.json
    ├── triage_metrics.json
    ├── brand_embeddings.npz
    └── threshold_sweep.json
```

**`features.py` is imported by both training and runtime.** If feature computation diverges between the two, the model silently degrades and you will not notice. One implementation, shared.

---

## 7. Hard checks before shipping a model

```python
# 1. Allowlist domains must never score above threshold
for d in tranco_top_1000:
    assert triage(d).score < SETTINGS.triage_threshold, d

# 2. Every brand's real domains must score ~0
for brand in brands:
    for d in brand.legit_domains:
        assert triage(d).score < 0.1, d

# 3. Hard negatives — legitimate domains containing brand tokens
#    Target: under 5% flagged
fp_rate = sum(triage(d).score >= T for d in hard_negatives) / len(hard_negatives)
assert fp_rate < 0.05

# 4. No single feature dominates
top_coef_share = max(abs(c) for c in coefs) / sum(abs(c) for c in coefs)
assert top_coef_share < 0.40, "one feature is carrying the model — check the data"
```

**Check 4 is the equivalent of the slope-dominance check that mattered last time.** If `brand_token_exact` carries 70% of the weight, the model has learned "contains a bank name" and your hard-negative set is too small. Fix the data, not the model.

**Make check 1 a hard failure in CI.** Flagging `google.com` during a demo is unrecoverable.

---

## 8. Prompt for Claude Code

> Build the ML layer under `services/ml/`, following `docs/MODELS.md` exactly.
>
> **Read §0 first.** The base rate is 1:1000. A balanced-set precision number is meaningless here and must never be reported.
>
> Build in this order, reporting after each step:
>
> **1. `datasets.py`** — fetch OpenPhish and PhishTank verified entries from the last 90 days, and a 200k random sample from Tranco top 1M. Then assemble the hard-negative set: legitimate domains containing brand tokens. **Report how many hard negatives you found before continuing** — if it is under 200, tell me and I will source more by hand.
>
> **2. `features.py`** — the 12 features in §2. This module is imported by `services/ingest/triage.py` at runtime. One implementation, shared. No domain-age feature — it needs WHOIS and breaks the 5 ms budget.
>
> **3. `split.py`** — temporal splitter and campaign-disjoint splitter. **Never a random split.** Same-campaign domains in both train and test inflate AUC to meaninglessness.
>
> **4. `train_triage.py`** — logistic regression with probability calibration. Export the model, the coefficients as JSON, and the metrics.
>
> **5. `evaluate.py`** — report recall at threshold, candidates per minute, **precision at a 1:1000 base rate**, hard-negative FP rate, and the coefficient table. Produce a threshold sweep from 0.20 to 0.80.
>
> **Implement the four hard checks in §7 as failing tests**, not warnings. Check 1 in particular — an allowlisted domain scoring above threshold must fail CI.
>
> **6. `brand_refs.py`** — capture reference login screenshots for the brands in `data/brands.yaml` and embed them. Start with favicon pHash; only add CLIP if everything above is green.
>
> **Rules:**
> - Never report balanced-set precision.
> - Never use a random train/test split on this data.
> - If a data source is unreachable, say so — do not substitute another without telling me.
> - If the positive count is under 5,000 after deduplication by campaign, stop and tell me. We ship hand-set weights instead and label the provenance.
>
> Start with `datasets.py` and report the hard-negative count.

---

## 9. What to say about models in the pitch

> "Most of this system is not machine learning, on purpose. The output is an accusation against a real business, so the confirmation gate is rule-based and explainable — a credential form posting to an IP that isn't the bank is a fact, not a probability.
>
> The one learned component is the triage scorer, and it is a logistic regression with twelve readable coefficients, validated on a temporal split because random splitting leaks campaign members and inflates AUC to 0.99.
>
> And the reason detection alone cannot work: at 200,000 certificates a minute with a 0.1% base rate, even 99.9% specificity gives you 200 false positives a minute. That is why we built an evidence gate instead of a better classifier."

That last paragraph is the strongest thing in the deck. It explains why every competing approach fails, using arithmetic rather than opinion.
