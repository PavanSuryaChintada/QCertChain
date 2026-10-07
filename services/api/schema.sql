-- QCertChain · PostgreSQL 16/17 (Supabase runs 17)
-- Apply:  python -m scripts.apply_schema --url "$DATABASE_URL_DIRECT"   (idempotent)
-- This file is the source of truth. Do not retype DDL from the docs.

create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;

-- ===============================================================
-- TENANCY  ·  two trust boundaries, on purpose:
--   * the CHAIN is public to every member (hashes, counts, reporter, timestamp);
--   * this DATABASE is strictly org-scoped. Every org-owned row carries org_id; the API runs each request
--     as role qcc_app with app.org_id set, and row-level security filters every table by it.
-- Shared (no org_id): certificates and public-feed candidates (domains.origin_org_id is null).
-- ===============================================================
create table if not exists organisations (
  id     bigserial primary key,
  slug   text not null unique,          -- matches the ledger account key: org1, org2
  name   text not null
);
insert into organisations (id, slug, name) values (1, 'org1', 'Bank One SOC'), (2, 'org2', 'Bank Two SOC')
  on conflict (id) do nothing;
select setval(pg_get_serial_sequence('organisations', 'id'), greatest(2, (select max(id) from organisations)));

-- API keys: only the SHA-256 of a 256-bit random token is stored; the token is shown once at creation.
create table if not exists api_keys (
  id          bigserial primary key,
  org_id      bigint references organisations(id),
  kind        text not null check (kind in ('org', 'demo', 'admin')),
  key_hash    text not null unique,
  prefix      text not null,            -- first characters, to tell keys apart in listings
  label       text,
  created_at  timestamptz default now(),
  revoked_at  timestamptz,
  constraint api_keys_admin_has_no_org check ((kind = 'admin') = (org_id is null))
);

create or replace function current_org() returns bigint language sql stable as $$
  select nullif(current_setting('app.org_id', true), '')::bigint
$$;

-- ===============================================================
-- CERTIFICATES  ·  raw CT observations
-- High volume. Retention 24h — see purge_raw_certs() at the bottom.
-- ===============================================================
create table if not exists certificates (
  id            bigserial primary key,
  ct_seen_at    timestamptz not null default now(),
  not_before    timestamptz,
  not_after     timestamptz,
  issuer        text,
  serial        text,
  fingerprint   text unique,           -- leaf sha256; one cert seen in many logs = one row
  san_count     smallint,
  source        text default 'certstream' check (source in ('certstream','replay','seed','email','sample'))
);
create index if not exists cert_seen_idx on certificates (ct_seen_at desc);

-- ===============================================================
-- DOMAINS  ·  one row per observed name
-- status is the single most important column in this schema:
-- a candidate is NOT an accusation. The UI must respect it.
-- ===============================================================
create table if not exists domains (
  id             bigserial primary key,
  name           text not null unique,
  etld1          text not null,
  cert_id        bigint references certificates(id) on delete set null,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  source         text not null default 'certstream'
                 check (source in ('certstream','replay','seed','email','sample')),

  -- stage timestamps: measured, never inferred (spec §4.1)
  ct_seen_at         timestamptz,   -- when the certificate reached us from CT
  candidate_at       timestamptz,   -- when triage made it a candidate

  -- triage (cheap, fast, NEVER a verdict)
  triage_score   real check (triage_score between 0 and 1),
  triage_reasons jsonb,
  brand_matched  text
  -- NO verdict here: confirmation is org-owned (domain_verdicts). A shared row must never reveal that a
  -- particular org confirmed it.
);
alter table domains add column if not exists received_at timestamptz;  -- when OUR ingest received the cert
-- null = public CT feed (shared with every org); set = private to that org (email-sourced, seeded)
alter table domains add column if not exists origin_org_id bigint references organisations(id);
create index if not exists domains_etld1_idx   on domains (etld1);
create index if not exists domains_seen_idx    on domains (first_seen desc, id desc);
create index if not exists domains_origin_idx  on domains (origin_org_id);
-- CLAUDE.md non-negotiable, enforced in the database too: confirmed needs >= 2 STRONG signals.
create or replace function strong_signal_count(reasons jsonb) returns int
language sql immutable as $$
  select count(*)::int from jsonb_array_elements(coalesce(reasons->'signals', '[]'::jsonb)) s
  where s->>'strength' = 'strong'
