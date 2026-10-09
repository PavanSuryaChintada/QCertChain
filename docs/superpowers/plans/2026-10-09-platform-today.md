# Platform today (Plan 2 of 4): public URL that survives restarts, super admin core, newest-first checking

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (owner chose native). Steps use `- [ ]`.

**Goal:** by tonight's demo (owner deadline 2026-10-09): the public Vercel site always finds the live API, a super
admin creates organisations by category from a panel and everyone signs in from a two-tab login page, and the live
queue shows real verdicts (not only "Suspicious") because the page checker takes the newest candidates first.

**Spec:** `docs/superpowers/specs/2026-10-09-multi-sector-platform-design.md` §3, §4, §8, §10 (approved). **Out of
today (Plan 3):** sector routing (§5), per-organisation chain accounts (§7), seeded campaign per new organisation
(§6). Until then a new organisation gets the shared feed and an empty workspace; its ledger lookups work, its
publishing waits for Plan 3. The panel says so.

## Global Constraints

- Owner rules: tests first (RED then GREEN); commit and push to `main`; no AI attribution; `AI_USAGE_LOG.md`.
- Schema changes only in `services/api/schema.sql`, idempotent; applied to Supabase **after a backup**
  (`docs/MIGRATION_RUNBOOK.md` §1–§4) with the writers paused; never typed into the dashboard.
- No new dependency: PyNaCl (argon2id `nacl.pwhash`, `nacl.secret.SecretBox`), `fetch` for Supabase REST.
- Secrets only in `.env` (gitignored): `KEY_SEAL_SECRET`, `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD`. Never printed.
- The public login page shows **read-only (demo) keys only**; full keys only in the super admin panel.
- Console design rules (`design.test.tsx`) and content rules (no typed measurements in explainer text) hold.
- Python DB tests: run single files (`.venv/Scripts/python -m pytest services/tests/<file> -q`); never two DB
  sessions at once. Console: `npx tsc --noEmit && npx vitest run`.

## Review Focus

1. Password guessing on a public site: 5 failures/min per client and 30/min overall → 429, before any argon2 work.
2. A superadmin session must read no organisation data (every org route 404s for it, like the admin key).
3. `GET /orgs/public` never returns a full, admin or session key, and never a key of a deactivated organisation.
4. The console's URL discovery accepts only `https://<sub>.trycloudflare.com`; anything else falls back.
5. A deactivated organisation's keys stop working within the auth cache window (30 s).

---

### Task 1: Newest-first page checking

**Files:** Modify `services/api/workers/enrich_worker.py` (pop and retry promotion); Test `services/tests/test_enrich_worker.py`.
**Interfaces:** Produces `async def pop_next(r) -> str | None` (blpop on `enrich:queue`, timeout 5).

- [ ] RED: test with fakeredis: `lpush` a, b, c (as triage does) → `pop_next` returns c, b, a; a due retry promoted
  by `_promote_retries` is popped before older queued items.
- [ ] GREEN: `pop_next` uses `blpop`; `_promote_retries` uses `lpush`; `worker` calls `pop_next`.
- [ ] Restart the enrich worker; commit "Page checker takes the newest candidates first…".

### Task 2: Public URL discovery (Cloudflare quick tunnel)

**Files:**
- Modify `services/api/schema.sql`: `public_endpoints (name text primary key, url text not null, updated_at timestamptz default now())`; RLS on (existing loop); `revoke all on public_endpoints from qcc_app`; policy `anon_read` for `select` to `anon` created only if role `anon` exists.
- Create `scripts/tunnel.py`: `parse_url(line) -> str | None`; `publish(engine, url)` upsert; `main()` runs `npx -y cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000`, reads output lines, on the URL waits for `<url>/health` 200 (60 s), publishes, keeps running; exits when cloudflared exits.
- Modify `scripts/demo_stack.py`: `tunnel` in the supervised set (marker `scripts.tunnel`); `scripts/demo.py check` row: published URL's `/health`.
- Create `apps/console/src/lib/apiUrl.ts`: `ACCEPT = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/`; `discoverApiUrl(fetchImpl?): Promise<string | null>` (3 s timeout; GET `${VITE_SUPABASE_URL}/rest/v1/public_endpoints?name=eq.api&select=url`, header `apikey`); returns null when the two settings are missing or the answer is not accepted.
- Modify `apps/console/src/lib/api.ts`: `API_URL` becomes `apiUrl()` / `setApiUrl()`; `apiFetch` on a network error (TypeError) re-discovers once and retries if the URL changed.
- Modify `apps/console/src/main.tsx`: await `discoverApiUrl()` (bounded 3 s) before the first render.
**Tests:** `services/tests/test_tunnel.py` (parse_url on real cloudflared lines; publish upserts; anon cannot write — schema test that `anon_read` is select-only when `anon` exists); console `apiUrl.test.ts` (accepted URL used; non-trycloudflare, timeout, missing settings → null; network failure re-discovers once).
- [ ] Back up Supabase, pause writers, apply schema (runbook), restart; start the tunnel through `demo_stack`; set Vercel `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` (owner, once); commit.

