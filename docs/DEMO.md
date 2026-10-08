# Demo script: QCertChain, 10–12 minutes

A timed shot list for the video. Each segment gives the exact clicks, the data state it needs, and what to say.
The script works with **no internet connection**. The seeded campaigns and the replay fixture are the baseline;
live CT is a bonus.

## The offline baseline (no internet at all)

`python -m scripts.e2e_stack` stands the whole demo up on this machine only: local Postgres (its own `_e2e`
database), local Redis, a local Hardhat chain, the API, the anchor worker and the built console (fonts are
self-hosted). It resets the demo, publishes Bank One's campaign on chain, then drives this exact script in a browser
that **aborts every non-localhost request**. Measured on the development laptop:

- stack up, seeded and anchored: about 13 minutes (the demo reset and 470 anchors dominate; do it before recording);
- the automated click-through, in this order, offline: **109 s**, with no request needing the internet;
- the published demo key during a presenter-paced walk: worst 60-second window **16 requests** (limit 60), no 429.

The same run is the `e2e` job in CI. Use this setup (point the browser at `http://localhost:4173`) when the venue's
network cannot be trusted; the hosted deployment is the bonus, not the baseline.

## Before recording (15 minutes, off camera)

From a PowerShell or terminal window you keep open, in the repo root (keys are read from `.env`):

```
$env:PYTHONPATH="."; .venv\Scripts\python -m scripts.demo up
```

That one command, safe to re-run (nothing starts twice), brings the whole demo up from cold and ends with `READY`:

1. **Starts everything detached**: Docker containers (Redis, certstream; starts Docker Desktop if needed), the demo
   chain on :8545 with the contracts (addresses are deterministic), the API on :8000, the four workers, the
   production console on :5180, and a **supervisor** that restarts any of them within 15 s if one dies
   (`.superpowers/watch.log`). Logs: `.superpowers/<name>.log`. Stop it all with `python -m scripts.demo down`.
2. **If the chain is new** (it lost its anchors): resets the demo data (admin key, one transaction, demo data
   only: Bank One SOC's 470-domain ICICI-themed campaign, Bank Two SOC's 50-domain HDFC-themed campaign on the same
   kit, sharing one hosting IP and one nameserver; live CT data is kept), publishes Bank One's campaign and waits for
   the anchors. Otherwise it keeps the anchored state.
3. **Warms** every page the script below visits, for both organisations: the solver benchmark for every k on the
   slider (cold, the first one takes up to 30 s; warm, under 1 s), sweep, graph, evidence verification, the ledger
   lookup. "Run again" on camera stays a genuine live run.

Measured on the presenting laptop (2026-10-09): from cold to `READY` in about 14 minutes; re-run on a running stack,
about 70 s.

4. **Optional: replay as the stream source** (admin): `POST /admin/stream/mode {"mode":"replay","speed":360}` with
   `REPLAY_FILE=data/replay/ct_24h.jsonl.gz` (the finalized capture: 22.6 hours of recorded CT, deduplicated and
   sorted, about 3.4 minutes at 360x). The UI labels replay throughout.
5. **Right before presenting:** `python -m scripts.demo flush` drops the stale page-fetch backlog (those domains stay
   candidates). On one laptop the fetcher (~240/h) cannot keep up with the live feed (~600 candidates/h), so the
   backlog only grows and the top bar would show the enrich stage as degraded; flushed, the running enrich worker
   stays under the "ok" line for over an hour. Keep the enrich worker running.