$$;

-- ===============================================================
-- ENRICHMENT  ·  infrastructure + fingerprints
-- These attributes become the EDGES of the campaign graph.
-- ===============================================================
create table if not exists enrichment (
  domain_id     bigint primary key references domains(id) on delete cascade,
  ip_addresses  inet[],
  asn           integer,
  asn_name      text,
  country       text,
  nameservers   text[],
  mx_records    text[],
  cert_issuer   text,
  registrar     text,
  registered_at timestamptz,
  registrant    text,

  -- the fingerprints that make clustering work
  dom_hash      text,          -- structure-only hash: THE kit fingerprint
  favicon_hash  text,
  js_hashes     text[],
  page_title    text,

  enriched_at   timestamptz default now(),
  partial       boolean default false,   -- true if any enricher failed
  errors        jsonb
);
create index if not exists enrich_dom_idx     on enrichment (dom_hash);
create index if not exists enrich_favicon_idx on enrichment (favicon_hash);
create index if not exists enrich_asn_idx     on enrichment (asn);

-- ===============================================================
-- GRAPH  ·  infrastructure nodes and domain→node edges
-- ===============================================================
create table if not exists infra_nodes (
  id          bigserial primary key,
  kind        text not null check (kind in
                ('ip','asn','nameserver','cert_issuer','kit_hash','favicon_hash','registrar')),
  value       text not null,
  first_seen  timestamptz default now(),
  domain_count integer default 0,
  unique (kind, value)
);
create index if not exists infra_kind_idx on infra_nodes (kind, domain_count desc);

create table if not exists graph_edges (
  id        bigserial primary key,
  domain_id bigint not null references domains(id) on delete cascade,
  node_id   bigint not null references infra_nodes(id) on delete cascade,
  weight    real not null check (weight between 0 and 1),
  unique (domain_id, node_id)
);
create index if not exists edges_domain_idx on graph_edges (domain_id);
create index if not exists edges_node_idx   on graph_edges (node_id);
-- clustering only traverses edges with weight >= 0.6; ASN and cert_issuer
-- edges sit below that on purpose (shared hosting creates false links)

-- ===============================================================
-- CAMPAIGNS
-- ===============================================================
create table if not exists campaigns (
  id            uuid primary key default gen_random_uuid(),
  label         text,
  kit_hash      text,
  domain_count  integer default 0,
  infra_count   integer default 0,
  confidence    real check (confidence between 0 and 1),
  brands        text[],
  first_seen    timestamptz default now(),
  last_seen     timestamptz default now(),
  status        text default 'active' check (status in ('active','dormant','dismantled')),
  ioc_root      text,          -- Merkle root over the IOC set
  published_tx  text           -- chain tx hash, null until published
);
create index if not exists campaigns_kit_idx  on campaigns (kit_hash);
create index if not exists campaigns_size_idx on campaigns (domain_count desc);

-- campaign membership lives in domain_verdicts (org-owned), with a same-org foreign key

-- ===============================================================
-- INTERDICTION  ·  see docs/NPHARD.md
-- ===============================================================
create table if not exists interdiction_plans (
  id              uuid primary key default gen_random_uuid(),
  campaign_id     uuid references campaigns(id) on delete cascade,
  budget_k        smallint not null,
  backend         text not null check (backend in ('cpsat','qaoa','annealing','greedy')),
  fell_back       boolean default false,
  fallback_from   text,
  objective       real,
  domains_killed  integer,
  domains_total   integer,
  coverage_pct    real,
  n_variables     smallint,
  qubit_count     smallint,
  solve_ms        integer,
  valid           boolean default false,   -- passed the validation gate
  created_at      timestamptz default now()
);
create index if not exists plans_campaign_idx on interdiction_plans (campaign_id, created_at desc);
alter table interdiction_plans add column if not exists killed_domain_ids bigint[];
alter table interdiction_plans add column if not exists notes text[];   -- e.g. 'cp-sat feasible (time limit; gap 2.2%)'

