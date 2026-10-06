# CLAUDE.md — Build Rules for SEVER

> Read this completely before writing any code. It overrides your defaults.
> Read `docs/ARCHITECTURE.md` next. Then the spec for whatever you are building.

*(Name is a placeholder. Rename with find-replace if the team picks another.)*

---

## 1. What this is

**SEVER** — a phishing campaign interdiction platform.

Everyone else builds a URL classifier. We do three things nobody else does:

1. **Catch the domain before the email is sent**, by monitoring the live Certificate Transparency firehose. Attackers must publish their own certificates to get an HTTPS padlock; we listen.
2. **Reconstruct the whole campaign**, not the single URL — 400 domains linked by shared kit, hosting, nameservers, certificate patterns.
3. **Compute the minimum set of takedowns that kills the campaign.** This is maximum coverage, NP-hard, and it is our core contribution.

Plus a permissioned ledger so one organisation's detection instantly protects the next, with tamper-proof evidence.

**The one-liner:** *Everyone blocks the URL after someone clicked it. We catch the certificate before the email is sent, and take down the whole campaign in four moves.*

---

## 2. Non-negotiable rules

### 2.1 Never fire a real takedown
We **generate** evidence-backed abuse reports. We **never submit** them.

Auto-submitting abuse reports from a hackathon project is a real-world action against real domains, and one false positive takes a legitimate business offline. The generated request is just as convincing in a demo.

No code in this repo sends email, files abuse forms, or calls registrar APIs. If you find yourself writing an SMTP client, stop.

### 2.1b The base rate makes a classifier alone impossible
200,000 certs/min at a ~0.1% phishing base rate means even 99.9% specificity
produces ~200 false positives per minute. No model quality fixes this. The
architecture is a cheap recall-oriented filter followed by a hard evidence
gate. See `docs/MODELS.md` §0 before building triage or confirmation.

### 2.2 Never claim a domain is malicious on name-matching alone
A name match (`sbi-verify.xyz`) is a **candidate**, not a verdict. A domain is only marked confirmed after we **fetch the page and find evidence** — cloned login form, brand assets, credential POST to a foreign origin.

Every domain in the system carries an explicit `status`: `candidate` → `confirmed` → `dismissed`. The UI must show which. **Never colour a candidate red.**

### 2.3 Honest quantum positioning
QAOA runs on one reduced subproblem, ~20 qubits, benchmarked against OR-Tools CP-SAT and greedy, **with losses reported**.

Framing, verbatim wherever it appears:
> "Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path."

Never put "quantum" in a heading, a nav item, or the tagline. Never claim quantum searches millions of certificates.

### 2.4 Blockchain must earn its place
The ledger exists for four reasons, all real: cross-organisation intelligence sharing, tamper-proof chain of custody for evidence, non-repudiation of who reported what, and avoiding a central honeypot.

**It stores hashes and commitments only.** No raw telemetry, no page content, no personal data ever goes on-chain.

### 2.5 The demo must survive a dead stream
The CT firehose may produce nothing interesting during a 5-minute demo window. Build a **replay mode** that plays back a captured stream file, and seed a known campaign. Both must be indistinguishable from live in the UI, and the UI must **label which mode is running**.

---

## 3. Repository layout

```
sever/
├── CLAUDE.md
├── README.md
├── docs/
│   ├── ARCHITECTURE.md     # read after this file
│   ├── PRD.md              # scope, users, features
│   ├── TRD.md              # technical spec
│   ├── NPHARD.md           # the QUBO — core contribution
│   ├── BLOCKCHAIN.md       # contracts and ledger design
│   ├── MODELS.md           # what is trained, what is not, and the data
│   ├── DATA.md             # CT stream + enrichment sources
│   ├── API_CONTRACT.md     # exact request/response shapes
│   ├── RUNBOOK.md          # setup + verification checkpoints
│   ├── WORKFLOW.md         # phase-by-phase build plan
│   └── DESIGN.md           # design system
├── services/
│   ├── api/                # FastAPI + BUILD_SPEC.md + schema.sql
│   ├── ingest/             # CT stream consumer
│   ├── enrich/             # DNS, WHOIS, ASN, page fetch, kit hash
│   └── graph/              # campaign clustering
├── packages/
│   ├── interdict/          # the QUBO solver — standalone, MIT
│   └── evidence/           # bundle builder + Ed25519 signing
├── contracts/              # Solidity + Hardhat + BUILD_SPEC.md
└── apps/
    ├── console/            # analyst dashboard
    └── BUILD_SPEC.md
```

