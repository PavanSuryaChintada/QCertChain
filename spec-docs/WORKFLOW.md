# WORKFLOW — SEVER

Phase-by-phase build plan, flows, and the demo script.

**Assumption flagged:** written for **4 people over a 36-hour window**. Compress proportionally if shorter; the cut order in §4 holds either way. Tell me your real numbers and I'll rework the phases.

Roles: **A** ingest + triage · **B** enrich + graph · **C** interdict + ledger · **D** console + integration

---

## 1. The pipeline, as a flow

```
CT firehose
    │
    ▼
INGEST ──────────► triage (<5ms)  ──► score < 0.45 ──► drop
    │                                      │
    │                                 score ≥ 0.45
    │                                      ▼
    │                               CANDIDATE  (not a verdict)
    │                                      │
    ▼                                      ▼
heartbeat                            CONFIRMATION
to console                     fetch · screenshot · DOM
                                           │
                        ┌──────────────────┼──────────────────┐
                        ▼                  ▼                  ▼
                   dismissed          unreachable         CONFIRMED
                                    (stays candidate)          │
                                                               ▼
                                                        ENRICHMENT
                                            DNS · WHOIS · ASN · cert
                                            dom_hash · favicon_hash
                                                               │
                                                               ▼
                                                        GRAPH EDGES
                                                               │
                                                               ▼
                                                   CAMPAIGN CLUSTERING
                                                               │
                                        ┌──────────────────────┤
                                        ▼                      ▼
                                  INTERDICTION            EVIDENCE
                              reduce → QUBO → solve    artifacts → Merkle
                                        │                → Ed25519 sign
                                        ▼                      │
                                 takedown plan                 ▼
                                        │                 LEDGER ANCHOR
                                        └──────────┬────────────┘
                                                   ▼
                                              CONSOLE
                                                   │
                                                   ▼
                                    SECOND ORG inherits by kit_hash
```

---

## 2. Domain lifecycle

```
          seen in CT
               │
               ▼
        ┌─────────────┐
        │  CANDIDATE  │ ◄──── unreachable retries here
        └──────┬──────┘
               │ confirmation runs
        ┌──────┴──────┬────────────┐
        ▼             ▼            ▼
  ┌───────────┐ ┌───────────┐ ┌─────────────┐
  │ CONFIRMED │ │ DISMISSED │ │ UNREACHABLE │
  └─────┬─────┘ └───────────┘ └─────────────┘
        │
        ▼
   enriched → graph edges → campaign member
```

**A candidate is never displayed as malicious.** Grey, not red. This rule is enforced in `DESIGN.md` and it is the thing that separates an accusation from an observation.

---

## 3. Phases

### PHASE 0 — Foundation *(H0–H3)*

- **All:** repo, Docker Compose up (postgres, redis), `schema.sql` applied, both deploy targets green and empty
- **A:** **pin Qiskit versions and commit the lockfile now.** Verify `import qiskit_aer` succeeds in an isolated venv. This is the single most likely thing to eat the night.
- **A:** connect to certstream, print raw messages. **Also record 30 minutes to `data/capture.jsonl` immediately** — that is your replay file and your demo insurance.
- **D:** FastAPI skeleton + `/health`, console scaffold deployed

> **Gate: certificates visibly arriving, and a capture file on disk.**

### PHASE 1 — Detection *(H3–H9)*

- **A:** `triage.py` with all signals, allowlist first. `test_triage.py` green. **Profile it — under 5 ms per name.**
- **A:** brands.yaml with ~40 Indian brands
- **A:** replay mode working and labelled
- **B:** `confirm.py` — Playwright fetch, screenshot, DOM, login-form and POST-target detection
- **B:** `dom_structure_hash` + **its stability test** — change every string and colour on a page, hash must not move
- **C:** `packages/interdict/` — types, greedy, CP-SAT. `test_interdict.py` green.
- **D:** live feed with SSE, connection-state indicator, candidate list

> **Gate: a real candidate from the live stream, confirmed, on screen.**

### PHASE 2 — Campaign *(H9–H16)*

- **B:** all enrichers, `infra_nodes` + `graph_edges` populated
- **B:** clustering with the 0.6 threshold. Validate it does not merge everything.
- **C:** `reduce.py` (collapse + prune + top-C), `router.py`, `test_fallback.py` green
- **C:** `packages/evidence/` — Merkle + Ed25519 + verify. `test_evidence.py` green. **No chain needed for this.**
- **D:** campaign list + Cytoscape graph view
- **D:** **seed script** — a realistic 400-domain campaign. Build it now, not on the last night.

> **Gate: a seeded campaign clusters correctly and renders as a graph.**

### PHASE 3 — The contribution *(H16–H24)*

- **C:** interdiction wired to real campaigns. Plan persisted, targets ranked.
- **C:** `benchmark.py` — all backends, honest table
- **C:** Hardhat + `OrgRegistry` + `CampaignRegistry`, deploy script, two org accounts
- **B:** evidence bundle generation on confirmed domains, artifacts to disk
- **D:** plan review screen — targets, kill count, coverage, benchmark table
- **A:** ops log + metrics feeding the console

