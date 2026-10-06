# API CONTRACT — QCertChain

Exact request and response shapes. **Build this before the real data exists** — the console and the backend are built in parallel and will diverge without it.

All models are Pydantic v2. All timestamps are UTC ISO-8601. All errors are RFC 7807.

---

## Conventions

```python
class Problem(BaseModel):          # RFC 7807 — every error
    type: str                      # "about:blank" or a doc URL
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
```

```python
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
```

**Enums — use these exact strings everywhere.**

```python
DomainStatus  = Literal["candidate", "confirmed", "dismissed", "unreachable"]
StreamMode    = Literal["live", "replay"]
ConnState     = Literal["connected", "reconnecting", "down", "replay"]
Backend       = Literal["cpsat", "qaoa", "annealing", "greedy"]
NodeKind      = Literal["ip","asn","nameserver","cert_issuer","kit_hash","favicon_hash"]
SignalStrength= Literal["strong", "moderate", "weak"]
Provenance    = Literal["model", "rules"]
Source        = Literal["certstream", "replay", "seed"]
Verdict       = Literal["confirmed", "dismissed", "disputed"]
```

---

## 1. Stream

### `GET /stream/state`

```json
{
  "mode": "live",
  "connection": "connected",
  "certs_per_sec": 3204,
  "names_per_sec": 8891,
  "candidates_per_min": 782,
  "queue_depth": {"certs_raw": 120, "enrich": 44, "anchor": 3},
  "replay_file": null,
  "uptime_s": 14203,
  "last_heartbeat": "2026-09-27T03:02:11Z"
}
```

### `POST /stream/mode`
```json
{"mode": "replay", "speed": 2.0}
```
Returns the same shape as `GET /stream/state`.

### `GET /certs/live` — Server-Sent Events

`Content-Type: text/event-stream`. **Server-throttled to ~20 events/sec** regardless of arrival rate.

```
event: cert
data: {"ts":"2026-09-27T03:02:12Z","name":"icici-verify-kyc.top","etld1":"icici-verify-kyc.top","score":0.87,"is_candidate":true,"domain_id":88213,"issuer":"Let's Encrypt","source":"live"}

event: heartbeat
data: {"ts":"2026-09-27T03:02:13Z","certs_per_sec":3204}
```

**`is_candidate` is the only flag the UI colours on.** `score` alone must never drive colour.

---

## 2. Domains

### `GET /candidates?status=&min_score=&limit=50&offset=0`

```json
{
  "items": [
    {
      "id": 88213,
      "name": "icici-verify-kyc.top",
      "etld1": "icici-verify-kyc.top",
      "status": "confirmed",
      "triage_score": 0.87,
      "brand_matched": "ICICI Bank",
      "confidence": 0.91,
      "campaign_id": "3f2a91c8-...",
      "first_seen": "2026-09-27T03:02:11Z",
      "source": "certstream"
    }
  ],
  "total": 782, "limit": 50, "offset": 0
}
```

### `GET /domains/{id}`

The full record. **Every verdict carries its reasons — a verdict without reasons is a bug.**

```json
{
  "id": 88213,
  "name": "icici-verify-kyc.top",
  "etld1": "icici-verify-kyc.top",
  "status": "confirmed",
  "source": "certstream",
  "first_seen": "2026-09-27T03:02:11Z",
  "last_seen": "2026-09-27T03:02:11Z",

  "triage": {
    "score": 0.87,
    "provenance": "model",
    "threshold": 0.45,
    "reasons": [
      {"feature": "brand_token_exact", "value": "icici", "contribution": 0.35},
      {"feature": "tld_risk",          "value": ".top",  "contribution": 0.15},
      {"feature": "keyword_count",     "value": 2,       "contribution": 0.15},
      {"feature": "min_edit_distance", "value": 0,       "contribution": 0.22}
    ]
  },

  "confirmation": {
    "verdict": "confirmed",
    "confidence": 0.91,
    "confirmed_at": "2026-09-27T03:02:31Z",
    "signals": [
      {"name": "credential_post_foreign_origin", "strength": "strong",
       "detail": "form POST -> 185.243.115.22 (not icicibank.com)"},
      {"name": "kit_dom_hash_match", "strength": "strong",
       "detail": "a4f2c9e1... matches 400 known domains"},
      {"name": "favicon_brand_match", "strength": "moderate",
       "detail": "pHash distance 2 from ICICI favicon"},
      {"name": "recently_registered", "strength": "weak",
       "detail": "registered 3 days ago"}
    ],
    "strong_count": 2,
    "screenshot_url": "/evidence/7c1e.../artifacts/screenshot.png"
  },

  "enrichment": {
    "ip_addresses": ["185.243.115.22"],
    "asn": 20473, "asn_name": "AS-VULTR", "country": "NL",
    "nameservers": ["ns1.cheapdns.top", "ns2.cheapdns.top"],
    "cert_issuer": "Let's Encrypt",
    "registrar": "NameSilo, LLC",
    "registered_at": "2026-09-24T00:00:00Z",
    "dom_hash": "a4f2c9e1...", "favicon_hash": "9c31ab...",
    "partial": false, "errors": null
  },

  "campaign_id": "3f2a91c8-...",
  "evidence_bundle_id": "7c1e4b22-..."
}
```