6. **Readiness:** `python -m scripts.demo check` must print `READY` (API and database, chain and anchor queue, CT
   stream, enrich backlog, both organisations' campaigns, console).
7. Two browser profiles: profile A signed in with **Bank One's** key, profile B with **Bank Two's**. Window
   size 1280x800.

Measured on the presenting laptop (2026-10-09, live Supabase in Singapore): the full click-through below, automated
in a real browser against this stack (`e2e/test_demo_path.py`), passes in **61 s** with no page error and no request
leaving the machine except to the API; after warming, the median API call is about 0.5 s, the solver table and
evidence verification under 0.7 s.

Required state at "Action": `scripts.demo check` prints READY (both orgs seeded, Bank One's campaign anchored, every component ok).

---

## 0:00–2:00 Ingest and triage (profile A)

| Time | Click | On screen | Say |
|---|---|---|---|
| 0:00 | Open the console (architecture page) | The system diagram with live status squares, and certs/s on the first edge | "Everyone blocks the URL after someone clicked it. We catch the certificate before the email is sent." |
| 0:20 | Point at the three panels under the diagram | Nothing is ever sent · Two strong signals to confirm · Hashes on-chain, never content | "Three positions the database itself enforces, not just the code." |
| 0:40 | Click the **Triage** node | Live queue, replay label visible | "Every certificate that is logged anywhere passes through here in under 5 ms." |
| 1:00 | Hover a candidate's score | The score breakdown: brand token, keyword, TLD | "A candidate is *suspicious, not verified*. Never red. Triage only nominates." |
| 1:20 | Point at a Cyrillic homograph row (e.g. `xn--bi-doc.co.in`) | The `skeleton_exact` signal | "A homograph of SBI's own domain. An exact confusable-skeleton match is its own strong signal." |
| 1:40 | Segmented filter → Confirmed | Confirmed rows in red, with the reasons | "Confirmed means we fetched the page and found two strong signals. The database rejects anything less." |

## 2:00–5:00 Campaign graph and interdiction (profile A)

| Time | Click | On screen | Say |
|---|---|---|---|
| 2:00 | Campaigns → the 470-domain campaign | The graph: domains around shared infrastructure | "470 domains, one operator. We found them by shared kit, hosting, nameservers and registrar." |
| 2:30 | Point at the legend | Filled squares = takedown targets (IP, nameserver, registrar); dashed circles = evidence only | "We can ask a host, a DNS provider or a registrar to act. We cannot take down a hash, so it is evidence, not a target." |
| 3:00 | Drag the budget slider from 1 to 15 | Targets light up and domains go dark; the coverage curve flattens toward the "440 reachable" line | "Which k takedowns kill the most domains? That is maximum coverage, which is NP-hard." |
| 3:40 | Set k = 5 | **"k = 5 covers 382 of 470 domains (440 reachable)"**, "16,108,764 possible 5-target plans here (74 targetable nodes) ... solved exactly", and the band "30 unreachable at any k" | "Five takedowns cover 382 of 470. Thirty sit only on shared DNS, so no budget reaches them: the best any plan can do is 440. The solver finds the exact optimum among sixteen million plans." |
| 4:15 | Read "Why this plan" | Each target, its route (hosting abuse / DNS abuse / registrar suspension) and the domains it covers | "Every target says who to ask and why." |
| 4:40 | Domain → Abuse report | The generated report, marked **not sent** | "We generate the request. We never send it. One false positive would take a real business offline." |

## 5:00–7:00 Solvers and the formulation (profile A, same page)

| Time | Click | On screen | Say |
|---|---|---|---|
| 5:00 | Scroll to Solvers | Greedy, CP-SAT, simulated annealing, QAOA and exhaustive search: covered, targets, ms, gap vs CP-SAT | "Same problem, five solvers, every row shown. Exhaustive search checks every plan after reduction and confirms CP-SAT's optimum." |
| 5:40 | Click **Run again** | It re-runs live (seconds for QAOA) | "Nothing pre-baked: a judge can run it." |
| 6:10 | Scroll to the formulation panel | QUBO variables, qubits, circuit depth, what the reduction discarded | "CP-SAT is production. The same QUBO runs on QAOA. The claim is about scaling, not speed today." |

## 7:00–9:00 Evidence and the ledger

| Time | Click | On screen | Say |
|---|---|---|---|
| 7:00 | A confirmed domain → Evidence | Artifacts with hashes; the Merkle tree with its root | "Screenshot, DOM, certificate, DNS, WHOIS: each hashed into one Merkle root, signed with Ed25519." |
| 7:30 | **Verify** | Three green checks: root, signature, anchored hash on chain | "The root on chain matches the bytes we hold. Only the hash is on chain, never the content." |
| 7:50 | **Tamper (demo)** | FAIL: expected vs actual hash with differing characters marked; the root and the chain no longer match | "Flip one byte, in memory: the evidence on disk is never touched, and the proof breaks." |
| 8:10 | **Restore** | Green again | |
| 8:20 | **Switch to profile B (Bank Two)** | A populated console, Bank Two's own 50-domain campaign | "A second bank. It cannot see Bank One's data: that is a 404, not a 403." |
| 8:35 | Ledger → paste the kit hash from its own campaign → Look up | Bank One's report: IOC root, kit hash, 470 domains, confidence, reporter, time. **No names, no IPs, no content** | "Bank Two found Bank One's campaign through the ledger, without receiving any of its data. One bank's detection protects the next." |
| 8:50 | **Corroborate** (or Dispute) | The queued write, signed as Bank Two | "Its signature is its own key's. Nobody can sign as another bank." |

## 9:00–10:00 Email correlation (profile A)

| Time | Click | On screen | Say |
|---|---|---|---|
| 9:00 | Email headers → paste `services/email/samples/p01_display_spoof_dmarc_fail.eml` | Parsed headers with pass/fail; signals by strength; the gate "2 strong required – 1 found" | "A spoofed SBI notice: suspicious, not yet malicious, because only one strong signal is present." |
| 9:30 | Point at the link domain | Its triage score and its candidate link | "Its link is now a candidate. When the pipeline confirms it, this email is re-scored to malicious automatically: the same two-strong rule." |

## 10:00–12:00 Metrics and the report

| Time | Click | On screen | Say |
|---|---|---|---|
| 10:00 | Metrics | Precision at a 1:1000 base rate, noted as not balanced-set | "At the real base rate, triage alone is imprecise, which is why it only nominates. Confirmation protects precision." |
| 10:30 | The threshold sweep chart | 0.20–0.80: recall, false positives, candidates per hour | "We chose 0.35 from this sweep: a lower threshold costs fetches, not accusations." |
| 10:50 | Lead time figure | Lead time over OpenPhish, measured, or "Not measured yet" with the reason | Say only what is on screen. |
| 11:10 | Per-stage response times | CT seen → candidate → confirmed → campaign → plan → bundle → anchored | |
| 11:30 | System health | API and database region, round trip, p95 per endpoint | "Measured, not asserted." |
| 11:45 | `docs/REPORT.md` | | "Every number here comes from a measurement script, and the report says what we could not measure." |

## If something fails on camera

- **The chain is down:** the ledger panel says so and shows the queued writes. Detection, clustering and
  interdiction carry on; say exactly that.
- **No live certificates:** the replay is the baseline and is labelled.
- **Rate limit (demo key, 60/min):** the console polls once per 5 s; a 429 shows a grey retry notice and backs off.
