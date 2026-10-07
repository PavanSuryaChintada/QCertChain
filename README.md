# QCertChain

**Phishing campaign interdiction.** Catch the certificate before the email is sent, and take the whole campaign down in four moves.


---

## The problem

| | |
|---|---|
| **21 seconds** | Median time to click a phishing link after delivery |
| **28 minutes** | Median time for a human to report it |
| **4.5 days** | Average time for Google Safe Browsing to detect it |
| **83.9%** | Phishing sites already dead before Safe Browsing notices |

The blocklist arrives after the crime.

## What everyone builds

A URL classifier. Paste a URL, get *"malicious: 94%."*

**It's structurally too late** — a URL only enters a dataset after someone received it. And **it kills one head of a hydra** — attackers run hundreds of domains from one kit on shared infrastructure. Block one, 399 stay live.

## What we do

**Catch the certificate.** Every HTTPS certificate is published to a public append-only log within seconds, and Chrome rejects unlogged ones. Attackers must announce their own domains to get a padlock. We listen to that firehose.

**Rebuild the campaign.** Shared hosting, ASN, nameservers, certificate patterns, DOM structure hash and favicon hash link one domain to the other 399.

**Compute the minimum kill.** *"Take down these 4 — 387 of 400 die."* Maximum coverage, NP-hard, and the core contribution.

**Share it with proof.** A permissioned ledger so the second organisation inherits the first's work, with tamper-evident chain of custody.

---

## The five stages

| | Stage | Method |
|---|---|---|
| 1 | **Ingest** | Certificate Transparency firehose, ~200k certs/min |
| 2 | **Triage** | Brand tokens, lookalikes, homoglyphs — produces *candidates*, never verdicts |
| 3 | **Confirm** | Fetch, screenshot, DOM. Cloned login + foreign credential POST. Evidence, not prediction. |
| 4 | **Cluster** | Infrastructure graph → campaigns |
| 5 | **Interdict** | Maximum coverage under a takedown budget |

---

## Honest positioning

**We never submit a takedown.** Reports are generated, never sent. One false positive takes a legitimate business offline.

**A candidate is not an accusation.** Confirmed requires two independent strong signals, and every verdict shows its reasons.

**Takedown selection runs on OR-Tools CP-SAT.** The same QUBO formulation runs on QAOA, benchmarked with losses reported. Quantum is not in the critical path — the system runs with Qiskit uninstalled.

**CT monitoring is established practice.** Netcraft and others do it commercially. Our contribution is campaign-level interdiction, the cross-organisation ledger and the evidence chain — not CT monitoring itself.

**Stated limits:** HTTP-only phishing has no certificate and is invisible to us. Wildcard certificates hide the phishing subdomain.

---

## Stack

**Ingest** Python 3.11 · websockets · certstream · Redis Streams
**Enrichment** dnspython · RDAP · pyasn · httpx · Playwright · tldextract · rapidfuzz
**API** FastAPI · Pydantic v2 · PostgreSQL 16 · SQLAlchemy 2
**Graph** NetworkX
**Optimisation** OR-Tools CP-SAT *(production)* · Qiskit + Aer QAOA
**Crypto** Ed25519 (PyNaCl) · SHA-256 Merkle
**Chain** Solidity 0.8.24 · Hardhat · ethers.js
**Console** Vite · React 18 · TypeScript · Tailwind · Cytoscape.js

---

## Deployment

| | URL |
|---|---|
| Console (Vercel, `sin1`) | `<console URL: published at submission>` |
| API (Railway, Singapore) | `<API URL: published at submission>` (`GET /health` is open; everything else needs a key) |

