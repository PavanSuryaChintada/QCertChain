# Migration runbook

How to change the hosted database (Supabase, `ap-southeast-1`) safely: back up, apply, verify, create keys,
roll back. Also how to reset the demo data and the demo chain. Every command here runs from the repo root.

`services/api/schema.sql` is the only source of DDL. Never retype DDL from the docs, and never edit tables
by hand in the Supabase dashboard.

## 0. Connection strings

| Variable | Form | Use |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres.<ref>:<pw>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres` | the app; also fine for migrations (session pooler, IPv4) |
| `DATABASE_URL_DIRECT` | `postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres` | migrations and `pg_dump` when your network has IPv6 |

`pg_dump` and `psql` need the plain `postgresql://` scheme, so strip the `+psycopg`. `scripts/apply_schema.py`
does that for you. Use the **session** pooler (port 5432), never the transaction pooler (6543): `pg_dump`, `SET`
and multi-statement DDL do not work through transaction pooling.

```bash
export PGURL="${DATABASE_URL/+psycopg/}"        # bash; plain libpq URL for pg_dump / psql
```

## 1. Back up first (always)

Use the `postgres:17` image so the client version matches Supabase (Postgres 17). A client older than the
server refuses to dump. `data/backups/` and `*.dump` are gitignored: backups contain data and never get committed.

```bash
mkdir -p data/backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker run --rm -v "$PWD/data/backups:/backups" postgres:17 \
  pg_dump "$PGURL" --format=custom --no-owner --no-privileges \
  --schema=public --file="/backups/qcertchain_$STAMP.dump"
ls -lh data/backups/                            # a dump of a few MB is normal; 0 bytes means it failed
docker run --rm -v "$PWD/data/backups:/backups" postgres:17 \
  pg_restore --list "/backups/qcertchain_$STAMP.dump" | head   # proves the file is readable
```

On Windows Git Bash, prefix the command with `MSYS_NO_PATHCONV=1` so `/backups` is not rewritten into a Windows path.

## 2. Pause the workers (lock contention)

Schema changes take `ACCESS EXCLUSIVE` locks. The workers hold transactions open for a long time. The
**enrich worker holds one transaction across each page fetch** (up to `CONFIRM_TIMEOUT_S`, 15 s, plus
Chromium), so an `ALTER TABLE domains` can sit behind it. Every new query then queues behind the waiting
`ALTER`, and the API stalls.

Pause the writers before migrating. The API can stay up: its transactions are short.

- **Railway:** scale `ingest`, `triage`, `enrich` and `anchor` to 0 replicas (service, Settings, Replicas),
  or remove their active deployments. Redis keeps the queued work, and the workers resume from their consumer
  groups.
- **Local:** stop the `python -m services...` worker processes, or run
  `docker compose stop ingest triage enrich anchor`.

Then check that nothing long-running is left:

```sql
select pid, state, now() - xact_start as xact_age, left(query, 80)
from pg_stat_activity
where datname = current_database() and xact_start is not null and pid <> pg_backend_pid()
order by xact_age desc;
```

## 3. Apply the schema

```bash
python -m scripts.apply_schema --url "$DATABASE_URL"        # or "$DATABASE_URL_DIRECT"
# -> schema applied
```

What it does:

- **Idempotent.** Every statement is `create ... if not exists`, `create or replace`, `on conflict do nothing`
  or a guarded `do $$ ... $$` block. Running it twice is a no-op, so it is safe to re-run after a partial failure.
- **One transaction.** The whole file is sent as a single multi-statement query, which Postgres runs as one
  implicit transaction. It either applies completely or not at all.