create table if not exists plan_targets (
  id        bigserial primary key,
  plan_id   uuid references interdiction_plans(id) on delete cascade,
  node_id   bigint references infra_nodes(id),
  rank      smallint,
  kills     integer,          -- domains this target alone removes
  takedown_route text check (takedown_route in ('hosting','dns','registrar'))
                              -- takedown targets are ip/nameserver/registrar only (spec D9)
);
create index if not exists targets_plan_idx on plan_targets (plan_id, rank);

-- benchmark rows: report every backend, INCLUDING where quantum loses
create table if not exists benchmarks (
  id             bigserial primary key,
  plan_id        uuid references interdiction_plans(id) on delete cascade,
  backend        text not null,
  objective      real,
  domains_killed integer,
  coverage_pct   real,
  solve_ms       integer,
  valid          boolean,
  n_variables    smallint,
  qubit_count    smallint,
  is_best        boolean default false,
  targets        jsonb,
  error          text            -- a failed backend is a row too, never filtered out
);

-- ===============================================================
-- EVIDENCE  ·  see docs/BLOCKCHAIN.md
-- ===============================================================
create table if not exists evidence_bundles (
  id           uuid primary key default gen_random_uuid(),
  domain_id    bigint references domains(id) on delete cascade,
  campaign_id  uuid references campaigns(id) on delete set null,
  bundle_root  text not null,          -- Merkle root, hex
  signature    text not null,          -- Ed25519 over bundle_root
  collector_pk text not null,
  artifact_dir text not null,
  partial      boolean default false,  -- some artifact could not be collected
  created_at   timestamptz default now(),
  anchored_tx  text,                   -- chain tx hash, null until anchored
  anchored_at  timestamptz
);
create index if not exists evidence_domain_idx on evidence_bundles (domain_id);

create table if not exists evidence_artifacts (
  id         bigserial primary key,
  bundle_id  uuid references evidence_bundles(id) on delete cascade,
  name       text not null,            -- screenshot.png, dom.html, ...
  sha256     text not null,
  size_bytes integer,
  unique (bundle_id, name)
);
-- leaves are sorted by name when building the Merkle tree — deterministic
-- order is mandatory or the same evidence yields different roots

-- generated abuse reports. NEVER SENT. See CLAUDE.md §2.1
create table if not exists abuse_reports (
  id         uuid primary key default gen_random_uuid(),
  bundle_id  uuid references evidence_bundles(id) on delete cascade,
  recipient  text,                     -- intended registrar/host, informational
  body       text not null,
  created_at timestamptz default now(),
  sent       boolean default false check (sent = false)   -- enforced: never true
);

-- ===============================================================
-- LEDGER MIRROR  ·  local index of on-chain state
-- ===============================================================
create table if not exists orgs (
  id        bigserial primary key,
  address   text not null unique,
  name      text not null,
  active    boolean default true,
  is_self   boolean default false
);

create table if not exists ledger_events (
  id           bigserial primary key,
  kind         text not null check (kind in
                 ('campaign_published','evidence_anchored','attested','corroborated')),
  tx_hash      text,
  block_number bigint,
  subject      text,                   -- campaignId / bundleId / subjectHash
  org_address  text,
  payload      jsonb,
  observed_at  timestamptz default now()
);
create index if not exists ledger_subject_idx on ledger_events (subject);
create index if not exists ledger_kind_idx    on ledger_events (kind, observed_at desc);

create table if not exists anchor_queue (
  id          bigserial primary key,
  kind        text not null,
  payload     jsonb not null,
  attempts    smallint default 0,
  last_error  text,
  queued_at   timestamptz default now(),
  done        boolean default false
);
alter table anchor_queue add column if not exists next_attempt_at timestamptz default now();
create index if not exists anchor_due_idx on anchor_queue (done, next_attempt_at);
-- anchoring is NON-BLOCKING. If the chain is down, detection, clustering
-- and interdiction all continue. Nothing in the critical path waits here.

