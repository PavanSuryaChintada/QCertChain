# TRD — SEVER

Technical specification. Pairs with `CLAUDE.md`, `ARCHITECTURE.md`, `NPHARD.md`, `BLOCKCHAIN.md`.

---

## 1. Services

```
services/
├── ingest/     CT stream → triage → Redis         (1 process)
├── enrich/     confirmation + enrichment workers  (N processes)
├── graph/      clustering into campaigns          (called by API)
└── api/        FastAPI, all HTTP surface
```

---

## 2. `services/ingest/`

### `stream.py` — CT consumer

```python
CERTSTREAM_URL = "wss://certstream.calidog.io/"
```

Connect, parse `certificate_update` messages, extract every name from `leaf_cert.all_domains`, push to Redis Stream `certs:raw`.

**Requirements**
- Auto-reconnect with exponential backoff, 1 s → 60 s cap
- Expose `connection_state`: `connected` / `reconnecting` / `replay` / `down`
- Emit a heartbeat to Redis every 5 s so the console can show liveness
- Replay mode: read from a captured `.jsonl` file at configurable speed

**Traps**
- The public certstream endpoint goes down periodically. Build replay mode **on day 1**, not as a demo afterthought.
- One certificate can carry hundreds of SANs. Process each name, but cap at 200 per cert and log the overflow.
- Do not run multiple stream consumers. They duplicate, not shard.

### `triage.py` — the hot path

**< 5 ms per name. Profile this early.** At 200k certs/min with several names each, a 50 ms function falls behind within seconds.

```python
def triage(name: str) -> TriageResult:
    """Returns score 0..1 and the reasons. NEVER a verdict."""
```

Signals:

| Signal | Implementation | Weight |
|---|---|---|
| Brand token present | exact substring against brand list | 0.35 |
| Lookalike | Damerau-Levenshtein ≤ 2 against brand list | 0.30 |
| Homoglyph | NFKC normalise + confusables map, then re-check | 0.30 |
| Risky TLD | set membership: `.top .xyz .click .cf .tk .gq .buzz .rest` | 0.15 |
| Phishing keyword | `verify kyc secure login update netbanking account` | 0.15 |
| Many hyphens / long label | `>3` hyphens or label `>25` chars | 0.10 |
| Free CA + new domain | Let's Encrypt + registered < 7 days | 0.10 |
| **Allowlist hit** | exact eTLD+1 in allowlist | **→ score 0, stop** |

`score ≥ 0.45` → candidate.

**Traps**
- **Allowlist first, always.** `sbi.co.in` must never become a candidate. Ship with the top 10k domains plus every brand's real domains.
- Levenshtein against a large brand list is the slow part. Precompute a length-bucketed index and only compare same-ish lengths.
- Use eTLD+1 via `tldextract`, not naive dot-splitting. `login.sbi.co.in.attacker.top` must resolve to `attacker.top`.

### Brand list — `data/brands.yaml`

```yaml
- name: State Bank of India
  tokens: [sbi, onlinesbi, yonosbi]
  legit_domains: [sbi.co.in, onlinesbi.sbi, yonosbi.com]
  sector: banking
```

Ship ~40 Indian brands: banks, UPI apps, telcos, government portals, e-commerce.

---

## 3. `services/enrich/`

### `confirm.py` — evidence, not prediction

```python
async def confirm(domain: str) -> ConfirmResult:
    """candidate -> confirmed | dismissed | unreachable"""
```

Fetch with Playwright (`httpx` fallback). Then check:

| Check | Evidence value |
|---|---|
| Password input present | necessary, not sufficient |
| **Form POST target ≠ page origin** | **strong** |
| Brand logo/favicon hash matches the real brand's | **strong** |
| DOM structure hash matches a known kit | **strong** |
| Obfuscated JS, `eval`, base64 blobs | moderate |
| Page title/meta impersonates the brand | moderate |
| Registered < 30 days | weak, supporting |

**Rules**
- `confirmed` requires **at least two strong signals**. Never one.
- Timeout, DNS failure or parked page → `unreachable`. Stays a candidate. **Never guess.**
- Every verdict stores the reasons that produced it. The UI shows them.

**Safety**
- Respect a hard per-host rate limit
- Never submit credentials, never interact with forms — **fetch and observe only**
- `User-Agent` identifies the scanner honestly
- Hard 15 s timeout, no redirect loops beyond 5 hops

### `enrichers.py`

DNS (A, AAAA, NS, MX, TXT), WHOIS, ASN, TLS chain, and the fingerprints:

```python
def dom_structure_hash(html: str) -> str:
    """
    Strip text, attributes and comments. Keep tag names and nesting only.
    Normalise whitespace. SHA-256 the result.

    This is the kit fingerprint: two pages from the same phishing kit
    produce identical hashes even with different brand names and colours.
    THIS IS THE STRONGEST EDGE IN THE CAMPAIGN GRAPH — get it right.
    """

def favicon_hash(data: bytes) -> str:   # mmh3 over base64, matching Shodan convention
def js_bundle_hashes(page) -> list[str]
```

**Trap:** `dom_structure_hash` must be stable across trivial variation. Test it: take one page, change every string, every colour, every image URL — the hash must not move. If it does, the campaign graph won't cluster and the whole demo fails.