- **Its own timeouts.** It sets `statement_timeout = '10min'` and `lock_timeout = '2min'` on its session first
  (Supabase's default statement timeout is shorter than a migration that waits for locks). If it fails with
  `canceling statement due to lock timeout`, something still holds a lock: go back to step 2.

`--write-migration` also copies the schema to `supabase/migrations/20261006000000_init.sql` for the Supabase CLI.

## 4. Verify

```bash
psql "$PGURL" -v ON_ERROR_STOP=1 <<'SQL'
-- every table exists and has row-level security on (expect rls = t on every row)
select tablename, rowsecurity as rls from pg_tables where schemaname = 'public' order by 1;
-- the two consortium organisations
select id, slug, name from organisations order by id;            -- 1 org1 Bank One SOC, 2 org2 Bank Two SOC
-- the request role exists and has no access to key material
select rolname from pg_roles where rolname = 'qcc_app';
select has_table_privilege('qcc_app', 'api_keys', 'select');      -- f
-- policies are in place
select tablename, policyname from pg_policies where schemaname = 'public' order by 1, 2;
-- data survived (compare with the numbers before the migration)
select (select count(*) from domains) as domains, (select count(*) from campaigns) as campaigns,
       (select count(*) from api_keys where revoked_at is null) as live_keys;
SQL
```

If `psql` is not installed locally, run it from the same image:
`docker run --rm -i postgres:17 psql "$PGURL" -v ON_ERROR_STOP=1 < verify.sql`.

Then restart the workers (step 2 in reverse) and check the API:

```bash
curl -s https://<api-host>/health | jq '{status, regions, database_round_trip_ms}'
# status "ok", regions.colocated true, database_round_trip_ms a few ms in Singapore
```

## 5. Create API keys

Keys live in the database (`api_keys`, SHA-256 only), so create them against the database the API uses.
Each token is printed **once**. Put it straight into a password manager.

```bash
export DATABASE_URL=...                     # the hosted database
python -m scripts.create_api_key --kind org   --org org1 --label "Bank One SOC"
python -m scripts.create_api_key --kind org   --org org2 --label "Bank Two SOC"
python -m scripts.create_api_key --kind demo  --org org1 --label "evaluators (read-only)"
python -m scripts.create_api_key --kind admin --label "platform admin"
python -m scripts.create_api_key --revoke qcc_demo_AbC   # revoke by prefix (first 12 characters)
```

A revoked key stops working within 30 s (the auth cache TTL). Rotate the demo key after evaluation by
revoking it and creating a new one.

## 6. Roll back

The schema is additive and idempotent, so a failed `apply_schema` has already rolled itself back (one
transaction). Restore from the backup only when a migration **succeeded** but was wrong, or when data was damaged.

```bash
# 1. pause the workers (step 2), then restore into the public schema, replacing what is there
docker run --rm -v "$PWD/data/backups:/backups" postgres:17 \
  pg_restore --dbname="$PGURL" --clean --if-exists --no-owner --no-privileges \
  --single-transaction "/backups/qcertchain_<STAMP>.dump"
# 2. re-apply the schema so roles, grants and policies match the code (idempotent)
python -m scripts.apply_schema --url "$DATABASE_URL"
# 3. verify (step 4) and restart the workers
```

`--single-transaction` makes the restore all-or-nothing. Keys created after the backup are lost by a restore:
re-create them (step 5).

## 7. Demo reset (data)

Restores the known-good demo state for both organisations in one transaction. It deletes **only** demo data
(`source = 'seed'` domains and everything derived from them, and the sample emails), then re-seeds. Live CT
candidates and their verdicts are never touched. It needs the admin key.

```bash
curl -sX POST https://<api-host>/admin/reset -H "X-API-Key: $QCC_KEY_ADMIN" | jq
# -> {"removed": {...counts}, "seeded": {"org1": {...}, "org2": {...}}}
```

## 8. Demo chain redeploy

Chain state is not transactional, so `/admin/reset` does not touch it. A fresh Hardhat node deploys the
contracts to the same deterministic addresses committed in `contracts/deployments/localhost.json`.

- **Railway:** redeploy (or restart) the `hardhat` service. The image starts the node and runs
  `scripts/deploy.ts` on boot. Its logs end with the deployment JSON; check that the addresses match the
  committed file.
- **Local:** stop the node, then `cd contracts && npx hardhat node`, and in a second terminal
  `npx hardhat run scripts/deploy.ts --network localhost`.

After a chain reset, the anchor worker re-sends pending anchors from `anchor_queue` (Postgres). Run
`/admin/reset` after the chain redeploy so the seeded evidence is anchored on the new chain.