Everything runs in Singapore, next to the Supabase database (`ap-southeast-1`). `GET /health` shows the regions and
the measured API-to-database round trip. How to deploy: [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Demo credentials

Every API route except `/health` needs an API key in the `X-API-Key` header, and the console asks for one on first
load. There are four kinds of key. **No real key is written in this repository**: org and admin keys can write and
reset data, and the repository is public.

| Key | What it can do | How it is distributed |
|---|---|---|
| **Demo key** (Bank One SOC, read-only) | Read Bank One SOC's campaigns, plans, evidence and email analyses, plus the shared public certificate feed. `GET` only. | Published here at submission: `<published at submission>` |
| **Bank One SOC org key** | Read and write within Bank One SOC: run interdiction plans, analyse emails, generate abuse reports, anchor to the ledger. | Given to evaluators privately, on request |
| **Bank Two SOC org key** | The same for Bank Two SOC. It inherits Bank One's shared campaign through the ledger, never its telemetry. | Given to evaluators privately, on request |
| **Admin key** | Platform only: `/admin/seed`, `/admin/reset`, `/admin/stream/mode`. It holds no organisation and reads no org data. | Never published |

The demo key:

- **Read-only.** `GET` only (plus `HEAD`/`OPTIONS`): any other HTTP verb returns `405`. Evidence verification
  works through `GET /evidence/{id}/verify`, which recomputes the proof and writes nothing.
- **One organisation.** It is scoped to Bank One SOC. Bank Two SOC's data does not exist for it (`404`).
- **Rate-limited** to 60 requests per minute (`429` with `Retry-After` above that). Normal console use stays under this.
- **Temporary.** It will be revoked and rotated after evaluation. Only its SHA-256 is stored.

Keys are created with `python -m scripts.create_api_key` (see [`docs/MIGRATION_RUNBOOK.md`](docs/MIGRATION_RUNBOOK.md) §5).

---

## Repository

```
CLAUDE.md                build rules: read first
docs/                    specifications, runbooks and the report (index below)
packages/interdict/      optimisation library: MIT, standalone
packages/evidence/       Merkle + Ed25519 bundles
services/                ingest · enrich · graph · ml · email · api (FastAPI + workers + schema.sql)
scripts/                 schema, keys, capture, evaluation, report
contracts/               Solidity + Hardhat
apps/console/            analyst console
deploy/                  Railway service configs + certstream image
```

### Document index

| Document | What it is |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System shape: the five stages, data flow, service boundaries. Read second, after `CLAUDE.md`. |
| [`docs/PRD.md`](docs/PRD.md) | Product requirements: the problem in numbers, users, features, scope. |
| [`docs/TRD.md`](docs/TRD.md) | Technical specification: services, interfaces, configuration. |
| [`docs/NPHARD.md`](docs/NPHARD.md) | The interdiction problem: maximum coverage as a QUBO, solvers, benchmarks. The core contribution. |
| [`docs/BLOCKCHAIN.md`](docs/BLOCKCHAIN.md) | Ledger and cryptography: why a ledger, contracts, evidence bundles, signing. |
| [`docs/MODELS.md`](docs/MODELS.md) | What is trained and what is not, and why the base rate forces a filter plus an evidence gate. |
| [`docs/DATA.md`](docs/DATA.md) | Data sources: the Certificate Transparency stream and the free enrichment sources. |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Exact request and response shapes (Pydantic v2, RFC 7807 errors). |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Console design system: locked tokens and interaction rules. |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | Phase-by-phase build plan, flows and the original demo script. |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Local setup and verification checkpoints, and the failures that actually happen. |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Deploying to Railway + Vercel in Singapore: credentials, order, environment per service. |
| [`docs/MIGRATION_RUNBOOK.md`](docs/MIGRATION_RUNBOOK.md) | Database changes: backup, apply, lock contention, verify, API keys, rollback, demo reset. |
| [`docs/DEMO.md`](docs/DEMO.md) | The 10–12 minute demo script: clicks, data state and narration per segment. |
| [`docs/REPORT.md`](docs/REPORT.md) | Technical report, generated from the measured `reports/metrics.json`. |
| [`docs/QUERY_PLANS.md`](docs/QUERY_PLANS.md) | `EXPLAIN` plans for the five hottest API queries, under row-level security. |
| [`docs/BUILD_DECISIONS.md`](docs/BUILD_DECISIONS.md) | Every ruling taken on the owner's behalf during the build, deferred findings and open owner decisions. |
| [`docs/AI_USAGE_LOG.md`](docs/AI_USAGE_LOG.md) | Development AI-usage log, kept live per task: what the AI did, what the owner decided, what was verified. |
| [`docs/superpowers/specs/2026-10-06-qcertchain-design.md`](docs/superpowers/specs/2026-10-06-qcertchain-design.md) | Design spec: the owner decisions (D1–D9) that override the baseline docs. |
| [`docs/superpowers/plans/2026-10-06-qcertchain.md`](docs/superpowers/plans/2026-10-06-qcertchain.md) | Task-by-task implementation plan the build followed. |

---

## Running it

Prerequisites: Python 3.11, Node 20, Docker. The database is Supabase (`DATABASE_URL` in `.env`, see
[`.env.example`](.env.example)). The local Postgres in compose is for the test suite only.

```bash
cp .env.example .env                         # fill in DATABASE_URL, COLLECTOR_PRIVATE_KEY (python -m scripts.genkey), ...
python -m venv .venv && . .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r services/api/requirements.txt -r services/api/requirements-quantum.txt
playwright install chromium

docker compose up -d redis certstream hardhat   # queue, self-hosted CT stream, demo chain (deploys on boot)
python -m scripts.apply_schema                  # idempotent; see docs/MIGRATION_RUNBOOK.md
python -m scripts.fetch_allowlist               # Tranco top 100k -> data/allowlist.txt

# API keys: each token is printed once
python -m scripts.create_api_key --kind org   --org org1 --label "Bank One SOC"
python -m scripts.create_api_key --kind org   --org org2 --label "Bank Two SOC"
python -m scripts.create_api_key --kind demo  --org org1 --label "read-only demo"
python -m scripts.create_api_key --kind admin --label "platform admin"

uvicorn services.api.main:app --port 8000       # API (repo root)
python -m services.ingest.stream                # each worker in its own terminal
python -m services.api.workers.triage_worker
python -m services.api.workers.enrich_worker
python -m services.api.workers.anchor_worker

curl -X POST localhost:8000/admin/reset -H "X-API-Key: $QCC_KEY_ADMIN"   # seed the demo campaigns

cd apps/console && npm install && npm run dev   # http://localhost:5180, paste a key on first load
```

Or everything in containers: `docker compose up -d` (API on `localhost:8000`). Tests:
`docker compose --profile test up -d postgres-test && pytest`.

The system runs with Qiskit uninstalled and with the chain node down.

---

## Offline demo

The whole demo runs with **no internet connection**:

```bash
python -m scripts.e2e_stack
```

It stands up local Postgres, Redis and a Hardhat chain (contracts deployed), the API, the anchor worker and the
built console, then resets the demo, publishes Bank One's campaign to the chain and runs the browser click-through
with every non-localhost request blocked. It is also the CI `e2e` job. Locally it needs Docker Postgres + Redis
(`docker compose --profile test up -d postgres-test redis`) and `npx hardhat node`; it reads `TEST_DATABASE_URL`,
`REDIS_URL`, `CHAIN_RPC`, `ORG_PRIVATE_KEY` and `ORG2_PRIVATE_KEY`. The console's fonts are self-hosted
(`apps/console/public/fonts`), so nothing is fetched from a CDN.

---

## Attribution

Certificate Transparency (RFC 6962) · certstream by Cali Dog Security · Tranco (KU Leuven) · OpenPhish · PhishTank · URLhaus (abuse.ch) · RDAP (ICANN) · Routeviews via pyasn (University of Oregon) · Team Cymru