---

## 4. `services/graph/`

### `build.py`

Nodes: `domain`, `ip`, `asn`, `nameserver`, `cert_issuer`, `kit_hash`, `favicon_hash`
Edges: domain → each infrastructure attribute it has.

Edge weights (how strongly they imply the same operator):

```
kit_hash        1.00      same phishing kit — near-certain
favicon_hash    0.85
ip              0.80
nameserver      0.60
asn             0.35      shared hosting produces false links
cert_issuer     0.15      almost everyone uses Let's Encrypt
```

### `cluster.py`

Connected components over edges with weight ≥ 0.6, then merge components sharing ≥ 2 medium-weight edges.

**Trap:** clustering on ASN or cert issuer alone merges half the internet into one campaign. The 0.6 threshold exists to prevent exactly that. Do not lower it to make the demo look bigger.

Campaign confidence = weighted average of internal edge weights.

---

## 5. `services/api/`

```
GET    /health
GET    /stream/state                  connection + mode + rate

GET    /certs/live?limit=             recent triage results (SSE also available)
GET    /candidates?status=&limit=
GET    /domains/{id}                  full record incl. verdict reasons

GET    /campaigns?min_size=
GET    /campaigns/{id}                members, infra, confidence
GET    /campaigns/{id}/graph          cytoscape-format nodes + edges

POST   /campaigns/{id}/interdict      {k, backend, timeout_s} -> plan
GET    /plans/{id}
POST   /plans/{id}/benchmark          all backends, honest table

GET    /evidence/{bundle_id}
POST   /evidence/{bundle_id}/verify   returns failing artifact if any
GET    /evidence/{bundle_id}/report   generated abuse report (NOT sent)

POST   /ledger/publish/{campaign_id}
GET    /ledger/by-kit/{kit_hash}      the cross-org inheritance query
POST   /ledger/attest

POST   /seed/campaign                 demo seeding
POST   /stream/mode                   {live|replay}
```

All responses Pydantic v2. Errors RFC 7807.

**SSE for the live feed.** Polling at the rate certificates arrive will melt the browser. `text/event-stream` on `/certs/live`, throttled server-side to ~20 events/sec for display.

---

## 6. Data stores

**PostgreSQL 16** — entities, edges, plans, evidence metadata. Schema in `services/api/schema.sql` (runnable; do not retype DDL from docs).

**Redis 7** — `certs:raw` stream, `enrich:queue`, heartbeat keys, per-host rate limiters.

**Object store** — evidence artifacts on local disk for the demo (`/data/evidence/{bundle_id}/`), S3-compatible in production.

**Retention:** raw certificate records older than 24 h are dropped. Only candidates and above persist. Without this the DB grows by millions of rows an hour.

---

## 7. Environment

```
# services — requirements.txt, pin exactly
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
sqlalchemy==2.0.36
alembic==1.14.0
psycopg[binary]==3.2.3
redis==5.2.1
websockets==14.1
httpx==0.28.1
playwright==1.49.0
dnspython==2.7.0
python-whois==0.9.5
tldextract==5.1.3
rapidfuzz==3.10.1          # Levenshtein, C-speed
mmh3==5.0.1                # favicon hash
pynacl==1.5.0
ortools==9.11.4210
networkx==3.4.2

# optional extra: quantum
qiskit==1.2.4
qiskit-aer==0.15.1
```

**Pin Qiskit exactly and commit the lockfile in hour 1.** Version drift across `qiskit` / `qiskit-aer` is the single most likely thing to eat a night.

**`playwright install chromium` is a separate step.** Put it in the Dockerfile; it is not a pip dependency.

```
# apps/console
react@18 · vite · typescript · tailwindcss
cytoscape · cytoscape-cose-bilkent     # graph layout
@tanstack/react-query
```

---

## 8. Configuration

```python
# services/config.py — single source, never hardcode twice
SETTINGS = {
    "certstream_url": "wss://certstream.calidog.io/",
    "stream_mode": "live",              # live | replay
    "replay_file": "data/capture.jsonl",
    "replay_speed": 1.0,
    "triage_threshold": 0.45,
    "confirm_timeout_s": 15,
    "enrich_workers": 4,
    "cluster_edge_threshold": 0.6,
    "interdict_budget_k": 5,
    "interdict_backend": "cpsat",       # NOT qaoa by default
    "max_qubo_variables": 24,
    "per_host_rate_limit_s": 2.0,
    "raw_cert_retention_h": 24,
}
```

---

## 9. Failure protocol

| If | Then |
|---|---|
| certstream endpoint down | Replay mode. UI labels it. **Build this day 1.** |
| Triage can't keep up | Profile; move Levenshtein to a length-bucketed index; raise threshold |
| Playwright won't install | `httpx` + raw HTML path; no screenshot; bundle marked partial |
| WHOIS rate-limited | Field marked unknown; graph builds from other edges |
| Clustering merges everything | Raise edge threshold; check ASN edges aren't being counted |
| Qiskit broken by H12 | Ship CP-SAT only; reframe as "same formulation, quantum backend pending" |
| Hardhat unstable | Contracts still testable offline; anchoring queue shows pending |
