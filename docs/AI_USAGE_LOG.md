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