**`strong_count` must be ≥ 2 for `verdict: "confirmed"`.** The UI should treat a confirmed verdict with `strong_count < 2` as a backend bug and display it as a candidate.

### `POST /domains/{id}/confirm`
Force re-confirmation. `202 Accepted`, returns `{"queued": true, "domain_id": 88213}`.

---

## 3. Campaigns

### `GET /campaigns?min_size=10&status=active`

```json
{
  "items": [{
    "id": "3f2a91c8-...",
    "label": "CAMP-0042",
    "kit_hash": "a4f2c9e1...",
    "domain_count": 400,
    "infra_count": 21,
    "confidence": 0.94,
    "brands": ["ICICI Bank", "HDFC Bank"],
    "status": "active",
    "first_seen": "2026-09-25T18:44:02Z",
    "published_tx": "0x8a1f..."
  }],
  "total": 12, "limit": 50, "offset": 0
}
```

### `GET /campaigns/{id}/graph`

**Cytoscape format directly.** Capped at 1000 nodes; above that, domains collapse into per-infra count badges.

```json
{
  "campaign_id": "3f2a91c8-...",
  "truncated": false,
  "node_count": 421,
  "elements": {
    "nodes": [
      {"data": {"id": "d:88213", "kind": "domain", "label": "icici-verify-kyc.top",
                "status": "confirmed", "weight": 1.0}},
      {"data": {"id": "n:551", "kind": "ip", "label": "185.243.115.22",
                "domain_count": 302, "is_target": true, "target_rank": 1}}
    ],
    "edges": [
      {"data": {"id": "e:1", "source": "d:88213", "target": "n:551", "weight": 0.80}}
    ]
  }
}
```

**`is_target` and `target_rank` are populated only when a plan exists.** They drive the ring styling in `DESIGN.md` §6.

---

## 4. Interdiction

### `POST /campaigns/{id}/interdict`

```json
{"k": 5, "backend": "cpsat", "timeout_s": 10.0}
```

Response:

```json
{
  "plan_id": "b91c...",
  "campaign_id": "3f2a91c8-...",
  "budget_k": 5,
  "backend": "cpsat",
  "fell_back": false,
  "fallback_from": null,
  "objective": 387.0,
  "domains_killed": 387,
  "domains_total": 400,
  "coverage_pct": 96.75,
  "n_variables": 26,
  "qubit_count": null,
  "solve_ms": 41,
  "valid": true,
  "targets": [
    {"rank": 1, "node_id": 551, "kind": "ip", "value": "185.243.115.22",
     "kills": 302, "takedown_route": "hosting"},
    {"rank": 2, "node_id": 612, "kind": "nameserver", "value": "ns1.cheapdns.top",
     "kills": 61, "takedown_route": "dns"},
    {"rank": 3, "node_id": 770, "kind": "kit_hash", "value": "a4f2c9e1...",
     "kills": 19, "takedown_route": "hosting"},
    {"rank": 4, "node_id": 203, "kind": "asn", "value": "20473",
     "kills": 5, "takedown_route": "hosting"}
  ],
  "killed_domain_ids": [88213, 88214, "..."]
}
```

**`qubit_count` is `null` for classical backends.** The UI shows `n_variables` always, `qubit_count` only when present.

**`fell_back: true` must be surfaced as text**, e.g. `qaoa timed out → cpsat`. `DESIGN.md` §9.

### `POST /plans/{id}/benchmark`

**Return every row, including losses.** A filtered table is worse than none.

```json
{
  "plan_id": "b91c...",
  "n_variables": 26,
  "rows": [
    {"backend":"cpsat","objective":387.0,"domains_killed":387,"coverage_pct":96.75,
     "solve_ms":41,"valid":true,"qubit_count":null,"is_best":true},
    {"backend":"qaoa","objective":371.0,"domains_killed":371,"coverage_pct":92.75,
     "solve_ms":8420,"valid":true,"qubit_count":24,"is_best":false},
    {"backend":"annealing","objective":379.0,"domains_killed":379,"coverage_pct":94.75,
     "solve_ms":1120,"valid":true,"qubit_count":null,"is_best":false},
    {"backend":"greedy","objective":364.0,"domains_killed":364,"coverage_pct":91.00,
     "solve_ms":3,"valid":true,"qubit_count":null,"is_best":false}
  ]
}
```

**The backend computes `is_best`.** The UI does not sort to favour anything.

---

## 5. Evidence

