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