`packages/interdict` imports nothing from the rest of the repo. It is publishable on its own.

---

## 4. Stack — pinned

**Ingest** Python 3.11 · `websockets` · `certstream` protocol · Redis Streams
**Enrichment** `dnspython` · `python-whois` · `pyasn` · `httpx` · Playwright (screenshots) · `tldextract` · `Levenshtein`
**API** FastAPI · Pydantic v2 · Uvicorn
**Database** PostgreSQL 16 · SQLAlchemy 2 · Alembic
**Graph** NetworkX (in-process; **not** Neo4j — setup cost too high for the window)
**Optimisation** OR-Tools CP-SAT *(production)* · Qiskit 1.2.4 + qiskit-aer 0.15.1 *(the QUBO)*
**Crypto** PyNaCl (Ed25519) · `pymerkle` or hand-rolled Merkle
**Chain** Solidity 0.8.24 · Hardhat · ethers.js v6 · local EVM node *(not Hyperledger Fabric — a two-day install)*
**Frontend** Vite · React 18 · TypeScript · Tailwind · Cytoscape.js (graph) · TanStack Query
**Deploy** Docker Compose · Railway (API) · Vercel (console)

Do not add libraries not listed without stating why.

---

## 5. Hard performance targets

| | Target |
|---|---|
| CT ingest throughput | ≥ 3,000 certs/sec sustained, no backpressure loss |
| Triage decision | < 5 ms per certificate |
| Candidate → confirmation verdict | < 20 s |
| Campaign clustering on 500 nodes | < 2 s |
| Interdiction solve (OR-Tools) | < 1 s |
| Interdiction solve (QAOA, ≤24 qubits) | < 15 s |

**The firehose is ~200k certs/minute.** If triage is slow, everything backs up. Profile it early.

---

## 6. Testing floor

Four tests are release gates. Do not demo without them green.

- `test_triage.py` — known-good domains (`google.com`, `sbi.co.in`) never become candidates; known phishing patterns always do
- `test_interdict.py` — 500 random instances, solver output never exceeds budget `k`, and coverage is correctly computed
- `test_fallback.py` — with Qiskit patched to fail on import, `solve()` still returns a valid plan
- `test_evidence.py` — a tampered artifact invalidates the Merkle root and the signature check fails

---

## 6b. Where the specs live

Read in this order for whatever you are building:

- `docs/ARCHITECTURE.md` — system shape. **Always second, after this file.**
- `docs/RUNBOOK.md` — setup and verification. **Run §0 before any other work.**
- `docs/API_CONTRACT.md` — exact shapes. Backend and console both build against it.
- `docs/NPHARD.md` — the QUBO. Core contribution.
- `docs/MODELS.md` — what is trained and what is not. **§0 before any triage work.**
- `docs/BLOCKCHAIN.md` + `contracts/BUILD_SPEC.md` — ledger and contracts
- `docs/DATA.md` — sources and the ingest prompt
- `services/api/BUILD_SPEC.md` · `apps/BUILD_SPEC.md` — file-by-file contracts
- `services/api/schema.sql` — runnable. Apply with psql; never retype DDL.

## 7. When you are unsure

Ask rather than assume. If a spec in `docs/` conflicts with this file, this file wins. Stop and ask before adding a dependency, sending any outbound request to a third party's abuse channel, claiming a performance result, or marking a domain confirmed on weak evidence.