### Task 3: Super admin backend

**Files:**
- `services/api/schema.sql`: `organisations` + `category text not null default 'other'` (check list of 9), `active boolean not null default true`, `created_at timestamptz default now()`; org1/org2 → `banking`; `api_keys` + `token_sealed bytea`, `expires_at timestamptz`; kind check → `org, demo, admin, superadmin` (drop/re-add `api_keys_kind_check`); `api_keys_admin_has_no_org` → `(kind in ('admin','superadmin')) = (org_id is null)`; `super_admins (id bigserial pk, email text unique not null, password_hash text not null, created_at timestamptz default now())`, `revoke all on super_admins from qcc_app`.
- `services/config.py`: `key_seal_secret`, `superadmin_email`, `superadmin_password` (default "").
- Create `services/api/seal.py`: `seal(text) -> bytes | None` (None without a secret), `unseal(bytes) -> str`.
- `services/api/auth.py`: `KeyKind` + `"superadmin"`; `create_key(..., expires_s=None)` seals when it can; `lookup` refuses expired keys and keys of inactive organisations.
- Create `services/api/routes/accounts.py` (public, no key): `POST /auth/superadmin/login` (Redis throttle 5/min/client by `CF-Connecting-IP` else socket, 30/min total → 429 before verifying; argon2id verify; returns `{token, expires_at}` 12 h); `GET /orgs/public` (`[{slug, name, category, demo_key}]`, active only, demo keys unsealed, never others).
- Create `services/api/routes/superadmin.py` (key + `require_superadmin`, 404 for every other kind): `POST /auth/logout` (revokes a superadmin session; 204 for other kinds); `GET /superadmin/orgs`; `POST /superadmin/orgs {name, category}` (slug from name, unique; org + org key + demo key, both sealed; returns both); `GET /superadmin/orgs/{slug}/keys`; `POST /superadmin/orgs/{slug}/rotate {kind}`; `POST /superadmin/orgs/{slug}/deactivate` (org1 refused, 409).
- `services/api/deps.py`: `require_superadmin`; `get_scope` treats `superadmin` like `admin` (404).
- `services/api/main.py`: include `accounts.router` without key dependencies; `superadmin.router` with them.
- Create `scripts/superadmin.py`: `set` (upsert from `.env`), `backfill` (seal `QCC_KEY_ORG1/ORG2/DEMO` after matching their stored hash; create and seal a demo key for org2).
**Tests (`services/tests/test_superadmin.py`, plus the allow-list in `test_auth.py`):** wrong password 401; throttle 429 after 5 per client and 30 total, before verifying; session works on `/superadmin/orgs`, expires, logout revokes; org/demo/admin keys 404 on `/superadmin/*`; superadmin 404 on `/campaigns`; create returns two working keys, the org key reads its own empty campaigns and 404s Bank One's campaign; `/orgs/public` lists demo keys only, active only; rotate revokes the old key; deactivate refuses its keys (after `auth.clear_cache()`), org1 409; seal round trip, wrong secret fails.
- [ ] Apply schema (backup first), `scripts.superadmin set` and `backfill`, restart the API; commit.

### Task 4: Login page and super admin panel (console)

**Files:**
- `apps/console/src/lib/api.ts`: `publicOrgs()`, `superLogin(email, password)`, `logout()`, `superOrgs()`, `createOrg(name, category)`, `orgKeys(slug)`, `rotateKey(slug, kind)`, `deactivateOrg(slug)`; types `PublicOrg`, `SuperOrg`, `OrgKeys`, `Category`.
- `apps/console/src/layout/KeyGate.tsx`: two tabs — **Organisations** (`/orgs/public` grouped by category; each row: name, read-only key with copy, **Sign in (read-only)**; below it the paste-a-key form) and **Super admin** (email + password → `setKey(token)`).
- Create `apps/console/src/views/SuperAdmin.tsx`: organisations table (name, category, active, created); **New organisation** form (name, category select); reveal/copy keys; rotate; deactivate; **Open console as this organisation** (`setKey(orgKey)`); sign out (`logout()` then `setKey(null)`). A note: "New organisations get the shared feed now; their seeded campaign and sector feed arrive with the next update."
- `apps/console/src/App.tsx` / `main.tsx`: a key starting `qcc_superadmin_` renders the panel instead of the organisation console.
- `help/content.ts`: `/superadmin` entry; `signin` entry updated (two tabs, read-only keys).
**Tests:** `login.test.tsx` (both tabs; one click signs in with the shown demo key; super admin login stores the session), `superadmin.test.tsx` (create → keys shown; open as organisation switches the key; sign out revokes; a superadmin key renders the panel not the console).
- [ ] Commit; push; Vercel redeploys from `main`.

### Task 5: Verify and log

- [ ] `demo check` READY; open the public site, sign in as super admin, create "ShopSafe SOC" (E-commerce), sign in as it read-only, see the shared feed; Bank One's campaign 404s for it.
- [ ] `AI_USAGE_LOG.md`; ledger; push.
