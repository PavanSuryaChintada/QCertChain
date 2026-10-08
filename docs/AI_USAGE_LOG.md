# Development AI-usage log

Kept live from Task 1 onward (not reconstructed). One entry per task: what the AI (Claude Code, model Opus 5.5) did, what the owner decided, and what was verified by running code rather than asserted.

Format: **AI did** · **Owner decided** · **Verified by** · **Rulings** (AI judgement calls, also in the plan ledger).

---

## Pre-build (2026-10-06) — context for the entries below

- **AI did:** read the 17 baseline spec files; identified conflicts with the challenge brief (email scanning was out of scope; report format unspecified; name placeholder; triage training data access); probed infrastructure (Supabase pooler config via management API; public certstream dead — connects, 0 certs in 30 s; CT log list; direct RFC 6962 polling rate); wrote the design spec and the 27-task implementation plan.
- **Owner decided:** D1 add email-header module · D2 paste/upload only · D3 Markdown report from measured metrics · D4 name QCertChain · D5 rules-first triage then train · D6 deploy later on explicit go-ahead · D7 Supabase DB · D8 self-hosted certstream-server-go v1.10.1, recovery off, fingerprint dedup · D9 takedown targets ip/nameserver/registrar · Native (inline) execution · accepted four baseline-spec corrections (Attestation first-org bug; org keys off account #0; 5+ char lookalike token floor; free-CA+new-domain rule moved to confirmation).
- **Owner standing instructions (2026-10-06):** never trim CT logs without per-operator volume from the capture; be a good CT citizen (confirm #104 fix, report outbound request rate); flag the email cold-start gate with measured recall before changing anything; verify the Supabase pooler hostname against the dashboard/API; Phase 0 order = capture → schema+RLS → rename; deploy waits for explicit go-ahead.

---

## Task 1 — repo restructure, rename, Python env, config

- **AI did:**
  - Moved specs into `docs/`, `CLAUDE.md`, `contracts/`, `apps/`, `services/api/`.
  - Renamed SEVER → QCertChain (sed, then grep shows zero hits).
  - Created a Python 3.11 venv and pinned requirements.
  - Wrote `services/config.py` test-first.
  - Pulled the CT capture forward per the owner's priority order. It needed Task 3's certstream config and `capture.py`, so those landed early.
- **Verified by:**
  - `test_config.py`: RED (ModuleNotFoundError), then GREEN, 2/2 passing.
  - Grep for leftover "SEVER" strings returns no hits.
  - certstream-server-go v1.10.1 source read at tag:
    - `DefaultMaxPartialWait = 1 * time.Minute`: partial tiles are deferred, not fetched every second.
    - Checkpoint backoff is between 2 and 15 seconds.
    - Release notes list the #104 fix and the #114 off-by-one fix.
- **Rulings:**
  - Pinned `web3==7.10.0` instead of the plan's 7.6.0, which requires `websockets<14` and conflicts with the TRD pin `websockets==14.1`.
  - The CT capture runs before the rest of Phase 0, per the owner's order.
- **Observed:** GoDaddy CT logs (aquamarine*) answered HTTP 429 at startup, and certstream-server-go dropped those workers. This is a coverage gap that goes into the capture report.

## Task 2 — Supabase schema + RLS, test Postgres

- **AI did:**
  - Extended `schema.sql` with:
    - `domains.source`
    - stage timestamps `ct_seen_at`, `candidate_at`, `campaign_joined_at`
    - a DB check that blocks `confirmed` without stored signals
    - a unique certificate fingerprint
    - the `registrar` node kind, with takedown routes limited to hosting, dns and registrar
    - benchmark columns `qubit_count`, `is_best`, `error`, `targets`
    - `fallback_from`
    - the `known_kits` and `email_analyses` tables, with a DB check that malicious needs 2 strong signals
    - an idempotent FK
    - RLS on every table
  - Added a `postgres:17` test container. Tests refuse to run against Supabase.
- **Verified by:**
  - `test_schema.py`: RED 7/9, then GREEN 9/9.
  - Supabase pooler host in `.env` == live project pooler config from the management API (`aws-0-ap-southeast-1.pooler.supabase.com`). Session mode on :5432 connects (PostgreSQL 17.11).
  - Applied to Supabase: 18 tables, 0 without RLS.
  - Live probe: anon REST read returned `[]` with a row present, and anon REST insert was rejected with `42501`. Probe row deleted.
- **Rulings:** none beyond the plan.
- **Incident:** a Python edit of `docker-compose.yml` used the Windows default cp1252 encoding and mangled the em dashes. I repaired it and verified there is no remaining mojibake. All file writes now pass `encoding="utf-8"` explicitly.

## Task 5 — brands, allowlist

- **AI did:** wrote `brands.yaml` (40 Indian brands, 50 legit domains), the Tranco fetch script, `brands.py` (brand index, allowlist, shared eTLD+1 extractor), and a DNS-verification script for the brand domains.
- **Verified by:**
  - `test_brands.py`: RED, then GREEN 7/7.
  - All 50 legit domains resolve in DNS.
  - Tranco list `56WKN` fetched.
- **Found by testing, fixed test-first:**
  - tldextract skips the PSL private section by default, so `x.github.io` would have collapsed to `github.io`.
  - 11 subdomain-hosting platforms are in Tranco but not in the PSL (weebly.com, 000webhostapp.com, surge.sh, …). Without the fix, every phishing subdomain on them would have been allowlisted with a score of 0. Now listed in `data/shared_hosting.txt` and treated as public suffixes.
- **Rulings:**
  - The allowlist size assertion is ≥ 99,000 (the plan said ≥ 100,000), because 100k Tranco rows normalise to 99,627 registrable domains.
  - `bank.in` is allowlisted as a zone (RBI-restricted registry).
  - Generic tokens were dropped from the spec's example: `netbanking` stays a phishing keyword rather than an HDFC token, and `axis` and `kite` were too generic.

## Task 6 — triage (release gate)

- **AI did:**
  - Wrote the confusable skeleton (`homoglyph.py`).
  - Wrote the 12-feature extractor shared with training (`services/ml/features.py`).
  - Wrote rules triage with allowlist first and TRD §2 weights, unchanged (`triage.py`).
  - Wrote the real-traffic benchmark (`scripts/bench_triage.py` → `reports/triage_bench.json`).
- **Verified by:**
  - `test_triage.py`: RED (module missing), then GREEN. It now has 50 tests:
    - plan gates: legit never a candidate, phishing always a candidate, < 5 ms average
    - 7 regressions built from real false positives in the capture
    - homoglyph, brand-TLD, unknown-TLD and warm-up tests
  - Benchmark on 200k unique real CT names: p50 0.29 ms, p95 1.5 ms, p99 4.8–5.3 ms (varies run to run on this laptop). Max 108 ms, consistent with the ~95 ms machine stalls measured with no triage code running.
  - Candidate volume: 50 → **10 per 200k names**, about 1.5 per minute of stream.
- **Found by measuring on real traffic, each fixed test-first:**
  1. **Double counting:** one substring hit counted as both an exact token and a lookalike. This flagged `growww.today` (Dutch, unrelated) and `idfcbank.com`, which is 1 edit from `hdfcbank`.
  2. **Lookalike on common words:** `onlines` is 2 deletions from `onlinesbi`. A segment shorter than the token now gets 1 edit at most.
  3. **Hex split into `vi`:** splitting segments on digits turned hex like `vi0svszw` into the token `vi`. Digits now stay inside segments, and edge digits are stripped (`sbi1` → `sbi`).
  4. **AWS's own domains** were flagged. Added `amazonaws.com`, `amazonwebservices.com/.com.cn/.eu` and `amazongamelift.com`, ownership checked via NS on `awsdns-*`. A bare public-suffix name (an S3 access point) now scores 0.
  5. **Brand-owned TLDs** (`.sbi`, `.jio`, `.amazon`, `.aws`) are now allowlisted, with the sponsor of each verified in IANA's root database.
  6. **ASCII `l→i`** turned `vl` into `vi`. Homoglyph matches on 2–3 letter tokens now need real non-ASCII characters.
  7. **Unknown-TLD bug:** a TLD missing from the PSL snapshot was being treated as "is a public suffix" and scored 0. New gTLDs would never have been flagged. Fixed and tested.
  8. **4-second first call:** the lazy allowlist build landed on the first live certificate. Added `warm()`, which workers call at startup.
- **Rulings:** listed in the ledger. Weights unchanged; every change is to feature extraction, per the plan's rule.

## Task 3 — self-hosted certstream, 30-minute capture, CT-citizenship report

- **AI did:**
  - Ran certstream-server-go v1.10.1 (recovery off) and the 30-minute capture.
  - Wrote `scripts/ct_capture_report.py`: per-operator and per-log volume from Prometheus snapshots, tiled vs RFC 6962 from Google's log list, measured inbound bytes, derived request rate.
  - Compacted the capture to a 1.5 GB replay file without DER/chain; the raw 7.6 GB is kept, git-ignored.
- **Verified by measurement:** results are in `reports/ct_capture/report.md`.
  - **Volume:** 1.27M log entries processed (689/s); 920k messages delivered to the capture client; **401k unique certificates (219/s)**.
  - **Tiled share:** **37.4%** of entries. All 6 Let's Encrypt tiled logs delivered.
  - **Load on CT log operators:** **14.8 Mbit/s** inbound, measured; **5–21 req/s**, derived.
  - **#104 fix:** partial-tile deferral of up to 60 s, confirmed in the v1.10.1 source.
- **Corrected a claim before it shipped:** the first draft attributed the processed-vs-delivered gap to cross-log dedup. Counting showed:
  - The server does not dedup: 56% of messages were duplicate deliveries.
  - 27% of entries were never delivered to the full-stream client.
  - On the lite stream, 92.8% is delivered.
  - The report now says the drop cause is inferred, not measured.
- **Owner instruction honoured:** no `excluded_logs` proposed. Coverage gaps are listed as involuntary: GoDaddy 429s, plus 0-entry logs at Cloudflare, Sectigo and IPng.

## Task 7 — interdict package: types, greedy, CP-SAT, validation (release gate)

- **AI did:** wrote the standalone MIT package `packages/interdict`: `Problem`/`Plan` types, greedy, CP-SAT and the validation gate.
- **Verified by:**
  - `test_interdict.py`: RED, then GREEN 569/569.
  - The tests cover: 500 random instances (never over budget, coverage exact); CP-SAT equals brute force on 60 small instances; greedy meets the 1−1/e bound against brute force; k=0 and k>nodes; unreachable domains; fractional weights.
- **Found by measuring, not assumed:**
  - On the plan's random 400-domain instance, CP-SAT needs **3–4 s on this 4-core laptop to *prove* optimality**, although greedy already finds the optimum.
  - Fixes: collapse identical dependency signatures (exact), warm-start from greedy, never return worse than the warm start, and **report OPTIMAL vs FEASIBLE with the gap** so a time-limited plan is never presented as proven.
  - Campaign-shaped 400-domain instances (Zipf IPs/NS/registrars) solve to OPTIMAL in < 1 s.
- **Rulings:** perf test split (campaign-shaped must be OPTIMAL under 1 s; hard random must respect a 0.9 s limit and report its gap). See ledger.

## Task 8 — reduction, QUBO, annealing, router with fallback, benchmark (release gate test_fallback)

- **AI did:**
  - Wrote reduction (collapse → prune dominated → top-C), the QUBO, simulated annealing, the fallback router (every exception falls through; greedy last; validation gate) and the honest benchmark (every backend run alone, failures are rows, exactly one `is_best`).
- **Verified by:** `test_reduce`, `test_qubo` and `test_fallback`: RED, then GREEN. The interdict suite is at 591/591.
- **Spec bug found and corrected (ruling, flagged to the owner): the NPHARD §6 QUBO rewards over-coverage.**
  - Counter-example: g1={a,b} w5, g2={c} w1, k=2. The spec energy picks {a,b} (energy −11) over the optimum {a,c} (energy −6).
  - Replaced with the x-only, second-order inclusion–exclusion formulation, which is exact for ≤ 2 dependencies per group.
  - A brute-force test asserts the ground state equals the true optimum on 25 random instances.
  - Qubits: ≤ 12 instead of 26.
  - Correction note added to `docs/NPHARD.md` §6; the original text is kept.

## Task 9 — QAOA backend

- **AI did:**
  - Installed the pinned qiskit 1.2.4 and qiskit-aer 0.15.1 (clean install) and committed `requirements.lock`.
  - Implemented `qubo_to_ising` (x = (1−z)/2, little-endian) and QAOA:
    - p = 3 layers
    - warm start biased toward the greedy plan (Ry, ε = 0.25)
    - COBYLA with 150 iterations and a wall-clock timeout inside the cost function
    - 1024 shots, keeping the best sampled bitstring
    - a 24-qubit guard; qiskit imported lazily
- **Verified by:**
  - `test_ising.py`: RED (missing function), then GREEN 6/6. The **Ising energy plus offset equals the QUBO energy for every bitstring** (brute force), and the energy ordering is identical.
  - Interdict suite: 597/597.
- **Found by measuring, fixed test-first:**
  - QAOA took 17–18 s on a 12-qubit campaign problem, over the 15 s target. Aer EstimatorV2 cost 190 ms per evaluation, almost all per-call overhead.
  - Switched to one transpiled circuit with `save_expectation_value`: 57 ms per evaluation. Now 11.5 s.
  - The test asserts under 15 s.
- **Observation for the owner:** on a seed where every domain uses one of 3 registrars, "report to all 3 registrars" kills 400/400, and all four backends find it. Whether that's realistic depends on how many registrars real campaigns spread across. The seed was not tuned to make the problem harder.

## Task 10 — evidence package (release gate)

- **AI did:**
  - Wrote the standalone `packages/evidence`:
    - domain-separated SHA-256 Merkle tree, with leaves binding artifact name + content hash and sorted by name
    - Ed25519 signature over the root
    - `verify_bundle`, which names each failing artifact with both hashes and the reason (`hash_mismatch` / `missing` / `unexpected`)
    - the Markdown abuse-report renderer, ending "Generated by QCertChain — not sent."
  - Generated the collector key into `.env` (not committed).
- **Verified by:** `test_evidence.py`: RED, then GREEN 11/11. Covered:
  - a one-byte tamper names `dom.html`
  - a wrong key fails the signature
  - a forged root fails
  - a deleted file is reported missing, an injected file unexpected
  - the root doesn't depend on insertion order, but renaming an artifact changes it
  - path traversal in artifact names is rejected
  - the report never claims it was sent
- **Rulings:**
  - Leaves bind the artifact name (not just the content hash), so swapping two files' names is detected.
  - Expected hashes come from the database, never from the bundle directory itself.

## Task 11 — page fingerprints

- **AI did:** wrote `fingerprint.py` with the stdlib HTML parser:
  - `dom_structure_hash`: tag names and nesting only; text, attributes, comments and script/style bodies are dropped; void tags are normalised
  - form extraction, with the action resolved against the page URL and the method
  - page title
  - favicon mmh3 hash (Shodan convention)
  - JS bundle hashes
  Fixture: a realistic cloned bank login page.
- **Verified by:** `test_fingerprint.py`: RED, then GREEN 12/12.
  - **The hash does not move** when every string, colour, image URL and class/id/style/alt attribute is changed, or when the brand name is swapped.
  - **It does move** when one wrapper `<div>` is added.
  - Malformed HTML doesn't crash.

## Task 12 — fetch, enrichers, confirmation gate

- **AI did:**
  - **`fetch.py`:**
    - Playwright first, with an httpx fallback.
    - Observe only: no interaction with the page.
    - Redirects followed manually (≤ 5 hops, loops detected), with the chain recorded.
    - Honest User-Agent; a per-host rate limiter is injected.
  - **`enrichers.py`:**
    - DNS, RDAP (registrar, abuse contact, registration date), Team Cymru ASN, and the stdlib TLS chain.
    - Each enricher fails independently, and any failure sets `partial`.
  - **`confirm.py`:**
    - The pure `analyze_page` gate: confirmed needs ≥ 2 strong signals.
      - strong: credential POST to a foreign origin, known-kit DOM hash, brand favicon
      - moderate: brand in the title, obfuscated JS, password field
      - weak: domain < 30 days old, free CA
    - `confirm()` runs the fetch and the enrichers concurrently.
- **Verified by:** `test_confirm` (14), `test_fetch` (5) and `test_enrichers` (6 incl. 2 live network): RED, then GREEN. Service suite: 119/119. Covered:
  - one strong signal never confirms; moderate-only never confirms
  - a POST to the brand's real domain, or to the same site, is not foreign
  - after a redirect, the final URL is the origin
  - parked pages and tiny error pages are `unreachable`; a blog is `dismissed`
  - an unreachable fetch never guesses; a rate-limited host stays a candidate
  - the fetch and the enrichers really run concurrently
  - Live checks: DNS/ASN/RDAP/TLS against example.com; Playwright fetched example.com (HTTP 200, 37 KB screenshot).
- **Rulings:**
  - **ASN via Team Cymru, not pyasn.** pyasn needs MSVC on Windows; Team Cymru is the other spec-listed source.
  - **The TLS issuer comes from a verified handshake (stdlib),** to avoid adding `cryptography`.
  - **One or more strong signals without enough for confirmation stays `candidate`.** It is not dismissed.
  - **Weak-only evidence is `dismissed`.** Free CA plus young domain describes a large share of all certificates.

## Task 13 — repository layer, triage worker

- **AI did:** wrote `db.py` (Supabase engine), `repo.py` (plain SQL against `schema.sql`; the caller owns the transaction) and `triage_worker.py`:
  - Consumer group on `certs:raw`, batches of 500.
  - Only candidates are written to Postgres.
  - New candidates go to `enrich:queue`.
  - Every triage result is published for the live feed, with its source labelled (live/replay/seed).
  - Warm-up runs at startup.
- **Verified by:** `test_repo` (6) and `test_triage_worker` (2): RED, then GREEN, against local postgres:17. Covered:
  - certificate upsert is idempotent on fingerprint
  - a repeat name (precert + final cert from different logs) gives one row, and first-seen/`candidate_at` are never overwritten
  - **the database rejects `confirmed` without stored signals**
  - node/edge upserts are idempotent, with a `domain_count`
  - allowlisted names never touch Postgres
  - the replay source is labelled in the DB and in the feed

## Task 14 — graph edges, clustering, campaign upsert

- **AI did:**
  - `build.py`: `edges_for` with the spec weights (registrar 0.15), `TAKEDOWN_ROUTE`, an IOC Merkle root, and `recluster`:
    - campaign ids stay stable across runs
    - labels are `CAMP-NNNN`
    - `campaign_joined_at` is set only when a domain's campaign changes
  - `cluster.py`: NetworkX components over edges ≥ 0.6, merged only when two components share ≥ 2 distinct medium-weight (ASN-class) nodes; a single domain is not a campaign.
- **Verified by:** `test_cluster.py`: RED, then GREEN 9/9. Covered:
  - shared ASN or issuer alone never merges; one medium edge doesn't merge, two do
  - weak infrastructure (registrar) is still listed as campaign infrastructure
  - 500 domains cluster in under 2 s
  - DB test: a stable campaign id on re-run, plus the label, kit hash and a 64-hex IOC root

## Task 15 — enrich worker, evidence pipeline, labelled seed

- **AI did:**
  - `pipeline.py`: `persist_result` (verdict → enrichment → edges → known kit → recluster → bundle → unsent report → anchor queue), with bundle prep split from the bulk insert.
  - `enrich_worker.py`:
    - per-host rate limit through a Redis `SET NX EX` lock
    - a rate-limited fetch is re-queued with a delay, never recorded as a verdict
    - forced re-confirm via a `force:` prefix
    - one bad domain never stops the worker
  - `seed.py` plus a kit template.
- **Verified by:** `test_pipeline` (3), `test_seed` (6) and `test_enrich_worker` (3): RED, then GREEN. Service suite all green. Covered:
  - all 400 seed domains confirmed **by the real gate** with ≥ 2 strong signals; one campaign; 12 IPs, 4 nameservers, 3 registrars, 1 kit
  - the shared DNS provider is never a node
  - the seed is deterministic
  - only `.example` names and documentation IPs are used
- **Found by measuring, fixed test-first:**
  - The Supabase round trip from this machine is **109 ms** (local Docker: 17 ms).
  - The first seed issued **10,341 SQL statements**, which would be about 19 minutes on Supabase.
  - Rewritten with `jsonb_to_recordset` bulk writes: **19 statements**, 19 s in total, most of it Python file I/O and HTML parsing.
  - The test asserts fewer than 40 statements for 400 domains, independent of network speed.
- **Ruling (safety):** the seed uses the reserved `.example` TLD, RFC 5737 IPs and RFC 5398 ASNs, rather than realistic `.top` names. A seed labelled "confirmed phishing" must never be able to name a real registrant.

## Task 16 — API

- **AI did:**
  - Updated `API_CONTRACT.md` first: registrar targets, marginal `kills`, `notes`, email §9, sources.
  - Wrote the FastAPI app:
    - RFC 7807 problem+json on every error
    - warm-up at startup
    - Pydantic v2 models field-for-field with the contract
    - routes for stream state and mode, SSE live feed (token bucket of 20/s; a candidate waits for a slot instead of being dropped), candidates, domain detail (one joined query), force re-confirm, campaigns, the Cytoscape graph (1,000-node cap), interdiction (409/422/404 per contract), plans, the benchmark (every row persisted), evidence (artifact download only for recorded names, verify, report with `sent: false`), metrics, ops log, seed
  - Plan `killed_domain_ids` and `notes` are stored as columns, not in the ops log.
- **Verified by:**
  - `test_api.py`: RED (modules missing), then GREEN 18/18.
  - Full repo suite green.
  - Live smoke against **Supabase** through the session pooler: `/health`, `/metrics`, `/candidates`, `/stream/state`, and a 404 problem+json.
- **Found by running it, fixed test-first:** `/stream/state` reported `connected` from a heartbeat hours old (my earlier smoke run left it in Redis). The console would have shown LIVE for a dead stream. Now three missed heartbeats (15 s) read as `down` with rate 0, in both `/stream/state` and `/metrics`.
- **Incident:** the Supabase direct host (IPv6) stopped resolving from this network. Schema changes are now applied through the IPv4 session pooler, which supports DDL.

## Task 17 — Solidity contracts (Hardhat)

- **AI did:**
  - Set up Hardhat 2.29.1 (Node 22) with BUILD_SPEC's config and a standard tsconfig.
  - Wrote OrgRegistry, CampaignRegistry, EvidenceAnchor and Attestation verbatim from BUILD_SPEC §2–5, plus the accepted Attestation fix.
  - Wrote the deploy script (`deployments/localhost.json` is the only place addresses live) and a Dockerfile that deploys on boot.
  - Set the `.env` org keys to Hardhat accounts #1/#2. These are public local test keys; account #0 is the admin and is not an org.
- **Verified by:**
  - `npx hardhat test`: RED (no artifacts), then GREEN 18/18, including THE INHERITANCE TEST (`findByKit`) and THE TAMPER TEST (`verify` false for a tampered root).
  - **The Attestation fix is proven, not assumed:** with BUILD_SPEC §5's original logic swapped back in, the test fails (only org1 is recorded and org2's dispute is lost); with the fix it passes.
  - A local deploy registered orgs whose addresses equal those derived from the `.env` keys.
- **Environment note:** the global npm registry is `registry.npmmirror.com`. The install took 13 minutes at 2–4 minutes per large package. Left unchanged; flagged to the owner.

## Task 18 — ledger service, anchor queue, ledger API

- **AI did:**
  - `ledger_service.py` (web3.py):
    - addresses from `deployments/localhost.json`, ABIs from committed `contracts/abi/` (exported from the build)
    - on-chain ids are keccak(uuid); custom errors are decoded by selector
  - `anchor_worker.py`:
    - drains `anchor_queue` with a savepoint per item
    - exponential backoff via the new `next_attempt_at` column
    - `AlreadyPublished`/`AlreadyAnchored` treated as idempotent success
    - updates `published_tx`/`anchored_tx` and `ledger_events`
  - Ledger routes:
    - publish, attest and corroborate are **queued (202)**, with no chain call inside a request
    - `by-kit` maps on-chain ids back to local campaigns and returns `local_telemetry_received: false`
    - a down chain gives 503 with the queue depth
    - the API keeps serving when the deployment file is missing
- **Verified by:** `test_ledger.py`: RED, then GREEN 10/10.
  - **5 tests against a real Hardhat node:**
    - inheritance by kit, with reporter name and corroboration
    - anchor + verify + tamper (false) + re-anchor rejected
    - org2 dispute
    - **end to end:** seed → publish via API → anchor worker → org 2's kit query returns the campaign, and `published_tx` matches
  - A fake ledger proves that with the chain down, items stay queued with backoff and nothing blocks.

## Task 19 — email-header module

- **AI did:**
  - `parse.py` (stdlib `email`, never raises, absent headers recorded), `signals.py` (spec §3.2) and `analyze.py` (≥ 2-strong gate; correlation creates `source='email'` candidates, never confirmed domains).
  - API: `POST /email/analyze` (JSON or multipart, 2 MB → 413; new candidates queued for normal confirmation), list, detail.
  - Labelled synthetic sample set: 8 phishing, 5 legit, all reserved `.example` names. Labels are ground truth, not expected verdicts.
  - `scripts/email_eval.py` → `reports/email_eval.json`.
- **Verified by:** `test_email.py`: RED, then GREEN 19/19. Covered:
  - the gate: moderate-only never malicious; legit never malicious, even warm
  - robustness: garbage, body-only paste, folded headers, non-UTF-8
  - DB correlation creates only candidates
  - API: JSON, multipart, 413, list and detail
- **Found by measuring, fixed test-first:** the display-name brand matcher missed "Income Tax Department" (token `incometax` has no space). It now compares with spacing and punctuation removed; short tokens still need a whole word.
- **Owner-requested measurement, gate NOT changed:**
  - Cold start: recall **0/8** (7/8 suspicious, 1/8 clean).
  - Warm (link domains already confirmed by the CT pipeline): **6/8**.
  - Legit rated malicious: **0/5** in both conditions.
  - Options were reported to the owner; the rule stays until the owner decides.
- **Ruling:** Return-Path and Message-ID mismatches are not counted when DMARC passes. An aligned pass explains third-party ESP sending; this keeps the legit ESP sample clean.

## Task 20 — console shell, tokens, stream rail, verdict chip, mode indicator

- **AI did:**
  - Vite + React 18 + TS + Tailwind (mapped only to DESIGN.md's locked tokens; no default palette, radius ≤ 2px, no shadows).
  - Typed API client mirroring API_CONTRACT.
  - Layout: header with mode indicator, counters, nav, and live/replay switch; left rail with campaigns (severity squares) and candidates (verdict chips); the stream rail, which never collapses and becomes a 120px bottom strip below 1100px.
  - `VerdictChip`, `ModeIndicator`, `StreamLine`, mono `DomainName`/`Num`/`Hash`.
  - Client-side SSE throttle.
- **Verified by:**
  - vitest RED (modules missing), then GREEN 10/10:
    - a candidate never renders a verdict colour
    - a `suspicious` email is grey like a candidate
    - a confirmed verdict with < 2 strong signals renders as CANDIDATE
    - every chip pairs colour with a word
    - replay ≠ live; down/reconnecting never reads LIVE
    - the throttle holds ≤ 20/s under 3,000/s; the cap keeps the newest lines and never drops candidates
  - `tsc --noEmit` + `vite build` pass.
  - Screenshot review of the running console against the live API showed no console errors, and the mode correctly showed STREAM DOWN because no ingest was running.
- **Incident:** port 5173 belongs to another local project (its dev server answered my first screenshot). The console now runs on 5180, which is in the API CORS default.

## Task 21 — domain detail, evidence viewer, campaign graph

- **AI did:**
  - `DomainDetail`:
    - verdict chip with every signal (strength + detail)
    - triage reasons with provenance and threshold
    - infrastructure, with partial-collection errors
    - screenshot when present
    - the full domain name in mono, wrapped, never truncated
  - `EvidenceViewer`: verify (the failing row turns red with both hashes), and the report labelled "Report generated — not sent". Moved here from Task 22 because the domain view embeds it.
  - `CampaignGraph` + `cyto.ts`: stylesheet only from tokens; targets ringed 2px `--ink-000`; no dragging.
- **Verified by:**
  - vitest RED, then GREEN 22/22, including the tamper display, layout settle-and-stop, and "every graph colour is a token" checked against the real `tokens.css`.
  - The demo campaign seeded on **Supabase** (400 domains, 24 infrastructure nodes, 14.5 s).
  - Screenshots of the campaign and domain views reviewed.
- **Found by running it, fixed test-first:**
  - **The campaign graph froze the tab for 46 s.** Headless benchmark on the real graph: cose-bilkent 17–18 s, cose 21–23 s, with or without the all-domain hub edges.
    - Replaced with a deterministic O(n) radial layout: IP hubs on an outer ring, sized so no domain sits nearer a foreign IP; each IP's domains in a golden-angle sunflower; shared infrastructure on an inner ring; then one 400 ms preset settle.
    - Tests on the real 400-domain graph: positions computed fast, each domain nearest its own IP, no overlaps, deterministic.
  - From the screenshot review:
    - an `inet` showed as `x/32` (API now returns `host()`, with a test)
    - "[object Object]" appeared as a triage value
    - small files showed "0 KB"
    - the header domain name was truncated
- **Ruling:** the graph does not use cose-bilkent (DESIGN.md names it). Measured 17–22 s on the demo campaign; the intent (one settle, then static, readable) is kept.

## Task 22 — plan panel, benchmark, second organisation, ops log, email analyzer

- **AI did:**
  - `PlanPanel`/`PlanSummary`:
    - the k control clamps to the maximum given in a 422
    - fallback stated in words ("qaoa timed out → cpsat"), and a time-limited plan labelled "not proven optimal"
    - variables always shown; qubits only when present
    - hovering a target highlights exactly the domains it takes down
    - "Reports are generated … never sent"
  - `BenchmarkTable`: every row, failures included, with the ink border on whichever backend wins, and the quantum framing verbatim (never in a heading).
  - `SecondOrg`: starts empty; kit-hash lookup; "Inherited from ledger. No raw telemetry received."; corroborate and dispute (queued).
  - `OpsLog` and `EmailAnalyzer` (paste or .eml drop; suspicious shown grey).
  - Campaign view with the "Publish to ledger" action.
  - The mode dot is now a glyph (DESIGN bans radius > 2px).
- **Verified by:**
  - vitest 27/27.
  - Design-ban grep clean.
  - A Playwright-driven run against the live API + Supabase + local chain: plan, benchmark, publish (401 anchors landed on chain), org-2 inheritance and email analysis, with no browser console errors.
  - Full Python suite **808/808**.
- **Found by running the real system, fixed test-first:**
  - **QAOA took 34 s inside the API, against 9.8 s standalone.** COBYLA's Python loop competed for the GIL with the API's other requests.
    - Now runs in a dedicated worker process with a hard wall-clock kill.
    - Worker start-up (8.2 s spawn + Qiskit import) is excluded from the solve budget, which stops the kill → cold-respawn → timeout cascade observed after the first fix.
    - Measured through the API: **12.0 s first, then 6.6–6.9 s**, inside the 15 s budget.
  - **The first CP-SAT plan took 3.4–4.5 s cold.** OR-Tools is now warmed at API startup: **131 ms** on the first call after startup, 73–78 ms warm.
  - **The API lifespan leaked a global solver flag,** which broke the `test_fallback` release gate when run in the same process. It's now restored on shutdown, with a test.

## Task 23 — triage model: datasets, honest evaluation, adoption gate; brand favicons

- **AI did:**
  - `datasets.py`: PhishTank verified-online (last 90 days), the OpenPhish public feed, Tranco 1M negatives and hard negatives; counts reported before training, with MODELS.md §8's stop rule.
  - `split.py`: temporal and campaign-disjoint splits, never random.
  - `train_triage.py`:
    - calibrated logistic regression on the SAME feature code triage runs
    - TLD rates fitted on training data only
    - metrics: AUC on both splits, recall, precision at the real 1:1000 base rate, hard-negative FP rate, sweep 0.20–0.80, coefficients
    - MODELS.md §7's four hard checks plus the triage release-gate cases as the adoption gate
  - `brand_refs.py`: real brand favicons (observe only); now used by the enrich worker.
- **Measured:**
  - Data: 13,584 PhishTank rows (90 days) + 300 OpenPhish → 9,375 unique → **8,384 after campaign de-dup** (≥ 5,000: train). **584 hard negatives** (≥ 200).
  - **Only 47 positives target our 40 Indian brands.**
  - Temporal AUC **0.787**, campaign-disjoint 0.844. At 0.45: recall 21%, **precision at 1:1000 = 7.7%**, hard-negative FP 0%. Top coefficient share 0.25.
- **Decision (MODELS.md fallback, no owner action needed): the model is NOT adopted; triage stays on hand-set rules labelled `provenance: rules`.** It failed these hard checks:
  - flags `aws.dev` and `amazon.dev` (Tranco top 1,000)
  - `onlinesbi.sbi` scores ≥ 0.1
  - misses `icicibannk-login.top`
  - flags `netbanking.hdfcbank.com`

  Cause: the public phishing feeds barely cover Indian brands, so the model learned TLD and name shape, not brand impersonation.
- **Favicons:** 32/40 brands collected. Unreachable, so no signal for them: Yes Bank, IDFC First, Google Pay, EPFO, IRCTC, Myntra, Meesho, Swiggy.

## Task 24 — measurement (`scripts/evaluate.py` → `reports/metrics.json`)

- **AI did:**
  - Wrote the evaluation script. Every section records dataset, n, method and time, or `unavailable: <reason>`, never an estimate.
  - Ran the **full live pipeline against Supabase** (self-hosted CT stream, triage, enrich with real page fetches, anchor worker) for measured windows.
  - Added `verdict_at` and `received_at` so response time is measured, not inferred.
- **Verified by:** `test_evaluate.py` (a failed section is unavailable, not a number; no balanced precision anywhere), plus TDD for each fix below.
- **Bugs in my own evaluation, found before anything was reported:**
  1. **Triage "recall 0.0" on the global feed** was feed composition (Bradesco, Allegro…), not triage. And my "our brands" filter matched `amazonaws` S3 buckets as Amazon. Recall is now measured only where triage itself detects one of our brands.
  2. **Lead time "9,157 matches"** came from registrable-domain matching on shared platforms (secureserver.net, tinyurl.com). Now matched on the exact hostname named in the certificate.
  3. A Redis scratch-database URL bug.
- **Product bugs found by measuring, fixed test-first:**
  - **`queue_depth.certs_raw` showed the Redis stream length (136k), not the triage backlog.** It now reports consumer-group lag + pending. The test runs on real Redis, because fakeredis 2.26 mis-reports XINFO pending after XACK. Measured lag: 0–3.
  - **Unreachable sites were fetched twice** (Playwright timeout, then httpx). The first window measured p95 candidate→verdict at 44.7 s. httpx now runs only if Playwright itself is broken.
  - **"CT seen" stamps run ~14.4 s behind receipt, with a constant offset** (14.08–14.63 s over 200 messages). That's a fixed delay in the upstream aggregator, not our pipeline. Receipt time is now recorded, splitting upstream latency from ours.
- **Measured (first live window):**
  - 88 live candidates, 84 verdicts: 76 unreachable, 7 dismissed.
  - Ingest: 1,840 unique certificates/s per process, against 219/s live.
  - Confirmation gate on 45 labelled pages: precision 1.0, recall 0.5. All misses are unknown-kit pages with only one strong signal.
  - Interdiction on the seed, k = 2–5: all four solvers reach equal coverage. CP-SAT 58–228 ms, QAOA 6.1–8.7 s, annealing 164–310 ms, greedy ~1 ms.
- **Findings reported to the owner, NOT changed:**
  - **Triage recall on real phishing naming our brands is 0/9 at the TRD threshold 0.45.** At 0.35 it's 8/9, for 11.5 candidates/min vs 1.5. Recommendation: 0.35; awaiting a decision.
  - **No CT-first lead-time case exists in a 30-minute capture** (11 exact-host matches, all listed earlier). The "hours ahead" headline cannot be claimed from our data.

## Task 25 — technical report (`docs/REPORT.md`)

- **AI did:**
  - Wrote `scripts/build_report.py`. It renders the report only from `reports/metrics.json`; an unmeasured section reads "not measured — <reason>".
  - Added a measured evidence/ledger section:
    - 25/25 stored bundles re-verify
    - 25/25 one-byte tampers caught, with the file named
    - 400/400 anchored on chain, 10/10 roots match the chain
    - 400 reports generated, 0 sent
  - Re-measured the live response times in a steady-state window (114 candidates).
- **Verified by:** `test_build_report.py` (8): unmeasured → "not measured"; numbers come from the metrics; quantum framing verbatim and never a heading; "never sent" stated; proper nouns keep their case; missed targets said plainly; no precision number shown where recall is zero.
- **Corrected in review before shipping:** misleading "precision 0.0" (undefined at zero recall), "0.0 false-positive rate" (now "0 of 60,000"), lower-cased proper nouns, build-log phrasing in the email section, "tens of milliseconds" (measured 58–228 ms), and a claim about mean latency that was never measured (replaced by the measured median).

## Task 26 — deploy configuration (not deployed)

- **AI did:** wrote `docker-compose.yml` (one image for API and workers, plus certstream, Hardhat, Redis and a test Postgres), `services/api/Dockerfile`, `.dockerignore`, Railway service configs, the certstream Dockerfile, `apps/console/vercel.json` and `docs/DEPLOY.md`.
- **Found while building:** `python:3.11-slim` moved to Debian trixie, where Playwright 1.49 cannot install its system libraries. The image is pinned to `python:3.11-slim-bookworm`.
- **Not done:** nothing is deployed. Deploy waits for the owner's go-ahead and tokens. `docs/DEPLOY.md` states that the API has no authentication yet.

## Whole-branch review and fix pass

- **AI did:** a fresh reviewer (separate agent, no build context) read the whole branch. It reported 1 critical, 10 important and 16 minor findings. The important and critical ones were fixed, each with a test that failed first:
  - **Database did not enforce "confirmed needs two strong signals".** Added a CHECK constraint (`strong_signal_count`). Checked first: 400 confirmed rows in Supabase, 0 violating. Then applied.
  - **Email endpoint returned 500 on malformed input.** Switched to the tolerant `compat32` parser. A 5,000-message fuzz found 86 crashes before the fix and 0 after. Non-object JSON now returns 422.
  - **Enrich worker could read a domain row before the triage commit landed.** It now retries, then gives up after 5 attempts. The triage worker publishes only after commit.
  - **Unreachable domains were never re-checked.** They are re-checked with backoff: 5 min, 30 min, 2 h, 6 h, 1 day, 3 days.
  - **Triage worker could lose certificates on a crash.** Stale messages are reclaimed (XAUTOCLAIM), and poison messages go to a dead-letter stream.
  - **SSRF in page fetching.** The host comes from an attacker's certificate. Every request is now checked: the start URL, each redirect hop, favicon, scripts, and every Playwright subrequest. A host is fetched only if every address it resolves to is public. Bodies are streamed and capped at 2 MB, and the whole fetch has a deadline.
  - **Shared CDN/DNS made unrelated sites one campaign.** CDN ASNs (Cloudflare, AWS, Google, Fastly, Akamai, Microsoft) and managed-DNS nameservers no longer create edges.
  - **Trivial pages shared a "kit" hash.** Pages below 20 tags or 8 distinct tags get no kit hash.
  - **Report over-claimed.** The QUBO is now described as "exact up to second order", and the QAOA warm start from the greedy plan is disclosed.
- **Verified by:** the full Python suite (services + packages), console vitest, and Hardhat tests (counts in the ledger).
- **Kept, with tests:** lookalike and homoglyph both firing on a pure homograph. It is what lifts `xn--cicibank-shh.com`, `xn--pytm-53d.com` and similar over the threshold. A known miss is pinned: the Cyrillic-s `sbi.co.in` homograph scores 0.30. It awaits the owner's homoglyph-threshold decision.
- **Deferred:** the 16 minor findings, listed in the final hand-off. API authentication is deferred to the deploy decision.

## Tenant isolation and API keys (owner items 6 + 4, T1–T10)

- **Found first, reported before any fix (owner instruction):** the API had no notion of an organisation. Any caller could read every campaign, domain, evidence bundle, artifact, report and email analysis. Ledger writes accepted `as_org` from the request body, so a caller could sign as another organisation. Direct Supabase access with the publishable key was already closed: RLS was on with no policies.
- **Owner decisions applied:**
  - Shared CT candidates are separate rows from org-owned verdicts.
  - The seeded campaign belongs to org1.
  - The admin key can seed and switch the stream, and reads no org data.
- **AI did:**
  - `organisations` and `api_keys` tables; keys are SHA-256 at rest and shown once.
  - `org_id` (not null, indexed) on every org-owned table.
  - `domain_verdicts` replaces the verdict columns on the shared `domains` table, and an `org_domains` view joins only the current org's verdict.
  - Row-level security policies, with each request running as role `qcc_app` with `app.org_id` set.
  - A scoped repository layer (`services/api/repos/`), so routes contain no SQL.
  - An `X-API-Key` header on every route except `/health`, with org, demo (read-only) and admin keys.
  - Cross-org requests return 404.
  - The ledger signer is the key's org, and corroboration is by chain id.
  - The console signs in with a key, reads the live feed over `fetch`, and loads the screenshot as a blob.
- **Verified by:**
  - `test_tenancy.py`: org2 gets 404 on 8 org-1 reads and 5 org-1 writes. Org2's listings contain nothing of org1. Org2 sees shared candidates without org1's verdict. Org2 reads org1's anchored campaign on the real chain, but gets 404 on its rows.
  - `test_auth.py`: every route returns 401 without a key; the demo key is read-only; the admin key reads nothing; keys are hashed; revocation works; a forged `as_org` gets 422.
  - `test_tenancy_static.py`: no database access in routes; only admin routes touch the privileged connection; an unscoped query on a scoped connection still sees one org.
  - Mutation checks, both run:
    - Removing the org binding turns all 5 tenancy tests red.
    - Removing the repository's explicit org filters leaves the database's row-level security still isolating.
- **Supabase migration:**
  - Took a `pg_dump` backup first (`data/backups/`, gitignored).
  - Rehearsed on the test database with old-schema data.
  - Applied in one transaction: 731 verdicts moved; 402 domains are org1-private and 329 shared.
  - Live curl matrix: org2 gets 404 on 6 org-1 resources, an empty email list, and 329 shared candidates with no org-1 verdicts.

## Live confirmation: diagnosis, JS-era signals, false-positive gate (owner briefs B1–B7, S1–S7, C1–C5; 2026-10-07/08)

- **Found first, from measurement:** on the live feed the confirmation layer had confirmed nothing. Of the 1,435 live
  domains in the capture window, 659 were assessed and 0 came back with any strong signal; of the 432 with a favicon,
  0 appeared with their own brand's icon; 776 were unreachable (318 from one auto-generated host, kennelstudio.com).
- **Owner decisions applied:**
  - S1 (exfiltration endpoint on a credential page) ships strong: 0 false positives in every gate run.
  - S2 (credential POST in the page's code) was refined once (drop load-time requests, real hostnames only), then run
    once on a held-out set; one false positive there (twitch.tv's feature-flag POST to eppo.cloud) means it ships
    moderate and is not re-tuned against the held-out set.
  - The two-strong rule is unchanged; zero live confirmations is an accepted, reported outcome.
- **AI did:**
  - `scripts/diagnose_confirm.py`: unreachable breakdown by cause, site concentration, favicon census, strong signals
    by detector, on a fixed domain set so before and after describe the same domains.
  - Fixed: DNS failures reported as SSRF blocks (134 of 138); Cloudflare "Suspected Phishing" interstitials dismissed
    (9) instead of treated as not assessable; brand references now hash every declared icon (33 -> 73 hashes).
  - `services/enrich/exfil.py` (S1, S2), Playwright capture of script bundles; `scripts/exfil_fp_gate.py` with a
    development set (65 pages), a re-test, and a held-out set (45 pages) run once.
  - Found and fixed a safety hole while wiring S1/S2: one Telegram URL counted as two strong signals, and one detector
    reporting two endpoints counted twice. One shared independence rule (different detectors, no shared artifact) in
    `confirm.independent_strong` AND the database check `has_two_independent_strong` (applied to Supabase; all 520
    existing confirmed rows still valid).
  - Kill switch: `POST /admin/signals` (Redis override read per domain, can only lower a strength).
  - 7 modern JS-kit cases + 2 legitimate modern controls in the labelled evaluation, reported per family.
  - REPORT.md: one definitions block for the live counts; the held-out methodology stated; the same-origin relay
    limitation (meesho-all.cfd, `/dev-api/mobileUser`) stated as built (clustering takes confirmed domains only).
  - `--allow-partial` can no longer write the real report; hourly OpenPhish snapshotter for forward lead time.
- **Verified by:**
  - Tests first for each change (red, then green): test_exfil, test_confirm (independence, shipped defaults),
    test_schema (database rejects one artifact counted twice and two instances of one detector), test_signal_switch,
    test_diagnose_confirm, test_build_report (definitions, methodology, what the zero means), test_evaluate, test_fetch.
  - The held-out gate itself, run once and reported as measured.
- **Corrected the owner, with evidence:** "427" was the number of live domains with a favicon earlier that evening, not
  the number checked; "the campaign layer works at scale on live data" would overclaim, because clustering takes
  confirmed domains as its input and no live domain has been confirmed; the report says it is demonstrated on the
  seeded campaign. The quoted 166 ms solve time is not in the measured metrics; the report uses the measured value.
- **S4 result (same 1,435 domains, shipped logic, measured 2026-10-08T02:09:52Z):** 0 confirmed; 647 assessed;
  0 with any strong signal; 0 live domains in a campaign; S1 fired on 0 live domains; S2 (moderate) fired on 6, with
  destinations contaboserver.net, shopifysvc.com (Shopify's own telemetry) and mydukaan.io (a store platform's API),
  the platform false positives the held-out gate predicted.
- **Owner follow-ups applied (C1–C5, D1–D3, E1–E3):** held-out method stated in the report; one definitions block for
  the live counts; the kill switch documented as an evaluation-time control; "the live pipeline ends at the
  confirmation gate" stated in Results with the measured campaign count as a number; infrastructure co-location named
  as future work, not built; the two caught overclaims recorded in BUILD_DECISIONS.md.
- **Test failures, investigated before any push (E1/E2):** 5 local failures in the overnight suite, run beside S4
  (database round trip p95 490 ms). The query-count failure was the API-key lookup re-running after its 30 s cache
  expired inside a slow request: statements captured, mechanism proved with the cache forced to expire (every
  endpoint +1), and the test passed alone on the idle machine. The 4 timing failures (QAOA isolation, CP-SAT time
  limit) passed 6/6 alone on the idle machine. No code was changed for them; a test-side hardening is proposed in
  BUILD_DECISIONS.md, not made.
