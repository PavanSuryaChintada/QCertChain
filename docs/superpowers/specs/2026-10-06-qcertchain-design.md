# QCertChain — Design Spec

**Date:** 2026-10-06
**Status:** awaiting review
**Baseline:** the specification set in `spec-docs/` (CLAUDE.md, ARCHITECTURE, PRD, TRD, NPHARD, BLOCKCHAIN, MODELS, DATA, API_CONTRACT, DESIGN, WORKFLOW, RUNBOOK, schema.sql, docker-compose.yml, both BUILD_SPECs).

This document does **not** restate the baseline. Everything in `spec-docs/` is built as written unless a section below changes it. Where this document and the baseline conflict, this document wins, because each change here was decided with the project owner on 2026-10-06.

---

## 1. Intended outcome

A working phishing-campaign interdiction system that satisfies the challenge brief:

| Brief requirement | Where it is met |
|---|---|
| Autonomous phishing detection and takedown system | Baseline pipeline: CT ingest → triage → confirm → enrich → graph → interdict → evidence → ledger → console. "Takedown" = generated, evidence-backed plan and reports, **never submitted** (baseline CLAUDE.md §2.1, unchanged). |
| Lookalike-domain and certificate analysis | Baseline triage (brand tokens, Damerau-Levenshtein, homoglyphs, TLD risk) on the live CT firehose; TLS chain enrichment. |
| Malicious email-header analysis module | **New — §3 below.** |
| Evidence-backed threat and takedown workflow | Baseline confirmation gate (≥2 strong signals), Merkle + Ed25519 bundles, abuse reports (unsent), on-chain anchors, dispute flow. |
| Detection precision and response-time analysis | **New — §4 below.** |
| Final technical report and demonstration | **New — §4 below** (`docs/REPORT.md`) + baseline demo script (WORKFLOW §5). |
| Correlate across domains, certificates, email | Campaign graph (baseline) + email-to-graph linking (§3.4). |
| Automated actions controlled, never target legit infra | Allowlist-first triage, ≥2 strong signals to confirm, candidate ≠ verdict in UI, no submission code anywhere, `sent=false` DB constraint, Attestation `Disputed`. |

**Quantum, SSL certificates, blockchain, reporting** — the four pillars the owner named — map to: QAOA backend on the reduced QUBO (NPHARD.md), live CT certificate monitoring + TLS chain evidence, Hardhat ledger (BLOCKCHAIN.md), and §4.

---

## 2. Decisions taken with the owner

| # | Decision | Effect on baseline |
|---|---|---|
| D1 | **Add an email-header module** | Overrides PRD §6 "Email scanning — out of scope". |
| D2 | Email input is **paste / `.eml` upload only** | No mailbox connection (IMAP etc.). Keeps the "no real customer data" rule intact. |
| D3 | Report = **Markdown + generated metrics** | `docs/REPORT.md` built from `reports/metrics.json`. |
| D4 | Name = **QCertChain** | Find-replace SEVER → QCertChain in all code, UI, docs. |
| D5 | Triage = **rules first, then train** | Ship TRD §2 hand-set weights labelled `provenance: rules`; then train LR on OpenPhish + Tranco (no PhishTank key). Stop and report if positives < 5,000 after campaign dedup (MODELS §8). |
| D6 | **Deploy** to Railway + Vercel | Configs built; actual deploy only after explicit go-ahead (outward-facing, needs tokens). |
| D7 | **Database = Supabase** (project `obyexvvwlirnijucyiob`, ap-southeast-1) | Replaces the `postgres` service in docker-compose. See §5. |

---

## 3. Email-header analysis module (new)

### 3.1 Location and shape

```
services/email/
├── parse.py        raw headers / .eml → ParsedEmail (stdlib `email`, policy=default)
├── signals.py      one function per check, each returns Signal(name, strength, detail)
├── analyze.py      ParsedEmail → EmailVerdict (applies the gate in §3.3)
└── samples/        demo .eml files, every one labelled source: sample
```

No new dependency: Python stdlib `email` + the existing `tldextract`, `dnspython`, and `services/ingest/triage.py`.

### 3.2 Signals

