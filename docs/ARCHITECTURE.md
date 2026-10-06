# ARCHITECTURE — QCertChain

Read after `CLAUDE.md`, before any build spec.

---

## 1. The shape of the system

```
          ┌──────────────────────────────────────────────┐
          │  CERTIFICATE TRANSPARENCY FIREHOSE           │
          │  certstream · ~200,000 certs / minute        │
          │  free · public · attackers cannot opt out    │
          └───────────────────┬──────────────────────────┘
                              │  websocket
                              ▼
    ┌─────────────────────────────────────────────────────┐
    │  1 · INGEST            services/ingest/             │
    │  parse cert → extract SANs → push to Redis Stream   │
    │  target: 3,000/sec, < 5 ms per cert                 │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  2 · TRIAGE            services/ingest/triage.py    │
    │  brand tokens · edit distance · TLD risk · keywords │
    │  homoglyph normalise · allowlist                    │
    │  OUTPUT: candidate  (NOT a verdict)                 │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  3 · CONFIRMATION      services/enrich/             │
    │  fetch page · screenshot · DOM · detect login form  │
    │  credential POST target · brand asset match         │
    │  OUTPUT: confirmed | dismissed                      │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  4 · ENRICHMENT        services/enrich/             │
    │  A/AAAA · NS · MX · WHOIS · ASN · cert chain        │
    │  DOM structure hash · favicon hash · JS bundle hash │
    │  → these are the EDGES of the campaign graph        │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  5 · CAMPAIGN GRAPH    services/graph/              │
    │  nodes: domains + infrastructure                    │
    │  edges: shared IP/ASN/NS/issuer/kit-hash/favicon    │
    │  connected components → campaigns                   │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  6 · INTERDICTION      packages/interdict/          │
    │  NP-hard MAXIMUM COVERAGE                           │
    │  reduce → QUBO → CP-SAT | QAOA | greedy             │
    │  OUTPUT: "take down these 4 → 387 of 400 die"       │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  7 · EVIDENCE          packages/evidence/           │
    │  screenshot + DOM + headers + cert + WHOIS + DNS    │
    │  → Merkle root → Ed25519 signature                  │
    │  → generated abuse report  (NEVER SENT)             │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  8 · LEDGER            contracts/                   │
    │  campaign commitments · evidence anchors            │
    │  org attestations · hashes only                     │
    └───────────────────┬─────────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────────┐
    │  9 · CONSOLE           apps/console/                │
    │  live stream · campaign graph · takedown plan       │
    │  evidence viewer · cross-org feed                   │
    └─────────────────────────────────────────────────────┘
```

---

## 2. Why each stage exists

| Stage | Without it | Why it's here |
|---|---|---|
| 1 Ingest | You wait for someone to report a URL | **6 hours ahead of the first victim, 4 days ahead of Google Safe Browsing** |
| 2 Triage | 200k certs/min drowns you | Cheap filter, no verdicts |
| 3 Confirmation | You accuse innocent domains | **The difference between evidence and a guess** |
| 4 Enrichment | You have isolated URLs | These attributes are the graph edges |
| 5 Graph | You block one of 400 | One domain becomes the whole operation |
| 6 Interdiction | You file 400 abuse reports and get rate-limited | **4 takedowns kill 387 domains** |
| 7 Evidence | Registrars reject your report | Abuse reports fail on missing evidence, not on weak threats |
| 8 Ledger | Bank B repeats Bank A's work | Detection propagates with proof |
| 9 Console | Nobody can see any of it | |

**Stages 5 and 6 are the contribution.** Everything else is plumbing that other people also have.

---

## 3. Data flow, concretely

```
03:02:11  cert issued for  icici-verify-kyc.top
03:02:13  INGEST      seen on certstream
03:02:13  TRIAGE      brand token "icici" + risky TLD + keyword "kyc"
                      → candidate, score 0.87
03:02:31  CONFIRM     page fetched. cloned ICICI login.
                      POST target → 185.x.x.x (not icicibank.com)
                      → CONFIRMED
03:02:34  ENRICH      A → 185.x.x.x · ASN 20473 · NS ns1.cheap.dns
                      DOM hash a4f2… · favicon hash 9c31…
03:02:35  GRAPH       DOM hash a4f2 matches 400 known domains
                      → campaign CAMP-0042, 400 domains, 12 IPs,
                        3 ASNs, 4 nameservers
03:02:37  INTERDICT   reduce 412 nodes → 27 → QUBO (24 qubits)
                      CP-SAT: take down 4 → 387 domains die (96.7%)
03:02:41  EVIDENCE    4 signed bundles, Merkle-rooted
03:02:44  LEDGER      campaign commitment + 4 anchors on-chain
03:02:45  CONSOLE     analyst sees the plan

09:00      first phishing email of this campaign is sent
           ── 5 h 58 m after we had the takedown plan ──
```

**That last line is the demo's closing frame.**

---

## 4. Deployment topology

```
Docker Compose (local + demo)
├── postgres:16          entities, graph edges, plans, evidence
├── redis:7              ingest stream + worker queues
├── ingest               1 process, websocket → Redis
├── enrich               N workers (default 4), async httpx + Playwright
├── api                  FastAPI, uvicorn
├── hardhat              local EVM node, contracts deployed on boot
└── console              Vite dev / static build

Production demo:  Railway (api, workers, postgres, redis) + Vercel (console)
```

**Ingest is one process.** Multiple consumers on the same CT stream duplicate work. Scale enrichment, not ingest.

---

## 5. Where cryptography, blockchain and quantum sit

| | Where | What it does |
|---|---|---|
| **Cryptography** | Stage 7 | Ed25519 signs each evidence artifact. Merkle root binds the bundle. Tampering is detectable. |
| **Cryptography** | Stage 8 | PSI lets two orgs check overlap of IOC sets without revealing either list *(stretch)* |
| **Blockchain** | Stage 8 | Campaign commitments, evidence anchors, reporter attestations. Hashes only. |
| **Quantum** | Stage 6 | QAOA on the reduced QUBO. One subproblem. Benchmarked. Never in the critical path. |

---

## 6. Failure modes designed for

| If | Then |
|---|---|
| CT stream drops | Auto-reconnect with backoff; UI shows connection state; replay mode available |
| Nothing interesting during demo | **Replay mode** from a captured file + seeded campaign, both labelled |
| Page fetch times out | Domain stays `candidate`, never `confirmed`. Never guess. |
| Playwright unavailable | Fall back to `httpx` + raw HTML; no screenshot, evidence bundle marked partial |
| Qiskit fails | Router falls to CP-SAT, then greedy. Greedy has no dependencies and cannot fail. |
| Chain node down | Anchoring queues locally and retries; nothing else blocks on it |
| WHOIS rate-limited | Enrichment marks the field unknown; graph still builds from the other edges |

**Every degradation is visible in the UI, never silent.**

---

## 7. What we deliberately do not build

State these as decisions, not gaps:

- **No takedown submission.** Reports are generated, never sent. See `CLAUDE.md` §2.1.
- **No ML classifier for phishing.** Confirmation is rule-based and explainable, because the output is an accusation against a real domain.
- **No HTTP-only phishing detection.** No certificate means no CT record. We say so — it converts poorly, so attackers mostly use HTTPS anyway.
- **No wildcard-cert subdomain enumeration.** `*.example.com` hides the phishing subdomain. Real gap. We catch the parent.
- **No real customer or victim data.** Nothing personal enters the system at any point.