> **Gate: "take down these 4 → 387 of 400 die" appears on screen, from real graph data.**

### PHASE 4 — Ledger and second org *(H24–H30)*

- **C:** `EvidenceAnchor` + anchoring queue (non-blocking), `Attestation` + dispute
- **C:** `find_by_kit_hash` — the inheritance query
- **D:** second-org console view, provenance display
- **D:** evidence viewer + **tamper demo** — edit one byte, verification names the failing artifact
- **B:** generated abuse report, written to disk, clearly marked unsent

> **Gate: org 2 inherits a campaign from the chain, with reporter identity.**

### PHASE 5 — QAOA *(H30–H33, timeboxed)*

- **C:** `qubo.py`, `penalties.py`, `solvers/qaoa.py`, `test_ising.py`
- **Hard cutoff at H33.** If QAOA is not producing a valid plan, ship CP-SAT and reframe: *"same formulation, quantum backend pending."* Do not let this eat Phase 6.

### PHASE 6 — Freeze and rehearse *(H33–H36)*

- Bugs only. No new features.
- Design pass against `DESIGN.md` — every candidate grey, every confirmed red, every mode labelled
- **Rehearse four times.** Record a backup video on two laptops and a phone.
- Warm both deploys before presenting so nothing cold-starts on stage

---

## 4. Cut order

Behind schedule? Cut from the bottom.

```
KEEP  1. CT stream + triage + candidates          ← never cut
      2. Confirmation with evidence
      3. Campaign graph + clustering
      4. Interdiction plan (CP-SAT)
      5. Evidence bundles + tamper demo
      6. Ledger publish + second-org inherit
      7. QAOA backend
      8. Attestation / dispute flow
CUT   9. PSI cross-org overlap
```

**Items 1–4 are the product.** Cutting 7 costs you a talking point. Cutting 3 costs you the entire differentiator.

---

## 5. Demo script — 5 minutes

| Time | Beat | Say |
|---|---|---|
| 0:00 | Live CT stream scrolling, real certificates | "Every HTTPS certificate in the world is published publicly within seconds. Chrome requires it. Attackers cannot opt out." |
| 0:40 | A candidate surfaces, highlighted | "This was issued 47 seconds ago. Note it says **candidate** — we haven't accused anyone yet." |
| 1:10 | Confirmation panel opens | "Now we fetched it. Cloned ICICI login. Credentials POST to an IP that isn't ICICI. Two strong signals. **Now** it's confirmed." |
| 1:50 | Graph builds, 1 node → 400 | "Same DOM structure hash as 400 other domains. Same kit. This isn't a URL, it's an operation." |
| 2:30 | **Run interdiction** | "You can't file 400 abuse reports. Which four takedowns kill the most?" |
| 2:45 | **Plan appears: 4 targets, 387 killed, 96.7%** | "Maximum coverage. NP-hard. Four moves." |
| 3:05 | Benchmark table | "CP-SAT in production. Same formulation on QAOA — we report both, including where quantum loses." |
| 3:25 | Evidence bundle, **edit one byte, re-verify** | "Registrars reject reports without evidence. This is signed and Merkle-rooted. Change one byte of the DOM — it names the exact artifact that failed." |
| 4:00 | Second org console, empty → inherits | "Different bank. Queries the chain by kit hash. Instantly has the campaign, with proof of who reported it and when." |
| 4:30 | The timing frame | "First email of this campaign went out at 9am. We had the takedown plan at 3:02am. **Google Safe Browsing averages four and a half days.**" |
| 4:50 | Close | "Everyone blocks the URL after someone clicked it. We catch the certificate before the email is sent, and take the campaign down in four moves." |

**The peak is 2:45 and 3:25.** Four targets killing 387 domains, and evidence that catches its own tampering. Rehearse both until automatic.

---

## 6. Failure protocol

| If | Then |
|---|---|
| Live stream produces nothing in the window | Switch to replay, labelled. Seeded campaign carries beats 1:50 onward. |
| certstream endpoint is down entirely | Replay only. Say it plainly: "public endpoint is down, this is a 30-minute capture from last night." |
| Confirmation finds nothing malicious live | Use the seeded campaign. Do **not** force a verdict on a live domain to make the demo work. |
| Clustering merges everything | Raise the edge threshold. Never lower it to inflate the number. |
| QAOA fails on stage | Backend selector falls to CP-SAT. The log line shows it. **That's a feature — say so.** |
| Chain node dies | Anchoring queue shows pending; everything else continues. Say it's non-blocking by design. |
| A judge says "Netcraft does this" | "Correct — CT monitoring is established. Our contribution is campaign-level interdiction, the cross-org ledger, and the evidence chain. We didn't invent CT monitoring and we don't claim to." |