| Signal | Strength | Rule |
|---|---|---|
| `dmarc_fail_brand_from` | **strong** | `Authentication-Results` shows `dmarc=fail` AND the From domain is a brand's legit domain (spoofing a real brand) |
| `display_name_brand_spoof` | **strong** | Display name contains a brand name/token AND From eTLD+1 is not in that brand's `legit_domains` |
| `link_domain_confirmed` | **strong** | A URL/link domain in the body is `confirmed` in our DB or belongs to an active campaign |
| `sender_domain_confirmed` | **strong** | From / Return-Path / Reply-To eTLD+1 is `confirmed` in our DB or belongs to an active campaign |
| `lookalike_sender_domain` | moderate | From/Reply-To eTLD+1 triages as a candidate (score ≥ threshold) |
| `reply_to_mismatch` | moderate | Reply-To eTLD+1 ≠ From eTLD+1 |
| `spf_fail` / `dkim_fail` | moderate | From `Authentication-Results` / `Received-SPF` |
| `return_path_mismatch` | weak | Return-Path eTLD+1 ≠ From eTLD+1 |
| `message_id_mismatch` | weak | Message-ID domain ≠ From eTLD+1 |
| `received_anomaly` | weak | Origin hop IP in a different ASN from the sender domain's MX, or hop timestamps out of order |
| `auth_results_missing` | weak | No `Authentication-Results` header at all |

Header parsing reads only what is present. A missing header is recorded as "absent", never guessed.

### 3.3 Verdict gate — same discipline as domains

- `malicious` requires **≥ 2 strong signals**. Never moderate-only.
- Anything with ≥ 1 signal but < 2 strong → `suspicious` — rendered **grey**, worded "Suspicious — not verified", same as a domain candidate.
- No signals → `clean`.
- Every verdict stores and returns all signals with details. A verdict without reasons is a bug.

### 3.4 Correlation into the pipeline

- Every link domain and sender domain is run through `triage()`. Those scoring ≥ threshold are inserted as domain **candidates** with `source = 'email'` and enter the normal confirmation pipeline. Email never confirms a domain on its own.
- The origin hop IP becomes (or matches) an `ip` infra node; the analysis records which campaign(s) it touches. The console shows "This email links to campaign CAMP-0042 via ns1.cheapdns.top / 185.243.115.22".
- No email content is stored beyond headers + extracted URLs. Bodies are discarded after URL extraction. Nothing email-derived goes on-chain except, optionally, a hash of the analysis as an Attestation subject.

### 3.5 Contract changes (made in API_CONTRACT.md / schema.sql **before** code)

- `Source` enum gains `"email"` and `"sample"`; `domains.source` / `certificates.source` check constraints updated.
- New table `email_analyses` (id uuid, received_at, source, from_addr, from_etld1, reply_to_etld1, return_path_etld1, auth_results jsonb, received_hops jsonb, urls text[], signals jsonb, strong_count, verdict check in ('malicious','suspicious','clean'), linked_campaign_ids uuid[], linked_domain_ids bigint[]).
- `POST /email/analyze` — body `{"raw": "<headers or full eml>", "source": "sample"|"analyst"}` or multipart `.eml`; returns the analysis.
- `GET /email/analyses?verdict=&limit=&offset=` (Page), `GET /email/analyses/{id}`.
- `ops_log.channel` gains `'email'`.

### 3.6 Console

New view `EmailAnalyzer.tsx`: paste box + `.eml` drop target, signals checklist (same component as domain confirmation reasons), verdict chip, links to correlated domains/campaigns. Nav label "Email headers". Design tokens unchanged.

### 3.7 Tests