### `GET /evidence/{bundle_id}`

```json
{
  "id": "7c1e4b22-...",
  "domain_id": 88213,
  "campaign_id": "3f2a91c8-...",
  "bundle_root": "c8e1a4f0...",
  "signature": "3045022100...",
  "collector_pk": "ed25519:9f2c...",
  "partial": false,
  "created_at": "2026-09-27T03:02:41Z",
  "anchored_tx": "0x8a1f...",
  "anchored_at": "2026-09-27T03:02:44Z",
  "artifacts": [
    {"name":"screenshot.png","sha256":"3f2a91...","size_bytes":867234,
     "url":"/evidence/7c1e4b22-.../artifacts/screenshot.png"},
    {"name":"dom.html","sha256":"a4f2c9...","size_bytes":31204,
     "url":"/evidence/7c1e4b22-.../artifacts/dom.html"}
  ]
}
```

### `POST /evidence/{bundle_id}/verify`

**Must name the failing artifact.** "Verification failed" is useless; the filename is the demo moment.

```json
{
  "valid": false,
  "root_matches": false,
  "signature_valid": true,
  "expected_root": "c8e1a4f0...",
  "computed_root": "5e88b1c2...",
  "failures": [
    {"artifact": "dom.html", "expected": "a4f2c9...", "found": "5e88b1...",
     "reason": "hash_mismatch"}
  ]
}
```

On success: `{"valid": true, "root_matches": true, "signature_valid": true, "failures": []}`

### `GET /evidence/{bundle_id}/report`

```json
{
  "bundle_id": "7c1e4b22-...",
  "recipient": "abuse@namesilo.com",
  "format": "markdown",
  "body": "## Phishing report\n\n**Domain:** icici-verify-kyc.top\n...",
  "sent": false,
  "generated_at": "2026-09-27T03:02:45Z"
}
```

**`sent` is always `false` and the database constraint enforces it.** See `CLAUDE.md` §2.1.

---

## 6. Ledger

### `POST /ledger/publish/{campaign_id}`
```json
{"queued": true, "campaign_id": "3f2a91c8-...", "queue_position": 2}
```
**Non-blocking.** Returns immediately; the anchor worker handles it.

### `GET /ledger/by-kit/{kit_hash}` — the inheritance query

```json
{
  "kit_hash": "a4f2c9e1...",
  "campaigns": [{
    "campaign_id": "3f2a91c8-...",
    "ioc_root": "d41f...",
    "domain_count": 400,
    "confidence": 94,
    "reporter": {"address": "0xA1b2...", "name": "Bank One SOC"},
    "published_at": "2026-09-27T03:02:44Z",
    "tx_hash": "0x8a1f...",
    "corroborations": [{"address":"0xC3d4...","name":"Bank Two SOC",
                        "at":"2026-09-27T05:11:02Z"}]
  }],
  "local_telemetry_received": false
}
```

**`local_telemetry_received: false` is deliberate.** Display it — it is the point of the ledger layer.

### `POST /ledger/attest`
```json
{"subject_hash": "0xa4f2...", "verdict": "disputed"}
```

---

## 7. Ops and seeding

### `GET /metrics`
```json
{"campaigns_active": 12, "domains_confirmed": 47, "domains_candidate": 782,
 "certs_per_sec": 3204, "plans_today": 6, "bundles_today": 19,
 "anchor_queue_depth": 3}
```

### `GET /ops/log?since=&channel=&limit=100`
```json
{"items":[{"id":4412,"at":"2026-09-27T03:02:37Z","channel":"interdict",
           "severity":0,"message":"plan b91c solved · cpsat · 41ms · 387/400",
           "context":{"plan_id":"b91c..."}}],
 "total":4412,"limit":100,"offset":0}
```

### `POST /seed/campaign`
```json
{"label":"titli-kit","domains":400,"ips":12,"asns":3,"nameservers":4,"brands":["ICICI Bank"]}
```
Returns a campaign object with `"source": "seed"` on every created domain. **The UI must display the source.**

---

## 8. Error cases the console must handle

| Code | When | Console behaviour |
|---|---|---|
| `409` | Interdict on a campaign with no shared infrastructure | *"No shared infrastructure — nothing to interdict."* Not an error state. |
| `422` | `k` larger than the candidate node count | Clamp the control, show the max |
| `503` | Chain unreachable on publish | Queue it, show depth, **do not block anything** |
| `404` | Bundle artifacts purged | *"Artifacts no longer on disk — hashes retained."* |
| `429` | Confirm requested too fast for one host | Show the rate limit, do not retry automatically |

---

## 9. Rule for both teams

**This file is the contract.** If the backend needs to change a shape, change it here first and tell the console team. Divergence between these two is the most common way parallel work falls apart under time pressure.

Ship fixture responses matching every shape above on day 1, before any real data exists. The console builds against fixtures; the backend swaps them out underneath.