-- ===============================================================
-- OPS LOG  ·  append-only. Never UPDATE, never DELETE.
-- ===============================================================
create table if not exists ops_log (
  id       bigserial primary key,
  at       timestamptz default now(),
  channel  text not null check (channel in
             ('stream','triage','confirm','enrich','graph','interdict',
              'evidence','ledger','email','system')),
  severity smallint default 0 check (severity between 0 and 4),
  message  text not null,
  context  jsonb
);
create index if not exists ops_at_idx on ops_log (at desc);
-- null org_id = platform message (stream, triage of the public feed); set = that org's activity only

-- ===============================================================
-- KNOWN KITS  ·  dom hashes seen on confirmed domains, or registered by the
-- seed (source='seed', always labelled). Feeds the kit_dom_hash_match signal.
-- ===============================================================
create table if not exists known_kits (
  dom_hash   text primary key,
  label      text,
  source     text not null check (source in ('confirmed','seed')),
  first_seen timestamptz default now()
);

-- ===============================================================
-- EMAIL ANALYSES  ·  headers + extracted URLs only; bodies are never stored.
-- 'malicious' needs >= 2 strong signals, enforced here as well as in code.
-- ===============================================================
create table if not exists email_analyses (
  id                  uuid primary key default gen_random_uuid(),
  received_at         timestamptz default now(),
  source              text not null check (source in ('analyst','sample')),
  from_addr           text,
  from_etld1          text,
  reply_to_etld1      text,
  return_path_etld1   text,
  auth_results        jsonb,
  received_hops       jsonb,
  urls                text[],
  signals             jsonb not null,
  strong_count        smallint not null,
  verdict             text not null check (verdict in ('malicious','suspicious','clean')),
  linked_campaign_ids uuid[],
  linked_domain_ids   bigint[],
  constraint email_malicious_needs_two_strong check (verdict <> 'malicious' or strong_count >= 2)
);
create index if not exists email_verdict_idx on email_analyses (verdict, received_at desc);

-- ===============================================================
-- OWNERSHIP  ·  org_id on every org-owned table. Idempotent: on an existing database the rows that
-- predate tenancy belong to org1 (the seeded campaign and the live pipeline's confirmations).
-- ===============================================================
do $$
declare t text;
begin
  foreach t in array array['enrichment','infra_nodes','graph_edges','campaigns','interdiction_plans','plan_targets',
                           'benchmarks','evidence_bundles','evidence_artifacts','abuse_reports','email_analyses',
                           'known_kits','ledger_events','anchor_queue'] loop
    execute format('alter table %I add column if not exists org_id bigint references organisations(id)', t);
    execute format('update %I set org_id = 1 where org_id is null', t);
    execute format('alter table %I alter column org_id set default current_org()', t);
    execute format('alter table %I alter column org_id set not null', t);
    execute format('create index if not exists %I on %I (org_id)', t || '_org_idx', t);
  end loop;
end $$;
alter table ops_log add column if not exists org_id bigint references organisations(id);
alter table ops_log alter column org_id set default current_org();
create index if not exists ops_log_org_idx on ops_log (org_id, at desc);

-- keys that were global become per-org
do $$ begin
  if exists (select 1 from pg_constraint where conname = 'enrichment_pkey'
             and pg_get_constraintdef(oid) = 'PRIMARY KEY (domain_id)') then
    alter table enrichment drop constraint enrichment_pkey;
    alter table enrichment add primary key (org_id, domain_id);
  end if;
  if exists (select 1 from pg_constraint where conname = 'known_kits_pkey'
             and pg_get_constraintdef(oid) = 'PRIMARY KEY (dom_hash)') then
    alter table known_kits drop constraint known_kits_pkey;
    alter table known_kits add primary key (org_id, dom_hash);
  end if;
  alter table infra_nodes drop constraint if exists infra_nodes_kind_value_key;
  if not exists (select 1 from pg_constraint where conname = 'infra_nodes_org_kind_value_key') then
    alter table infra_nodes add constraint infra_nodes_org_kind_value_key unique (org_id, kind, value);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'campaigns_org_id_id_key') then
    alter table campaigns add constraint campaigns_org_id_id_key unique (org_id, id);
  end if;
  -- the same name can exist once in the public feed and once privately per org
  alter table domains drop constraint if exists domains_name_key;
  if not exists (select 1 from pg_constraint where conname = 'domains_name_origin_key') then
    alter table domains add constraint domains_name_origin_key unique nulls not distinct (name, origin_org_id);
  end if;
