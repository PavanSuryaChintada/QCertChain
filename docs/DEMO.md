# Demo script: QCertChain, 10–12 minutes

A timed shot list for the video. Each segment gives the exact clicks, the data state it needs, and what to say.
The script works with **no internet connection**. The seeded campaigns and the replay fixture are the baseline;
live CT is a bonus.

## Before recording (5 minutes, off camera)

1. **Reset the demo chain.** Chain state is not transactional, so it is reset separately: stop the Hardhat node,
   start it again (`cd contracts && npx hardhat node`), then
   `npx hardhat run scripts/deploy.ts --network localhost`. The contract addresses are deterministic, so
   nothing else changes.
2. **Reset the demo data** (admin key, one transaction, demo data only):
   `curl -X POST localhost:8000/admin/reset -H "X-API-Key: $QCC_KEY_ADMIN"`.
   It gives Bank One SOC its 400-domain ICICI-themed campaign and Bank Two SOC its 50-domain HDFC-themed campaign
   on the same kit, sharing one hosting IP and one nameserver. Live CT data is kept.
3. **Publish Bank One's campaign to the ledger:** `POST /ledger/publish/{campaign_id}` with Bank One's key. Wait
   for the anchor worker to drain (the top bar's ledger queue reaches 0).
4. **Warm the benchmark:** open the Bank One campaign page once, so the solver table is cached; "Run again" stays
   live.
5. **Replay as the stream source** (admin): `POST /admin/stream/mode {"mode":"replay","speed":360}` with
   `REPLAY_FILE=data/replay/ct_live.jsonl.gz`. That plays 24 hours of recorded CT in about 4 minutes, and the UI
   labels it as replay throughout.
6. Two browser profiles: profile A signed in with **Bank One's** key, profile B with **Bank Two's**. Window
   size 1280×800.

Required state at "Action": both orgs seeded, Bank One's campaign anchored, replay running, `/health` green.

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
| 2:00 | Campaigns → the 400-domain campaign | The graph: domains around shared infrastructure | "400 domains, one operator. We found them by shared kit, hosting, nameservers and registrar." |
| 2:30 | Point at the legend | Filled squares = takedown targets (IP, nameserver, registrar); dashed circles = evidence only | "We can ask a host, a DNS provider or a registrar to act. We cannot take down a hash, so it is evidence, not a target." |
| 3:00 | Drag the budget slider from 1 to 10 | Targets light up and domains go dark; the coverage curve flattens | "Which k takedowns kill the most domains? That is maximum coverage, which is NP-hard." |
| 3:40 | Set k = 5 | **"2^19 candidate subsets, solved in … ms"** and **400 / 400 covered** | "Five takedowns end all 400 domains. CP-SAT proves it optimal in milliseconds." |
| 4:15 | Read "Why this plan" | Each target, its route (hosting abuse / DNS abuse / registrar suspension) and the domains it covers | "Every target says who to ask and why." |
| 4:40 | Domain → Abuse report | The generated report, marked **not sent** | "We generate the request. We never send it. One false positive would take a real business offline." |

## 5:00–7:00 Solvers and the formulation (profile A, same page)

| Time | Click | On screen | Say |
|---|---|---|---|
| 5:00 | Scroll to Solvers | Greedy, CP-SAT, annealing and QAOA: covered, targets, ms, gap vs CP-SAT | "Same problem, four solvers, every row shown, including where QAOA loses." |
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
| 8:35 | Ledger → paste the kit hash from its own campaign → Look up | Bank One's report: IOC root, kit hash, 400 domains, confidence, reporter, time. **No names, no IPs, no content** | "Bank Two found Bank One's campaign through the ledger, without receiving any of its data. One bank's detection protects the next." |
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
