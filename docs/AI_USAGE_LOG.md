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