end $$;
create index if not exists infra_org_kind_idx on infra_nodes (org_id, kind, domain_count desc);
create index if not exists campaigns_org_size_idx on campaigns (org_id, domain_count desc, first_seen desc);
create index if not exists email_org_idx on email_analyses (org_id, received_at desc);
create index if not exists plans_org_campaign_idx on interdiction_plans (org_id, campaign_id, created_at desc);
create index if not exists evidence_org_domain_idx on evidence_bundles (org_id, domain_id, created_at desc);
create index if not exists artifacts_bundle_idx on evidence_artifacts (bundle_id);
create index if not exists reports_bundle_idx on abuse_reports (bundle_id, created_at desc);
create index if not exists benchmarks_plan_idx on benchmarks (plan_id);

-- ===============================================================
-- DOMAIN VERDICTS  ·  org-owned confirmation of a (shared or private) domain. One row per org.
-- Absence of a row = still a candidate for that org.
-- ===============================================================
create table if not exists domain_verdicts (
  org_id             bigint not null default current_org() references organisations(id),
  domain_id          bigint not null references domains(id) on delete cascade,
  status             text not null default 'candidate'
                     check (status in ('candidate','confirmed','dismissed','unreachable')),
  confirm_reasons    jsonb,
  confirmed_at       timestamptz,
  confidence         real check (confidence between 0 and 1),
  verdict_at         timestamptz,     -- when ANY verdict was reached (response time)
  campaign_id        uuid,
  campaign_joined_at timestamptz,     -- when clustering placed it in a campaign
  weight             real default 1.0,
  primary key (org_id, domain_id),
  constraint dv_campaign_same_org foreign key (org_id, campaign_id) references campaigns (org_id, id)
    on delete set null (campaign_id),
  -- a confirmed verdict without stored reasons is rejected by the database
  constraint dv_confirmed_has_reasons check (
    status <> 'confirmed' or jsonb_array_length(coalesce(confirm_reasons->'signals', '[]'::jsonb)) > 0),
  -- CLAUDE.md non-negotiable: confirmed needs >= 2 STRONG signals
  constraint dv_confirmed_needs_two_strong check (status <> 'confirmed' or strong_signal_count(confirm_reasons) >= 2)
);
create index if not exists dv_org_status_idx   on domain_verdicts (org_id, status);
create index if not exists dv_org_campaign_idx on domain_verdicts (org_id, campaign_id);
create index if not exists dv_domain_idx       on domain_verdicts (domain_id);

-- move pre-tenancy verdicts out of the shared table (existing databases only)
do $$ begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'domains' and column_name = 'status') then
    insert into domain_verdicts (org_id, domain_id, status, confirm_reasons, confirmed_at, confidence, verdict_at,
                                 campaign_id, campaign_joined_at, weight)
    select 1, id, status, confirm_reasons, confirmed_at, confidence, verdict_at, campaign_id, campaign_joined_at,
           coalesce(weight, 1.0)
    from domains where status <> 'candidate' or campaign_id is not null or confirm_reasons is not null
    on conflict do nothing;
    update domains set origin_org_id = 1 where source in ('seed', 'email', 'sample') and origin_org_id is null;
    alter table domains drop column status cascade, drop column confirm_reasons cascade,
      drop column confirmed_at, drop column confidence, drop column verdict_at, drop column campaign_id cascade,
      drop column campaign_joined_at, drop column weight;
  end if;
