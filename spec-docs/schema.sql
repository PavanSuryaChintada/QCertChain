-- SEVER · PostgreSQL 16
-- Run once:  psql $DATABASE_URL -f services/api/schema.sql
-- This file is the source of truth. Do not retype DDL from the docs.

create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;

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
  fingerprint   text,
  san_count     smallint,
  source        text default 'certstream' check (source in ('certstream','replay','seed'))
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

  -- triage (cheap, fast, NEVER a verdict)
  triage_score   real check (triage_score between 0 and 1),
  triage_reasons jsonb,
  brand_matched  text,

  -- confirmation (evidence-based verdict)
  status         text not null default 'candidate'
                 check (status in ('candidate','confirmed','dismissed','unreachable')),
  confirm_reasons jsonb,
  confirmed_at   timestamptz,
  confidence     real check (confidence between 0 and 1),

  campaign_id    uuid,
  weight         real default 1.0
);
create index if not exists domains_status_idx  on domains (status, triage_score desc);
create index if not exists domains_etld1_idx   on domains (etld1);
create index if not exists domains_campaign_idx on domains (campaign_id);
create index if not exists domains_seen_idx    on domains (first_seen desc);

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
                ('ip','asn','nameserver','cert_issuer','kit_hash','favicon_hash')),
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

alter table domains
  add constraint domains_campaign_fk
  foreign key (campaign_id) references campaigns(id) on delete set null;

-- ===============================================================
-- INTERDICTION  ·  see docs/NPHARD.md
-- ===============================================================
create table if not exists interdiction_plans (
  id              uuid primary key default gen_random_uuid(),
  campaign_id     uuid references campaigns(id) on delete cascade,
  budget_k        smallint not null,
  backend         text not null check (backend in ('cpsat','qaoa','annealing','greedy')),
  fell_back       boolean default false,
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

create table if not exists plan_targets (
  id        bigserial primary key,
  plan_id   uuid references interdiction_plans(id) on delete cascade,
  node_id   bigint references infra_nodes(id),
  rank      smallint,
  kills     integer,          -- domains this target alone removes
  takedown_route text         -- registrar | hosting | dns | ca
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
  n_variables    smallint
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
              'evidence','ledger','system')),
  severity smallint default 0 check (severity between 0 and 4),
  message  text not null,
  context  jsonb
);
create index if not exists ops_at_idx on ops_log (at desc);

-- ===============================================================
-- RETENTION  ·  raw certs are dropped after 24h or the DB grows by
-- millions of rows per hour. Candidates and above persist.
-- ===============================================================
create or replace function purge_raw_certs() returns void as $$
begin
  delete from certificates c
  where c.ct_seen_at < now() - interval '24 hours'
    and not exists (
      select 1 from domains d
      where d.cert_id = c.id and d.status <> 'candidate'
    );
end;
$$ language plpgsql;