`services/tests/test_email.py`: SPF/DKIM/DMARC parsing from real-format `Authentication-Results`; display-name spoof; a legit brand email (passing DMARC from the brand's real domain) is `clean`; a moderate-only email is never `malicious`; correlation inserts a candidate, never a confirmed domain.

---

## 4. Reporting — precision and response-time analysis (new)

### 4.1 Instrumentation

Stage timestamps per domain are already partly in the schema (`first_seen`, `confirmed_at`, plan `created_at`, bundle `created_at`, `anchored_at`). Add `domains.candidate_at` and `domains.ct_seen_at` (from the cert) so each stage boundary is measured, not inferred. Ops log already records solver ms.

### 4.2 `scripts/evaluate.py` → `reports/metrics.json`

| Section | Metric | Method |
|---|---|---|
| Triage | recall at threshold, **precision at 1:1000 base rate**, hard-negative FP rate, threshold sweep 0.20–0.80, coefficients | MODELS §2; temporal split; never balanced-set precision |
| Triage | latency p50 / p95 / p99 per name | timed over ≥ 100k names from the capture file |
| Ingest | sustained certs/sec in replay at max speed | replay benchmark |
| Confirmation | precision / recall on a labelled set | labelled set = seeded kit pages (positive) + brand legit pages and hard negatives (negative); served locally, never live third-party sites for negatives |
| Email | precision / recall of `malicious` on labelled sample set | `services/email/samples/` labels |
| Response time | p50 / p95 per stage: CT seen → candidate → confirmed → in campaign → plan → bundle → anchored | from stage timestamps |
| Interdiction | full benchmark table cpsat / qaoa / annealing / greedy, **losses included**; solve ms; n_variables / qubits | NPHARD §10 |
| Lead time | CT-certificate time vs. OpenPhish listing time for recent OpenPhish entries | DATA §3 — the headline number |

Every number records the dataset, date and sample size it came from. If a source is unreachable the section says so and the number is absent — never estimated.

### 4.3 `docs/REPORT.md`

Generated by `scripts/build_report.py` from `metrics.json` + a template: problem, architecture, method per stage, results tables, limits (HTTP-only phishing, wildcard certs, email module is paste-only, QAOA at ≤24 qubits), and the honest-positioning statements from baseline CLAUDE.md §2.3/§2.4. Exportable to PDF/Word later.

---

## 5. Database — Supabase

- **Postgres 17** (baseline says 16; `schema.sql` uses nothing version-specific). Extensions `uuid-ossp`, `pgcrypto` are available on Supabase.
- Connection: the **session pooler** `aws-0-ap-southeast-1.pooler.supabase.com:5432` (IPv4 — required because the direct host `db.obyexvvwlirnijucyiob.supabase.co` is IPv6-only and Docker/Railway cannot reach it). Direct host used only for migrations from this machine.
- Schema applied with `psql "$DATABASE_URL_DIRECT" -f services/api/schema.sql`, via a Supabase migration so it is reproducible.
- **Security — required:** Supabase exposes `public` tables through PostgREST to anyone holding the publishable key. The schema migration will `alter table … enable row level security` on **every** table with **no policies**, so the anon/authenticated roles get nothing. The API connects as `postgres` (bypasses RLS). The publishable key is not used by the console at all — the console talks only to our FastAPI.
- `docker-compose.yml` drops the `postgres` service; keeps `redis`, `api`, `ingest`, `triage`, `enrich`, `hardhat`.
- Secrets live in `.env` (git-ignored). Railway/Vercel get them as environment variables, never in the repo.

---

## 6. Deployment

- **Railway:** `api`, `ingest` (1 replica), `triage`, `enrich`, `anchor` worker, `redis`, `hardhat` (as the demo consortium node). Playwright Chromium in the API image; if it fails on Railway, `httpx` fallback with `partial: true` bundles (baseline-sanctioned).
- **Vercel:** `apps/console` static build; `VITE_API_URL` points at Railway.
- Deploy executes only after the owner says go, with their Railway/Vercel tokens.

---

## 7. Repository layout changes

- `spec-docs/*.md` → `docs/`; `CLAUDE.md` → repo root; `schema.sql` → `services/api/`; `BUILD_SPEC.md` (contracts) → `contracts/`; `mnt/.../apps/BUILD_SPEC.md` → `apps/`; `docker-compose.yml`, `.env.example` → root. `CLAUDE (1).md` (older subset of CLAUDE.md) deleted.
- `services/api/BUILD_SPEC.md` is referenced by CLAUDE.md but does not exist; the API is built from TRD §5 + API_CONTRACT.md, and a BUILD_SPEC is written as we go.
- Add `services/email/` (§3), `scripts/evaluate.py`, `scripts/build_report.py`, `reports/`, `docs/REPORT.md`.

---

## 8. Unchanged non-negotiables (restated because they gate every task)

1. No code sends a takedown, email, abuse form, or registrar API call.
2. Confirmed requires ≥ 2 strong signals. Candidates are grey. Verdicts always show reasons.
3. Quantum: QUBO on CP-SAT in production, QAOA benchmarked with losses, never in a heading or a speed claim, system runs with Qiskit uninstalled.
4. On-chain = hashes and commitments only.
5. Replay mode and seeded data always labelled.
6. If a data source (certstream, OpenPhish, Tranco, RDAP) is down or unreachable, report it — no silent substitution.
7. Release gates green before demo: test_triage, test_interdict, test_fallback, test_evidence, + new test_email.

---

## 9. Build order

Baseline WORKFLOW phases 0–6 and cut order, with these insertions:

- Phase 0: Supabase schema + RLS migration; 30-min CT capture started first.
- Phase 2 (after triage exists): email module §3 + test_email.
- Phase 3: stage-timestamp instrumentation.
- Phase 6: `evaluate.py`, `build_report.py`, `docs/REPORT.md`; deploy configs; deploy on go-ahead.

Cut order: email module sits after item 5 (evidence + tamper demo) and before item 6 (ledger) — it is a brief requirement, so it is cut only after the optional items (QAOA backend excepted — owner named quantum explicitly, so QAOA is not cut; if it fails it ships as benchmarked-with-fallback).