end $$;

-- What an org sees of a domain: shared or its own private rows, with ITS verdict (or 'candidate').
create or replace view org_domains with (security_invoker = true) as
select d.id, d.name, d.etld1, d.cert_id, d.first_seen, d.last_seen, d.source, d.ct_seen_at, d.candidate_at,
       d.received_at, d.triage_score, d.triage_reasons, d.brand_matched, d.origin_org_id,
       coalesce(v.status, 'candidate') as status, v.confirm_reasons, v.confirmed_at, v.confidence, v.verdict_at,
       v.campaign_id, v.campaign_joined_at, coalesce(v.weight, 1.0) as weight
from domains d
left join domain_verdicts v on v.domain_id = d.id and v.org_id = current_org()
where d.origin_org_id is null or d.origin_org_id = current_org();

-- ===============================================================
-- RETENTION  ·  raw certs are dropped after 24h or the DB grows by
-- millions of rows per hour. Candidates and above persist.
-- ===============================================================
create or replace function purge_raw_certs() returns void as $$
begin
  delete from certificates c
  where c.ct_seen_at < now() - interval '24 hours'
    and not exists (
      select 1 from domains d join domain_verdicts v on v.domain_id = d.id
      where d.cert_id = c.id and v.status <> 'candidate'
    );
end;
$$ language plpgsql;

-- ===============================================================
-- SUPABASE  ·  every public table is exposed through PostgREST to anyone
-- holding the publishable key. RLS on with ZERO policies => the anon and
-- authenticated roles can read and write nothing. The API connects as
-- postgres, which bypasses RLS. Runs last so it covers every table above.
-- ===============================================================
do $$ declare t record; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;

-- The API's request role. NOLOGIN: reached only via `set local role qcc_app` inside a transaction that
-- has already set app.org_id. Not the table owner, so row-level security applies to it.
do $$ begin create role qcc_app nologin; exception when duplicate_object then null; end $$;
do $$ begin
  execute format('grant qcc_app to %I with set true', current_user);
exception when others then
  execute format('grant qcc_app to %I', current_user);
end $$;
grant usage on schema public to qcc_app;
grant select, insert, update, delete on all tables in schema public to qcc_app;
grant usage, select on all sequences in schema public to qcc_app;
revoke all on api_keys from qcc_app;          -- key material is read only by the auth step, before the role switch
revoke insert, update, delete on organisations, certificates from qcc_app;

do $$
declare t text;
begin
  foreach t in array array['domain_verdicts','enrichment','infra_nodes','graph_edges','campaigns','interdiction_plans',
                           'plan_targets','benchmarks','evidence_bundles','evidence_artifacts','abuse_reports',
                           'email_analyses','known_kits','ledger_events','anchor_queue'] loop
    execute format('drop policy if exists org_isolation on %I', t);
    execute format('create policy org_isolation on %I for all to qcc_app
                    using (org_id = current_org()) with check (org_id = current_org())', t);
  end loop;
end $$;
drop policy if exists shared_or_own on domains;
create policy shared_or_own on domains for select to qcc_app
  using (origin_org_id is null or origin_org_id = current_org());
drop policy if exists own_private_write on domains;
create policy own_private_write on domains for insert to qcc_app with check (origin_org_id = current_org());
drop policy if exists own_private_update on domains;
create policy own_private_update on domains for update to qcc_app
  using (origin_org_id = current_org()) with check (origin_org_id = current_org());
drop policy if exists shared_read on certificates;
create policy shared_read on certificates for select to qcc_app using (true);
drop policy if exists shared_read on organisations;
create policy shared_read on organisations for select to qcc_app using (true);
drop policy if exists platform_or_own on ops_log;
create policy platform_or_own on ops_log for select to qcc_app using (org_id is null or org_id = current_org());
drop policy if exists own_write on ops_log;
create policy own_write on ops_log for insert to qcc_app with check (org_id = current_org());
