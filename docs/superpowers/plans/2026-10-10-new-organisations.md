# New organisations get the full workflow (Plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (owner chose native). Steps use `- [ ]`.

**Goal:** an organisation the super admin creates works like Bank One: its own chain account (it can publish to and
sign on the ledger), a seeded demo campaign in its sector (graph, plan, evidence, ledger lookup), its sector's live
candidates, and a Live queue that shows its sector by default. The report's response time counts every
organisation's live verdicts, and demo reset re-seeds every organisation.

**Spec:** `docs/superpowers/specs/2026-10-09-multi-sector-platform-design.md` §3 (columns), §5, §6, §7 (approved).

## Global Constraints

- Owner rules: tests first; commit and push to `main`; no AI attribution; `AI_USAGE_LOG.md`; never hand-type a number
  into `docs/REPORT.md` (it is generated).
- Schema only in `schema.sql`, applied after a backup (`scripts.backup_tables` when Docker cannot reach Supabase),
  writers paused, and the API restarted on new code **only after the apply succeeded**.
- Chain tests use the test chain (:8546), never the demo chain (:8545). The chain admin key is Hardhat account #0
  (public, demo chain only), from `.env` `CHAIN_ADMIN_PRIVATE_KEY`.
- Seeded data stays labelled seeded (source `seed`), uses documentation IPs and `.example` names only.
- No new dependency.

## Review Focus

1. The chain is down when an organisation is created: the organisation still works; its account is registered by
   the next `scripts.superadmin chain` (run by `demo up`), and the panel shows "chain: pending".
2. Seeding is slow on this network: creation answers at once and the campaign appears when ready; a failure is
   written to the ops log, never lost silently.
3. Two organisations in one sector: only the oldest receives that sector's live confirmations (stated limit).
4. A candidate whose brand is unknown, or a sector with no organisation, goes to the pipeline organisation (org1).
5. Reset must not touch live CT data or another organisation's data.

---

### Task 1: Columns (and the migration)
`organisations` + `chain_address text`, `chain_key_sealed bytea`, `demo_brand text`. Back up, pause writers, apply,
restart only on success.

### Task 2: A chain account per organisation
- `Ledger(key_loader=...)`; `Ledger.account(slug)` (cached, else loaded from the sealed key in the database);
  `_send` and the anchor worker use it; `Ledger.register_org(address, name)` funds the account from the chain admin
  and calls `OrgRegistry.registerOrg`; `Ledger.is_registered(address)`.
- `services/api/platform.py` `provision_chain(c, ledger, slug, name)`: generate, seal, store, fund + register.
- `scripts.superadmin chain`: register every active organisation with an address on the current chain (idempotent);
  `scripts.demo up` runs it after deploying contracts on a fresh chain.
- Tests (`test_ledger_orgs.py`, chain): a provisioned organisation is registered, can anchor and publish, and its
  name is the reporter; re-running `chain` is a no-op.

### Task 3: Provisioning on creation, reset for everyone
- `POST /superadmin/orgs` takes optional `demo_brand` (required for `other`); answers at once; a background task
  provisions the chain account, seeds a ~60-domain campaign imitating the brand (default: first brand of the
  sector), and queues its publication. Failures go to the ops log.
- `GET /superadmin/orgs` adds `campaigns` and `chain` (`registered` / `pending` / `none`).
- `reset_demo` re-seeds every other active organisation with its own campaign.
- Tests (`test_superadmin.py`, `test_reset_demo.py`).

### Task 4: Sector routing and the sector filter
- Triage worker tags new candidates `"<org_id>:<domain_id>"` for the oldest active organisation in the brand's
  sector (60 s cache); unknown brand or sector without organisation: untagged (pipeline organisation).
- `GET /candidates?sector=` filters by the sector's brands; `/status` returns the organisation's category.
- Live queue: a Sector dropdown, defaulting to the organisation's category (`other`: all sectors).
- Tests (`test_triage_worker.py`, `test_api.py`, console `queueDefault.test.tsx`).

### Task 5: Response time across organisations
- `scripts/evaluate.py` response time reads every organisation's live verdicts (each live domain has one confirmer).
- Test (`test_evaluate.py`).

### Task 6: Docs and verification
- `API_CONTRACT.md` (platform routes), `DEPLOY.md` (new variables, the quick tunnel), `DEMO.md` (platform segment),
  `BUILD_DECISIONS.md` (the spec §9 changes), `AI_USAGE_LOG.md`.
- Offline e2e when the laptop is free; `demo check` READY.
