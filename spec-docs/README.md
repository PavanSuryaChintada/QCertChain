# SEVER

**Phishing campaign interdiction.** Catch the certificate before the email is sent, and take the whole campaign down in four moves.

*(Name is a placeholder — rename with find-replace.)*

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

## Repository

```
CLAUDE.md                build rules — read first
docs/ARCHITECTURE.md     system shape — read second
docs/PRD.md              scope, users, features
docs/TRD.md              technical specification
docs/NPHARD.md           the QUBO — the core contribution
docs/BLOCKCHAIN.md       contracts, evidence, cryptography
docs/DATA.md             CT stream + enrichment sources + ingest prompt
docs/WORKFLOW.md         phase-by-phase build plan + demo script
docs/DESIGN.md           design system

packages/interdict/      optimisation library — MIT, standalone
packages/evidence/       Merkle + Ed25519 bundles
services/                ingest · enrich · graph · api
contracts/               Solidity + Hardhat
apps/console/            analyst console
```

---

## Running it

```bash
docker compose up -d postgres redis
psql $DATABASE_URL -f services/api/schema.sql

# capture a replay file FIRST — this is demo insurance
python -m services.ingest.capture --minutes 30 --out data/capture.jsonl

cd services/api && pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload

python -m services.ingest.stream
python -m services.api.workers.triage_worker
python -m services.api.workers.enrich_worker

npx hardhat node                          # separate terminal
npx hardhat run scripts/deploy.ts --network localhost

cd apps/console && npm install && npm run dev
```

The system runs with Qiskit uninstalled and with the chain node down.

---

## Attribution

Certificate Transparency (RFC 6962) · certstream by Cali Dog Security · Tranco (KU Leuven) · OpenPhish · PhishTank · URLhaus (abuse.ch) · RDAP (ICANN) · Routeviews via pyasn (University of Oregon) · Team Cymru
