# QCertChain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build QCertChain — CT-certificate phishing detection, evidence-gated confirmation, campaign clustering, max-coverage takedown planning (CP-SAT / QAOA / annealing / greedy), signed evidence + Hardhat ledger, email-header analysis, analyst console, and a measured technical report.

**Architecture:** Python 3.11 services (ingest → Redis Streams → triage worker → Postgres(Supabase) → enrich/confirm worker → graph clustering → interdiction/evidence → anchor worker → Hardhat). FastAPI is the only HTTP surface; the Vite/React console talks only to it. `packages/interdict` and `packages/evidence` are standalone libraries with zero imports from `services/`.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 Core + psycopg 3 · Redis 7 · certstream-server-go v1.10.1 · Playwright/httpx · dnspython · tldextract · rapidfuzz · mmh3 · NetworkX · OR-Tools · Qiskit 1.2.4 + Aer 0.15.1 · PyNaCl · web3.py · Solidity 0.8.24 + Hardhat 2 · Vite + React 18 + TS + Tailwind + Cytoscape · scikit-learn (triage LR).

**Spec:** `docs/superpowers/specs/2026-10-06-qcertchain-design.md` + baseline `docs/*.md` (moved from `spec-docs/` in Task 1). Executors read both.

## Global Constraints

- Name is **QCertChain** everywhere (code, UI, docs, DB comments). No "SEVER" string survives (Task 26 greps).
- **No code sends** email, abuse forms, registrar/host API calls, SMTP. `abuse_reports.sent` is constrained `false`.
- Domain `status` ∈ `candidate|confirmed|dismissed|unreachable`. `confirmed` requires **≥ 2 strong signals**. Candidates render **grey** (`--v-candidate #67645E`), never red.
- Email verdict ∈ `malicious|suspicious|clean`; `malicious` requires ≥ 2 strong signals; `suspicious` renders grey.
- Every verdict stores and returns its reasons.
- Quantum framing verbatim where it appears: *"Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path."* Never in a heading, nav item, or speed claim. System runs with Qiskit uninstalled.
- On-chain: hashes/commitments only.
- Replay, seed and sample data are always labelled (`source` column; UI shows it).
- Triage hot path < 5 ms/name. Interdiction CP-SAT < 1 s. Clustering 500 nodes < 2 s. QAOA ≤ 24 qubits, < 15 s.
- Takedown target node kinds: **`ip`, `nameserver`, `registrar` only** (routes: hosting, dns, registrar). `asn`, `cert_issuer`, `kit_hash`, `favicon_hash` are clustering evidence only.
- Edge weights: kit_hash 1.00 · favicon_hash 0.85 · ip 0.80 · nameserver 0.60 · asn 0.35 · cert_issuer 0.15 · registrar 0.15. Cluster threshold 0.6 — never lowered.
- Database is Supabase Postgres 17 via session pooler (`DATABASE_URL`); RLS enabled on every table, no policies. Tests use a local Docker `postgres:17` (`TEST_DATABASE_URL`), never Supabase.
- certstream-server-go pinned `v1.10.1`, `recovery.enabled: false`; ingest dedups on leaf fingerprint.
- If any external source (certstream server, Tranco, OpenPhish, RDAP) is unreachable: report it to the owner; no silent substitution.
- Design tokens from `docs/DESIGN.md` §3–4 verbatim; bans in §2 enforced (no gradients, purple, glow, radius > 2px, emoji, pills).
- No new dependency beyond: the TRD §7 list, `qiskit`/`qiskit-aer`, `scikit-learn`/`joblib` (MODELS.md), `web3` (contracts BUILD_SPEC §8), `pyyaml` (brands.yaml), `pytest`/`pytest-asyncio`/`fakeredis` (tests), `pyasn` (DATA.md), `vitest`/`@testing-library/react`/`jsdom` (console tests required by apps BUILD_SPEC §11), `cytoscape`, `cytoscape-cose-bilkent`, `@tanstack/react-query`, `react-router-dom` (the `/org2` route in apps BUILD_SPEC §8). Anything else: stop and ask.

## Review Focus

1. **Internationalised / punycode domain names** (`xn--sbi-xxx.com`, Cyrillic `аmazon`) — triage must decode IDNA and still flag homoglyph lookalikes, and must not crash on invalid punycode. Test added in Task 6.
2. **Wildcard and malformed SANs** (`*.sbi-login.top`, empty string, trailing dot, IP-literal SAN) — must strip `*.`, skip IPs/empties, never crash the stream. Test added in Task 4.
3. **Duplicate certificates** (same cert from multiple logs, precert + final cert) — must yield one domain row, not duplicates or a crash on the unique constraint. Tests added in Task 4 and Task 13.
4. **Malformed / partial email headers** (no Authentication-Results, folded headers, non-UTF-8 bytes, body-only paste) — analyzer returns a result with `absent` fields, never 500. Test added in Task 19.
5. **Interdiction edge cases** (k larger than node count, campaign with zero takedownable nodes, k=0) — 422 / 409 per API_CONTRACT §8, never a crash or an over-budget plan. Tests added in Task 8 and Task 16.

---

## File map

```
QCertChain/
├── CLAUDE.md  README.md  .env(.gitignored)  .env.example  .gitignore  docker-compose.yml  pytest.ini
├── docs/                         baseline specs (moved) + REPORT.md + superpowers/
├── data/  brands.yaml  allowlist.txt(gen)  capture.jsonl(gen)  MANIFEST.md  certstream-config.yaml
├── supabase/migrations/20261006000000_init.sql      generated from services/api/schema.sql + RLS
├── scripts/  apply_schema.py  genkey.py  fetch_allowlist.py  evaluate.py  build_report.py  bench_triage.py
├── reports/  metrics.json(gen)
├── services/
│   ├── __init__.py  config.py
│   ├── ingest/  certparse.py  capture.py  stream.py  brands.py  homoglyph.py  triage.py
│   ├── ml/      features.py  datasets.py  split.py  train_triage.py  evaluate.py  brand_refs.py  artifacts/
│   ├── enrich/  fingerprint.py  enrichers.py  fetch.py  confirm.py
│   ├── graph/   build.py  cluster.py
│   ├── email/   parse.py  signals.py  analyze.py  samples/*.eml  samples/labels.json
│   ├── api/     main.py  db.py  models.py  repo.py  seed.py  ledger_service.py  schema.sql  Dockerfile
│   │   ├── routes/  stream.py domains.py campaigns.py plans.py evidence.py ledger.py email.py ops.py
│   │   └── workers/ triage_worker.py  enrich_worker.py  anchor_worker.py
│   └── tests/   conftest.py  test_*.py  fixtures/
├── packages/
│   ├── interdict/  pyproject.toml  src/interdict/{types,reduce,qubo,penalties,router,benchmark}.py
│   │               src/interdict/solvers/{greedy,cpsat,annealing,qaoa}.py  tests/
│   └── evidence/   pyproject.toml  src/evidence/{merkle,bundle,report}.py  tests/
├── contracts/      hardhat project per contracts/BUILD_SPEC.md
└── apps/console/   Vite app per apps/BUILD_SPEC.md + views/EmailAnalyzer.tsx + views/Reports? (no — report is docs/REPORT.md)
```

---

## Phase 0 — Foundation

### Task 1: Repo restructure, rename, Python env, config

**Files:**
- Move: `spec-docs/*.md` → `docs/` (except `CLAUDE.md` → root, `README.md` → root, `BUILD_SPEC.md` → `contracts/BUILD_SPEC.md`), `spec-docs/mnt/user-data/outputs/sever/apps/BUILD_SPEC.md` → `apps/BUILD_SPEC.md`, `spec-docs/schema.sql` → `services/api/schema.sql`, `spec-docs/docker-compose.yml` → root, `spec-docs/.env.example` → root. Delete `spec-docs/CLAUDE (1).md`, then `spec-docs/`.
- Create: `services/__init__.py`, `services/config.py`, `services/api/requirements.txt`, `pytest.ini`, `services/tests/test_config.py`
- Modify: every moved file — find-replace `SEVER`→`QCertChain`, `sever`→`qcertchain` (DB user/name strings, compose project name, User-Agent).

**Interfaces:**
- Produces: `from services.config import SETTINGS` — frozen dataclass with fields: `database_url, test_database_url, redis_url, certstream_url, stream_mode, replay_file, replay_speed, triage_threshold, triage_model_path, brands_file, allowlist_file, confirm_timeout_s, enrich_workers, per_host_rate_limit_s, user_agent, cluster_edge_threshold, interdict_budget_k, interdict_backend, max_qubo_variables, evidence_dir, collector_private_key, chain_rpc, org_private_key, org2_private_key, raw_cert_retention_h`. Loaded from process env, falling back to `.env` at repo root (hand-parsed `KEY=VALUE`, `#` comments), falling back to TRD §8 defaults.

- [ ] **Step 1: Move files with `git mv`, delete the stale copy, rename**

```bash
cd C:/Users/prave/Downloads/QCertChain
mkdir -p docs contracts apps services/api
for f in ARCHITECTURE PRD TRD NPHARD BLOCKCHAIN MODELS DATA API_CONTRACT DESIGN WORKFLOW RUNBOOK; do git mv spec-docs/$f.md docs/$f.md; done
git mv spec-docs/CLAUDE.md CLAUDE.md && git mv spec-docs/README.md README.md
git mv spec-docs/BUILD_SPEC.md contracts/BUILD_SPEC.md
git mv spec-docs/mnt/user-data/outputs/sever/apps/BUILD_SPEC.md apps/BUILD_SPEC.md
git mv spec-docs/schema.sql services/api/schema.sql
git mv spec-docs/docker-compose.yml docker-compose.yml && git mv spec-docs/.env.example .env.example
git rm -q "spec-docs/CLAUDE (1).md"
grep -rl "SEVER\|sever" CLAUDE.md README.md docs contracts apps services docker-compose.yml .env.example | xargs sed -i 's/SEVER/QCertChain/g; s/\bsever\b/qcertchain/g; s/SEVER-Scanner/QCertChain-Scanner/g'
grep -rn "SEVER\|\bsever\b" CLAUDE.md README.md docs contracts apps services docker-compose.yml .env.example || echo "rename clean"
```
Expected: `rename clean`. Also fix `README.md`/`CLAUDE.md` path references (`docs/…` already correct after the move).

- [ ] **Step 2: Create the venv and requirements**

`services/api/requirements.txt`:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
sqlalchemy==2.0.36
psycopg[binary]==3.2.3
redis==5.2.1
websockets==14.1
httpx==0.28.1
playwright==1.49.0
dnspython==2.7.0
python-whois==0.9.5
tldextract==5.1.3
rapidfuzz==3.10.1
mmh3==5.0.1
pynacl==1.5.0
ortools==9.11.4210
networkx==3.4.2
pyyaml==6.0.2
web3==7.6.0
python-multipart==0.0.20
scikit-learn==1.5.2
joblib==1.4.2
numpy==1.26.4
pytest==8.3.4
pytest-asyncio==0.24.0
fakeredis==2.26.2
-e packages/interdict
-e packages/evidence
```
`services/api/requirements-quantum.txt`:
```
qiskit==1.2.4
qiskit-aer==0.15.1
```
(`pyasn` is attempted separately in Task 12 — it needs a C compiler on Windows; Team Cymru DNS is the spec-listed alternative.)

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -q --upgrade pip
```
(The `-e packages/...` lines resolve once Tasks 7 and 10 create those packages; until then install with `grep -v "^-e" services/api/requirements.txt > /tmp/r.txt && .venv/Scripts/pip install -r /tmp/r.txt`.)

- [ ] **Step 3: Write the failing config test**

`services/tests/test_config.py`:
```python
from services.config import load_settings

def test_defaults_when_env_empty(tmp_path, monkeypatch):
    for k in ["TRIAGE_THRESHOLD", "INTERDICT_BACKEND", "CLUSTER_EDGE_THRESHOLD"]:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(env_file=tmp_path / "missing.env")
    assert s.triage_threshold == 0.45
    assert s.interdict_backend == "cpsat"
    assert s.cluster_edge_threshold == 0.6
    assert s.max_qubo_variables == 24

def test_env_file_parsed_and_process_env_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\nTRIAGE_THRESHOLD=0.5\nINTERDICT_BUDGET_K=7  # trailing\n")
    monkeypatch.setenv("INTERDICT_BUDGET_K", "3")
    monkeypatch.delenv("TRIAGE_THRESHOLD", raising=False)
    s = load_settings(env_file=f)
    assert s.triage_threshold == 0.5
    assert s.interdict_budget_k == 3
```
`pytest.ini`:
```ini
[pytest]
testpaths = services/tests packages/interdict/tests packages/evidence/tests
asyncio_mode = auto
markers =
    db: needs TEST_DATABASE_URL postgres
    network: touches the internet
    quantum: needs qiskit
```

- [ ] **Step 4: Run — expect ImportError.** `.venv/Scripts/python -m pytest services/tests/test_config.py -q`

- [ ] **Step 5: Implement `services/config.py`**

```python
"""Single source of configuration. Never hardcode a setting twice (TRD §8)."""
from __future__ import annotations
import os
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    test_database_url: str = "postgresql+psycopg://qcertchain:qcertchain@localhost:5433/qcertchain_test"
    redis_url: str = "redis://localhost:6379"
    certstream_url: str = "ws://localhost:8080/full-stream"
    stream_mode: str = "live"
    replay_file: str = "data/capture.jsonl"
    replay_speed: float = 1.0
    triage_threshold: float = 0.45
    triage_model_path: str = "services/ml/artifacts/triage_lr.joblib"
    brands_file: str = "data/brands.yaml"
    allowlist_file: str = "data/allowlist.txt"
    confirm_timeout_s: float = 15.0
    enrich_workers: int = 4
    per_host_rate_limit_s: float = 2.0
    user_agent: str = "QCertChain-Scanner/0.1 (phishing research)"
    cluster_edge_threshold: float = 0.6
    interdict_budget_k: int = 5
    interdict_backend: str = "cpsat"
    max_qubo_variables: int = 24
    evidence_dir: str = "data/evidence"
    collector_private_key: str = ""
    chain_rpc: str = "http://localhost:8545"
    org_private_key: str = ""
    org2_private_key: str = ""
    raw_cert_retention_h: int = 24

def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        out[k.strip()] = v
    return out

def load_settings(env_file: Path | None = None) -> Settings:
    file_vals = _parse_env_file(env_file or ROOT / ".env")
    kwargs = {}
    for f in fields(Settings):
        raw = os.environ.get(f.name.upper(), file_vals.get(f.name.upper()))
        if raw is None or raw == "":
            continue
        typ = type(f.default)
        kwargs[f.name] = typ(raw) if typ in (int, float) else raw
    return Settings(**kwargs)

SETTINGS = load_settings()
```

- [ ] **Step 6: Run tests — PASS.** Also run the core-import checkpoint from RUNBOOK §3 (minus quantum). Expected `core ok`.

- [ ] **Step 7: Commit** `git add -A && git commit -m "chore: restructure repo, rename to QCertChain, config + deps"` (verify `.env` not staged: `git diff --cached --name-only | grep -x .env && exit 1`).

---

### Task 2: Supabase schema + RLS, local test Postgres, Redis

**Files:**
- Modify: `services/api/schema.sql`
- Create: `scripts/apply_schema.py`, `supabase/migrations/20261006000000_init.sql`, `services/tests/conftest.py`, `services/tests/test_schema.py`
- Modify: `docker-compose.yml` (drop `postgres`; add `postgres-test` on 5433 under profile `test`; add `certstream` in Task 3)

**Interfaces:**
- Produces: schema with these additions to the baseline: `domains.source text default 'certstream' check (source in ('certstream','replay','seed','email','sample'))`, `domains.ct_seen_at timestamptz`, `domains.candidate_at timestamptz`, `domains.campaign_joined_at timestamptz`, `certificates.source` check extended likewise, `certificates.fingerprint` **unique**, `infra_nodes.kind` check adds `'registrar'`, `plan_targets.takedown_route` check `in ('hosting','dns','registrar')`, `ops_log.channel` adds `'email'`, new tables `known_kits`, `email_analyses`, RLS on all tables.
- Produces fixture `db_engine` (session-scoped SQLAlchemy engine on `TEST_DATABASE_URL`, schema applied fresh) and `db` (per-test connection inside a rolled-back transaction).

- [ ] **Step 1: Edit `schema.sql`** — apply the additions above. Make the FK idempotent:

```sql
do $$ begin
  alter table domains add constraint domains_campaign_fk
    foreign key (campaign_id) references campaigns(id) on delete set null;
exception when duplicate_object then null; end $$;
```
New tables (append before RETENTION):
```sql
-- KNOWN KITS · dom hashes seen on confirmed domains or registered by the seed (source='seed')
create table if not exists known_kits (
  dom_hash   text primary key,
  label      text,
  source     text not null check (source in ('confirmed','seed')),
  first_seen timestamptz default now()
);

-- EMAIL ANALYSES · headers + extracted URLs only; bodies are never stored
create table if not exists email_analyses (
  id                 uuid primary key default gen_random_uuid(),
  received_at        timestamptz default now(),
  source             text not null check (source in ('analyst','sample')),
  from_addr          text,
  from_etld1         text,
  reply_to_etld1     text,
  return_path_etld1  text,
  auth_results       jsonb,
  received_hops      jsonb,
  urls               text[],
  signals            jsonb not null,
  strong_count       smallint not null,
  verdict            text not null check (verdict in ('malicious','suspicious','clean')),
  linked_campaign_ids uuid[],
  linked_domain_ids  bigint[],
  check (verdict <> 'malicious' or strong_count >= 2)
);
create index if not exists email_verdict_idx on email_analyses (verdict, received_at desc);
```
Add to `domains`: `check (status <> 'confirmed' or jsonb_array_length(coalesce(confirm_reasons->'signals','[]'::jsonb)) > 0)` — confirmed without stored reasons is rejected by the DB.

RLS block at the end:
```sql
-- SUPABASE: every public table is exposed via PostgREST to the publishable key.
-- RLS on, zero policies => anon/authenticated roles read and write nothing.
-- The API connects as postgres, which bypasses RLS.
do $$ declare t record; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;
```

- [ ] **Step 2: Write `scripts/apply_schema.py`**

```python
"""Apply services/api/schema.sql. Usage: python scripts/apply_schema.py [--url URL] [--write-migration]"""
import argparse, shutil, psycopg
from pathlib import Path
from services.config import SETTINGS, ROOT

SCHEMA = ROOT / "services/api/schema.sql"
MIGRATION = ROOT / "supabase/migrations/20261006000000_init.sql"

def plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")

def apply(url: str) -> None:
    with psycopg.connect(plain(url), autocommit=True) as c:
        c.execute(SCHEMA.read_text(encoding="utf-8"))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=SETTINGS.database_url)
    ap.add_argument("--write-migration", action="store_true")
    a = ap.parse_args()
    if a.write_migration:
        MIGRATION.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SCHEMA, MIGRATION)
    apply(a.url)
    print("schema applied")
```

- [ ] **Step 3: Compose changes** — remove the `postgres` service and every `depends_on: postgres`; services get `DATABASE_URL` from `.env`. Add:

```yaml
  postgres-test:
    image: postgres:17-alpine
    profiles: [test]
    environment: {POSTGRES_USER: qcertchain, POSTGRES_PASSWORD: qcertchain, POSTGRES_DB: qcertchain_test}
    ports: ["5433:5432"]
    tmpfs: [/var/lib/postgresql/data]
```

- [ ] **Step 4: Write failing tests** `services/tests/conftest.py`:

```python
import os, pytest, sqlalchemy as sa
from services.config import SETTINGS
from scripts.apply_schema import apply, plain

TEST_URL = os.environ.get("TEST_DATABASE_URL", SETTINGS.test_database_url)

@pytest.fixture(scope="session")
def db_engine():
    assert "supabase" not in TEST_URL, "tests must never run against Supabase"
    with sa.create_engine(TEST_URL).begin() as c:
        c.exec_driver_sql("drop schema public cascade; create schema public;")
    apply(TEST_URL)
    eng = sa.create_engine(TEST_URL)
    yield eng
    eng.dispose()

@pytest.fixture
def db(db_engine):
    conn = db_engine.connect()
    tx = conn.begin()
    yield conn
    tx.rollback(); conn.close()
```
`services/tests/test_schema.py`:
```python
import pytest, sqlalchemy as sa
pytestmark = pytest.mark.db

def test_all_tables_have_rls(db):
    rows = db.execute(sa.text(
        "select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relkind='r' and not c.relrowsecurity")).all()
    assert rows == []

def test_abuse_report_cannot_be_sent(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into abuse_reports(body, sent) values ('x', true)"))

def test_confirmed_without_reasons_rejected(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into domains(name, etld1, status) values ('a.top','a.top','confirmed')"))

def test_email_malicious_needs_two_strong(db):
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.text("insert into email_analyses(source, signals, strong_count, verdict) "
                           "values ('sample','[]',1,'malicious')"))

def test_schema_is_idempotent(db_engine):
    from scripts.apply_schema import apply
    from services.tests.conftest import TEST_URL
    apply(TEST_URL)  # second run must not raise
```

- [ ] **Step 5: Run** `docker compose --profile test up -d postgres-test redis && .venv/Scripts/python -m pytest -m db -q` → FAIL until schema edits are complete; then PASS.

- [ ] **Step 6: Apply to Supabase** `.venv/Scripts/python scripts/apply_schema.py --url "$DATABASE_URL_DIRECT" --write-migration` (direct IPv6 host works from this machine). Verify the publishable key sees nothing:

```bash
curl -s "https://obyexvvwlirnijucyiob.supabase.co/rest/v1/domains?select=*" -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```
Expected: `[]` (RLS, no policies). Insert a row via psql-equivalent then curl again → still `[]`. Delete the row.

- [ ] **Step 7: Commit** `feat(db): schema additions (email, registrar, stage timestamps, known kits) + RLS, applied to Supabase`.

---

### Task 3: Self-hosted certstream + 30-minute capture

**Files:**
- Create: `data/certstream-config.yaml`, `services/ingest/__init__.py`, `services/ingest/capture.py`
- Modify: `docker-compose.yml` (add `certstream`)

**Interfaces:**
- Produces: websocket at `ws://localhost:8080/full-stream` speaking the certstream protocol; `data/capture.jsonl` (one raw `certificate_update` JSON per line).

- [ ] **Step 1: Config** `data/certstream-config.yaml` (from upstream `config.sample.yaml`, v1.10.1):

```yaml
webserver:
  listen_addr: "0.0.0.0"
  listen_port: 8080
  real_ip: false
  whitelist: []          # local docker network only; port not published publicly in Railway (private networking)
  full_url: "/full-stream"
  lite_url: "/"
  domains_only_url: "/domains-only"
  compression_enabled: false
prometheus:
  enabled: true
  listen_addr: "0.0.0.0"
  listen_port: 8080
  metrics_url: "/metrics"
  whitelist: []
general:
  disable_default_logs: false
  excluded_logs: []      # trimmed in Step 4 only after measuring volume, reported to owner
  buffer_sizes: {websocket: 300, ctlog: 1000, dispatcher: 10000}
  drop_old_logs: true
  recovery:
    enabled: false       # known issue: tiled-worker restart replays millions of entries
```

- [ ] **Step 2: Compose service**

```yaml
  certstream:
    image: 0rickyy0/certstream-server-go:v1.10.1
    ports: ["8080:8080"]
    volumes: ["./data/certstream-config.yaml:/app/config.yaml:ro"]
    restart: unless-stopped
```
`docker compose up -d certstream && docker compose logs --tail 50 certstream` — expect log workers starting for RFC 6962 and tiled logs (Let's Encrypt sycamore/willow listed). If the image path for config differs, read `docker run --rm 0rickyy0/certstream-server-go:v1.10.1 --help` and fix the mount.

- [ ] **Step 3: `services/ingest/capture.py`**

```python
"""Record raw certstream messages to JSONL. Demo insurance (DATA.md §1)."""
import argparse, asyncio, json, time
import websockets
from services.config import SETTINGS

async def capture(url: str, minutes: float, out: str) -> int:
    n, deadline = 0, time.time() + minutes * 60
    with open(out, "a", encoding="utf-8") as f:
        while time.time() < deadline:
            try:
                async with websockets.connect(url, max_size=2**24, open_timeout=20) as ws:
                    while time.time() < deadline:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        msg = json.loads(raw)
                        if msg.get("message_type") == "certificate_update":
                            f.write(json.dumps(msg, separators=(",", ":")) + "\n"); n += 1
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
                print(f"capture: connection issue {type(e).__name__}: {e}; retrying in 5s")
                await asyncio.sleep(5)
    return n

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--out", default="data/capture.jsonl")
    ap.add_argument("--url", default=SETTINGS.certstream_url)
    a = ap.parse_args()
    print("captured", asyncio.run(capture(a.url, a.minutes, a.out)))
```

- [ ] **Step 4: Run a 2-minute probe, measure volume, then start the 30-minute capture in the background**

```bash
.venv/Scripts/python -m services.ingest.capture --minutes 2 --out data/probe.jsonl && wc -l data/probe.jsonl
.venv/Scripts/python -m services.ingest.capture --minutes 30 --out data/capture.jsonl   # background
```
Checkpoint: probe has thousands of lines. **Report the measured certs/sec to the owner.** If the rate overwhelms the machine (CPU > 80% sustained in certstream container), propose specific `excluded_logs` entries (duplicate-coverage operators) and wait for a yes before applying. If the probe has 0 lines after 2 min: stop and report (do not substitute).

- [ ] **Step 5: Commit** `feat(ingest): self-hosted certstream-server-go v1.10.1 + capture` (capture.jsonl is git-ignored).

---

## Phase 1 — Detection

### Task 4: Cert parsing, dedup, stream consumer (live + replay)

**Files:**
- Create: `services/ingest/certparse.py`, `services/ingest/stream.py`, `services/tests/test_certparse.py`, `services/tests/test_stream.py`, `services/tests/fixtures/cert_update.json`

**Interfaces:**
- Produces:
  - `CertRecord` dataclass: `fingerprint: str, names: list[str], overflow: int, issuer: str|None, not_before: datetime|None, not_after: datetime|None, serial: str|None, san_count: int, seen_at: datetime, source: str`
  - `parse_message(msg: dict, source: str = "certstream") -> CertRecord | None`
  - `normalize_name(raw: str) -> str | None` — lowercases, strips `*.` and trailing `.`, IDNA-decodes `xn--` labels to Unicode, returns None for empty / IP literal / no dot.
  - `class SeenFingerprints(maxlen=500_000)` with `.add(fp) -> bool` (True if new).
  - `backoff_delays()` → iterator 1,2,4,8,16,32,60,60,…
  - Redis: stream `certs:raw` entries `{"cert": <CertRecord json>}`; hash `stream:state` fields `mode, connection, certs_per_sec, names_per_sec, replay_file, started_at, last_heartbeat`; heartbeat every 5 s.
  - `async run(mode: str, redis, *, url, replay_file, speed, stop: asyncio.Event)`; CLI `python -m services.ingest.stream`. Mode is re-read from Redis key `stream:mode_request` (set by the API) every heartbeat; switching restarts the source loop.

- [ ] **Step 1: Fixture** — take one real line from `data/probe.jsonl`, save as `services/tests/fixtures/cert_update.json`, then hand-edit `leaf_cert.all_domains` to `["*.sbi-login.top", "sbi-login.top", "", "192.168.0.1", "xn--80ak6aa92e.com", "Example.COM."]`.

- [ ] **Step 2: Failing tests** `test_certparse.py`:

```python
import json
from pathlib import Path
from services.ingest.certparse import parse_message, normalize_name, SeenFingerprints

FIX = json.loads((Path(__file__).parent / "fixtures/cert_update.json").read_text())

def test_wildcards_ips_empties_handled():
    r = parse_message(FIX)
    assert r.names == ["sbi-login.top", "аррӏе.com", "example.com"]  # deduped, wildcard stripped
    assert r.san_count == 6

def test_normalize_edge_cases():
    assert normalize_name("*.A.Example.com.") == "a.example.com"
    assert normalize_name("") is None
    assert normalize_name("10.0.0.1") is None
    assert normalize_name("localhost") is None
    assert normalize_name("xn--invalid--.com") == "xn--invalid--.com"  # undecodable stays raw, no crash

def test_san_cap_200():
    msg = json.loads(json.dumps(FIX))
    msg["data"]["leaf_cert"]["all_domains"] = [f"d{i}.example.org" for i in range(350)]
    r = parse_message(msg)
    assert len(r.names) == 200 and r.overflow == 150

def test_non_cert_message_ignored():
    assert parse_message({"message_type": "heartbeat"}) is None

def test_dedup_same_cert_from_two_logs():
    s = SeenFingerprints(maxlen=3)
    assert s.add("a") and not s.add("a")
    for x in "bcd": s.add(x)
    assert s.add("a")  # evicted, LRU
```
`test_stream.py` (uses `fakeredis.aioredis`):
```python
import asyncio, json, fakeredis.aioredis as fr
from itertools import islice
from pathlib import Path
from services.ingest.stream import backoff_delays, run

def test_backoff_caps_at_60():
    assert list(islice(backoff_delays(), 9)) == [1, 2, 4, 8, 16, 32, 60, 60, 60]

async def test_replay_pushes_names_and_labels_mode(tmp_path):
    line = (Path(__file__).parent / "fixtures/cert_update.json").read_text().replace("\n", "")
    f = tmp_path / "cap.jsonl"; f.write_text(line + "\n" + line + "\n")  # duplicate cert
    r = fr.FakeRedis(decode_responses=True); stop = asyncio.Event()
    task = asyncio.create_task(run("replay", r, url="", replay_file=str(f), speed=1000, stop=stop))
    await asyncio.sleep(0.5); stop.set(); await task
    entries = await r.xrange("certs:raw")
    assert len(entries) == 1                                    # dedup on fingerprint
    assert json.loads(entries[0][1]["cert"])["source"] == "replay"
    st = await r.hgetall("stream:state")
    assert st["mode"] == "replay" and st["connection"] == "replay"
```

- [ ] **Step 3: Run — FAIL.**

- [ ] **Step 4: Implement `certparse.py`**

```python
from __future__ import annotations
import ipaddress, json
from collections import OrderedDict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

SAN_CAP = 200

@dataclass
class CertRecord:
    fingerprint: str
    names: list[str]
    overflow: int
    issuer: str | None
    not_before: datetime | None
    not_after: datetime | None
    serial: str | None
    san_count: int
    seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "certstream"

    def to_json(self) -> str:
        d = asdict(self)
        for k in ("not_before", "not_after", "seen_at"):
            d[k] = d[k].isoformat() if d[k] else None
        return json.dumps(d, ensure_ascii=False)

    @staticmethod
    def from_json(s: str) -> "CertRecord":
        d = json.loads(s)
        for k in ("not_before", "not_after", "seen_at"):
            d[k] = datetime.fromisoformat(d[k]) if d[k] else None
        return CertRecord(**d)

def _decode_label(label: str) -> str:
    if label.startswith("xn--"):
        try:
            return label.encode("ascii").decode("idna")
        except (UnicodeError, ValueError):
            return label
    return label

def normalize_name(raw: str) -> str | None:
    n = (raw or "").strip().lower().rstrip(".")
    while n.startswith("*."):
        n = n[2:]
    if not n or "." not in n:
        return None
    try:
        ipaddress.ip_address(n); return None
    except ValueError:
        pass
    return ".".join(_decode_label(l) for l in n.split("."))

def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(v, timezone.utc) if isinstance(v, (int, float)) else None

def parse_message(msg: dict, source: str = "certstream") -> CertRecord | None:
    if msg.get("message_type") != "certificate_update":
        return None
    leaf = msg["data"]["leaf_cert"]
    raw = leaf.get("all_domains") or []
    seen, names = set(), []
    for r in raw:
        n = normalize_name(r)
        if n and n not in seen:
            seen.add(n); names.append(n)
    overflow = max(0, len(names) - SAN_CAP)
    return CertRecord(
        fingerprint=leaf.get("sha256") or leaf.get("fingerprint") or "",
        names=names[:SAN_CAP], overflow=overflow,
        issuer=(leaf.get("issuer") or {}).get("O"),
        not_before=_ts(leaf.get("not_before")), not_after=_ts(leaf.get("not_after")),
        serial=leaf.get("serial_number"), san_count=len(raw), source=source)

class SeenFingerprints:
    def __init__(self, maxlen: int = 500_000):
        self._d: OrderedDict[str, None] = OrderedDict(); self._max = maxlen
    def add(self, fp: str) -> bool:
        if fp in self._d:
            self._d.move_to_end(fp); return False
        self._d[fp] = None
        if len(self._d) > self._max:
            self._d.popitem(last=False)
        return True
```
(Check the fixture: if certstream-server-go's leaf has `sha256` vs `fingerprint`, keep both lookups; the test fixture is the arbiter. Fix the `test_wildcards…` expected IDNA string to the actual decode of `xn--80ak6aa92e` — `"аррӏе"` Cyrillic — by running `"xn--80ak6aa92e".encode().decode("idna")` once.)

- [ ] **Step 5: Implement `stream.py`**

```python
"""CT consumer: live (certstream websocket) or replay (capture.jsonl). ONE process only."""
from __future__ import annotations
import asyncio, json, time
from datetime import datetime, timezone
import websockets, redis.asyncio as aioredis
from services.config import SETTINGS
from services.ingest.certparse import parse_message, SeenFingerprints

STREAM, STATE, MODE_REQ = "certs:raw", "stream:state", "stream:mode_request"

def backoff_delays():
    d = 1
    while True:
        yield d
        d = min(d * 2, 60) if d < 32 else 60

class Counter:
    def __init__(self): self.certs = self.names = 0; self.t0 = time.time()
    def rates(self):
        dt = max(time.time() - self.t0, 1e-6); r = (self.certs / dt, self.names / dt)
        self.certs = self.names = 0; self.t0 = time.time(); return r

async def _emit(r, rec, seen, ctr):
    if not rec or not rec.names or not seen.add(rec.fingerprint or rec.to_json()):
        return
    await r.xadd(STREAM, {"cert": rec.to_json()}, maxlen=1_000_000, approximate=True)
    ctr.certs += 1; ctr.names += len(rec.names)

async def _state(r, **kw):
    kw["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    await r.hset(STATE, mapping={k: ("" if v is None else str(v)) for k, v in kw.items()})

async def _heartbeat(r, mode_ref, conn_ref, ctr, replay_file, stop):
    while not stop.is_set():
        c, n = ctr.rates()
        await _state(r, mode=mode_ref[0], connection=conn_ref[0], certs_per_sec=round(c, 1),
                     names_per_sec=round(n, 1), replay_file=replay_file if mode_ref[0] == "replay" else "")
        try: await asyncio.wait_for(stop.wait(), 5)
        except asyncio.TimeoutError: pass

async def _live(r, url, seen, ctr, conn_ref, stop):
    delays = backoff_delays()
    while not stop.is_set():
        try:
            async with websockets.connect(url, max_size=2**24, open_timeout=20) as ws:
                conn_ref[0] = "connected"; delays = backoff_delays()
                while not stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    await _emit(r, parse_message(json.loads(raw), "certstream"), seen, ctr)
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException):
            conn_ref[0] = "reconnecting"
            try: await asyncio.wait_for(stop.wait(), next(delays))
            except asyncio.TimeoutError: pass

async def _replay(r, path, speed, seen, ctr, stop):
    prev = None
    while not stop.is_set():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if stop.is_set(): return
                msg = json.loads(line)
                ts = msg.get("data", {}).get("seen")
                if prev is not None and ts is not None and speed > 0:
                    await asyncio.sleep(max(0.0, min((ts - prev) / speed, 2.0)))
                prev = ts if ts is not None else prev
                await _emit(r, parse_message(msg, "replay"), seen, ctr)
        await asyncio.sleep(0)  # loop the file

async def run(mode, r, *, url, replay_file, speed, stop):
    seen, ctr = SeenFingerprints(), Counter()
    mode_ref, conn_ref = [mode], ["replay" if mode == "replay" else "reconnecting"]
    hb = asyncio.create_task(_heartbeat(r, mode_ref, conn_ref, ctr, replay_file, stop))
    src = (_replay(r, replay_file, speed, seen, ctr, stop) if mode == "replay"
           else _live(r, url, seen, ctr, conn_ref, stop))
    try:
        await src
    finally:
        await _state(r, mode=mode_ref[0], connection=conn_ref[0], certs_per_sec=0, names_per_sec=0,
                     replay_file=replay_file if mode == "replay" else "")
        stop.set(); await hb

async def main():
    r = aioredis.from_url(SETTINGS.redis_url, decode_responses=True)
    while True:
        req = await r.hgetall(MODE_REQ)
        mode = req.get("mode") or SETTINGS.stream_mode
        speed = float(req.get("speed") or SETTINGS.replay_speed)
        stop = asyncio.Event()
        async def watch():
            while not stop.is_set():
                await asyncio.sleep(2)
                if (await r.hget(MODE_REQ, "mode") or SETTINGS.stream_mode) != mode: stop.set()
        w = asyncio.create_task(watch())
        await run(mode, r, url=SETTINGS.certstream_url, replay_file=SETTINGS.replay_file, speed=speed, stop=stop)
        w.cancel()

if __name__ == "__main__":
    asyncio.run(main())
```
Note: `_emit` already labels the source; the replay test's `run()` returns once the file loops are stopped.

- [ ] **Step 6: Run tests — PASS.** Then smoke: `docker compose up -d redis certstream; python -m services.ingest.stream` for 30 s, `redis-cli XLEN certs:raw` > 0, `redis-cli HGETALL stream:state` shows `connected`.

- [ ] **Step 7: Commit** `feat(ingest): cert parsing, fingerprint dedup, live+replay stream with heartbeat`.

---

### Task 5: Brands and allowlist data

**Files:**
- Create: `data/brands.yaml`, `scripts/fetch_allowlist.py`, `data/MANIFEST.md`, `services/ingest/brands.py`, `services/tests/test_brands.py`

**Interfaces:**
- Produces: `Brand(name, tokens: list[str], legit_domains: list[str], sector)`; `BrandIndex` with `.brands`, `.legit_etld1s: set[str]`, `.by_token: dict[str, Brand]`, `.tokens_by_len: dict[int, list[str]]`; `load_brands(path) -> BrandIndex`; `load_allowlist(path, brands) -> frozenset[str]` (Tranco top-100k ∪ brand legit domains ∪ infra list).

- [ ] **Step 1: `data/brands.yaml`** — 40 entries covering exactly DATA.md §4's list: SBI, HDFC, ICICI, Axis, Kotak, PNB, Bank of Baroda, Canara, Union Bank, IndusInd, Yes Bank, IDFC First · Paytm, PhonePe, Google Pay, NPCI/UPI, BHIM, MobiKwik · Jio, Airtel, Vi · Income Tax, EPFO, UIDAI/Aadhaar, DigiLocker, IRCTC, India Post, GST, Parivahan, NSDL/PAN · Amazon.in, Flipkart, Myntra, Meesho · Zerodha, Groww, Upstox, Angel One · LIC, Swiggy. Format per DATA.md §4. Every `legit_domains` value must be the brand's real public domain; when unsure of a domain, **omit it and list it in MANIFEST.md "unverified"** rather than guessing. Tokens ≤ 3 chars (`sbi`, `upi`, `jio`, `vi`, `lic`, `gst`, `pnb`) are allowed but marked by length; triage treats them as segment-only (Task 6).
- [ ] **Step 2: `scripts/fetch_allowlist.py`** — download `https://tranco-list.eu/top-1m.csv.zip`, take first 100,000 `domain` values, write `data/allowlist.txt`; record Tranco list ID + date into `data/MANIFEST.md`. Fails loudly (exit 1, message) if unreachable — no substitute.
- [ ] **Step 3: Failing test** `test_brands.py`:

```python
from services.ingest.brands import load_brands, load_allowlist
from services.config import SETTINGS

def test_brands_shape():
    idx = load_brands(SETTINGS.brands_file)
    assert len(idx.brands) >= 40
    assert {"sbi.co.in", "hdfcbank.com", "icicibank.com", "paytm.com", "incometax.gov.in"} <= idx.legit_etld1s
    assert all(b.tokens and b.sector for b in idx.brands)

def test_allowlist_contains_every_legit_domain():
    idx = load_brands(SETTINGS.brands_file)
    allow = load_allowlist(SETTINGS.allowlist_file, idx)
    assert idx.legit_etld1s <= allow and "google.com" in allow and len(allow) >= 100_000
```
- [ ] **Step 4: Implement `brands.py`** (pyyaml load; `legit_etld1s` via `tldextract.TLDExtract(suffix_list_urls=())` offline snapshot `.top_domain_under_public_suffix` — use the `registered_domain` attr for tldextract 5.1.3). Infra allowlist constant: `["cloudflare.com","amazonaws.com","azureedge.net","googleusercontent.com","akamaiedge.net","fastly.net","cloudfront.net","github.io","vercel.app","netlify.app"]` — note: `github.io`/`vercel.app`/`netlify.app` are **public suffixes** in the PSL so subdomains there have their own eTLD+1 and are NOT allowlisted by this entry (correct — attackers use them).
- [ ] **Step 5: Run fetch + tests — PASS.** Commit `feat(data): 40 Indian brands, Tranco top-100k allowlist, manifest`.

---

### Task 6: Triage (rules provenance) — RELEASE GATE `test_triage.py`

**Files:**
- Create: `services/ingest/homoglyph.py`, `services/ml/__init__.py`, `services/ml/features.py`, `services/ingest/triage.py`, `services/tests/test_triage.py`, `scripts/bench_triage.py`

**Interfaces:**
- Consumes: `load_brands`, `load_allowlist` (Task 5).
- Produces:
  - `features.extract(name: str, issuer: str|None, san_count: int, idx: BrandIndex) -> Features` — dataclass with MODELS §2's 12 fields `brand_token_exact: bool, min_edit_distance: int, homoglyph_hit: bool, tld_risk: float, keyword_count: int, hyphen_count: int, max_label_len: int, digit_ratio: float, subdomain_depth: int, entropy: float, issuer_is_free_ca: bool, san_count: int` plus `etld1: str, brand: Brand|None, matched_token: str|None`. `.vector() -> list[float]` in that fixed order. **Shared by training (Task 23) and runtime.**
  - `triage(name, issuer=None, san_count=1) -> TriageResult(score: float, is_candidate: bool, etld1: str, brand: str|None, reasons: list[Reason], provenance: "rules"|"model", threshold: float)`; `Reason(feature: str, value, contribution: float)`.
  - Rules: TRD §2 weights. Allowlist first → score 0, `reasons=[Reason("allowlisted", etld1, 0.0)]`.

Decisions recorded in code comments:
- Lookalike: Damerau-Levenshtein (`rapidfuzz.distance.DamerauLevenshtein`) per hyphen/dot/digit-split segment of the eTLD+1 label vs brand tokens of length ≥ 5 only; threshold ≤ 1 for len 5–7, ≤ 2 for len ≥ 8. (Spec says ≤ 2 flat; on 3–4-letter tokens that matches most short words — `google.com`-class false positives the release gate forbids.) Length-bucketed: only compare tokens with `|len(seg)-len(tok)| ≤ 2`.
- Short tokens (≤ 3 chars) count as `brand_token_exact` only when equal to a whole segment (`sbi-verify` yes, `service` no for `vi`).
- "Free CA + new domain" (TRD) does not fire in triage: age needs WHOIS, which MODELS §2 forbids in the hot path. `issuer_is_free_ca` is still a feature for the model.
- `tld_risk`: rules mode uses TRD's set → 0.15; model mode uses empirical per-TLD rate.

- [ ] **Step 1: Failing tests** `test_triage.py`:

```python
import time, pytest
from services.ingest.triage import triage
from services.config import SETTINGS

LEGIT = ["google.com", "sbi.co.in", "hdfcbank.com", "paytm.com", "amazon.in", "icicibank.com",
         "onlinesbi.sbi", "incometax.gov.in", "flipkart.com", "airtel.in", "service.gov.in", "wikipedia.org"]
PHISH = ["sbi-verify-kyc.top", "icici-netbanking-login.xyz", "hdfc-secure-update.click",
         "paytm-kyc-verify.buzz", "incometax-refund-verify.top", "login.sbi.co.in.attacker.top",
         "icicibannk-login.top", "yonosbi-update.rest"]

@pytest.mark.parametrize("d", LEGIT)
def test_known_good_never_candidates(d):
    r = triage(d); assert not r.is_candidate, (d, r.score, r.reasons)

@pytest.mark.parametrize("d", PHISH)
def test_known_phishing_always_candidates(d):
    r = triage(d); assert r.is_candidate, (d, r.score, r.reasons)

def test_etld1_not_naive_split():
    assert triage("login.sbi.co.in.attacker.top").etld1 == "attacker.top"

def test_homoglyph_cyrillic_and_punycode():
    assert triage("ѕbі-kyc-verify.top").is_candidate          # Cyrillic s, i
    assert triage("xn--invalid--.com").score >= 0             # no crash on bad punycode

def test_reasons_and_provenance():
    r = triage("sbi-verify-kyc.top")
    assert r.provenance == "rules" and r.threshold == SETTINGS.triage_threshold
    assert sum(x.contribution for x in r.reasons) == pytest.approx(r.score)

def test_under_5ms_per_name():
    names = [f"shop{i}-example.com" for i in range(5000)] + PHISH * 100
    t = time.perf_counter()
    for n in names: triage(n)
    assert (time.perf_counter() - t) / len(names) < 0.005
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement `homoglyph.py`** — `CONFUSABLES: dict[str, str]` covering Cyrillic/Greek lookalikes of a–z (а→a, е→e, о→o, р→p, с→c, у→y, х→x, ѕ→s, і→i, ј→j, ӏ→l, ԁ→d, ɡ→g, ո→n, ν→v, ο→o, α→a) and digit/ascii swaps applied as a second pass (`0→o, 1→l, 3→e, 5→s, rn→m, vv→w`); `skeleton(s) -> str` = NFKC → per-char map → ascii swaps.
- [ ] **Step 4: Implement `features.py` and `triage.py`.** `triage.py` loads brands, allowlist and (if `SETTINGS.triage_model_path` exists **and** `services/ml/artifacts/triage_coefficients.json` has `"passed_checks": true`) the LR model — else rules. Module-level singletons, built once. Score = min(1, Σ contributions); contributions: brand_token_exact .35; lookalike (dist within threshold, not exact) .30; homoglyph_hit (skeleton reveals a token not visible in the raw string) .30; risky TLD .15; keyword_count ≥ 1 → .15; hyphen_count > 3 or max_label_len > 25 → .10.
- [ ] **Step 5: Run — PASS.** If a PHISH fixture fails, inspect its reasons before touching weights; weights are TRD-fixed — fix feature extraction, not weights. If a weight change is truly required, stop and ask.
- [ ] **Step 6: `scripts/bench_triage.py`** — runs triage over every name in `data/capture.jsonl` (first 100k), prints p50/p95/p99 µs, candidates count, and writes `reports/triage_bench.json`. Run it.
- [ ] **Step 7: Commit** `feat(triage): rules triage with allowlist-first, homoglyph skeleton, <5ms gate`.

---

### Task 7: `packages/interdict` — types, greedy, CP-SAT, validate — RELEASE GATE `test_interdict.py`

**Files:**
- Create: `packages/interdict/pyproject.toml`, `README.md`, `LICENSE` (MIT), `src/interdict/__init__.py`, `types.py`, `validate.py`, `solvers/__init__.py`, `solvers/greedy.py`, `solvers/cpsat.py`, `tests/test_interdict.py`

**Interfaces:**
- Produces:
```python
@dataclass(frozen=True)
class Problem:
    nodes: tuple[str, ...]                  # takedownable node ids
    deps: Mapping[str, frozenset[str]]      # domain id -> node ids it depends on
    weights: Mapping[str, float]            # domain id -> weight (default 1.0)
    k: int
    @property
    def domains(self) -> tuple[str, ...]: ...
    def coverage(self, targets: Iterable[str]) -> set[str]   # domains with any dep in targets
    def objective(self, targets) -> float

@dataclass
class Plan:
    backend: str; targets: list[str]; killed: set[str]; objective: float
    domains_total: int; solve_ms: int; valid: bool
    fell_back: bool = False; fallback_from: str | None = None
    n_variables: int = 0; qubit_count: int | None = None; notes: list[str] = field(default_factory=list)
    @property
    def coverage_pct(self) -> float

class PlanInvalid(Exception): ...
def validate(p: Problem, targets: list[str]) -> set[str]   # raises PlanInvalid; returns killed
def solve_greedy(p: Problem) -> list[str]
def solve_cpsat(p: Problem, timeout_s: float = 10.0) -> list[str]
```
`pyproject.toml`: name `interdict`, deps `ortools==9.11.4210`, `numpy`; optional extra `quantum = ["qiskit==1.2.4", "qiskit-aer==0.15.1"]`. **No import of `services`.**

- [ ] **Step 1: Failing tests** `tests/test_interdict.py`:

```python
import random, itertools, pytest
from interdict.types import Problem
from interdict.validate import validate, PlanInvalid
from interdict.solvers.greedy import solve_greedy
from interdict.solvers.cpsat import solve_cpsat

def rand_problem(rng, n_nodes=None, n_dom=None, k=None):
    n_nodes = n_nodes or rng.randint(1, 15); n_dom = n_dom or rng.randint(1, 60)
    nodes = tuple(f"n{i}" for i in range(n_nodes))
    deps = {f"d{j}": frozenset(rng.sample(nodes, rng.randint(0, min(3, n_nodes)))) for j in range(n_dom)}
    w = {d: rng.choice([1.0, 1.0, 2.5]) for d in deps}
    return Problem(nodes, deps, w, k if k is not None else rng.randint(0, 6))

def brute(p):
    best = 0.0
    for r in range(min(p.k, len(p.nodes)) + 1):
        for c in itertools.combinations(p.nodes, r):
            best = max(best, p.objective(c))
    return best

@pytest.mark.parametrize("seed", range(500))
def test_500_random_instances_budget_and_coverage(seed):
    rng = random.Random(seed); p = rand_problem(rng)
    for solver in (solve_greedy, solve_cpsat):
        t = solver(p)
        killed = validate(p, t)
        assert len(t) <= p.k
        assert killed == {d for d, s in p.deps.items() if s & set(t)}

@pytest.mark.parametrize("seed", range(60))
def test_cpsat_is_optimal_on_small(seed):
    p = rand_problem(random.Random(1000 + seed), n_nodes=8, n_dom=25)
    assert p.objective(solve_cpsat(p)) == pytest.approx(brute(p))

def test_greedy_meets_1_minus_1_over_e():
    for s in range(100):
        p = rand_problem(random.Random(s), n_nodes=9, n_dom=30)
        opt = brute(p)
        assert p.objective(solve_greedy(p)) >= (1 - 1 / 2.718281828) * opt - 1e-9

def test_validate_rejects_over_budget_and_unknown():
    p = Problem(("a", "b"), {"d": frozenset({"a"})}, {"d": 1.0}, 1)
    with pytest.raises(PlanInvalid): validate(p, ["a", "b"])
    with pytest.raises(PlanInvalid): validate(p, ["zzz"])

def test_k_zero_and_k_above_nodes():
    p = Problem(("a",), {"d": frozenset({"a"})}, {"d": 1.0}, 0)
    assert solve_cpsat(p) == [] and solve_greedy(p) == []
    p2 = Problem(("a",), {"d": frozenset({"a"})}, {"d": 1.0}, 9)
    assert solve_cpsat(p2) == ["a"]

def test_cpsat_400_domains_under_1s():
    import time
    rng = random.Random(7); nodes = tuple(f"n{i}" for i in range(30))
    deps = {f"d{j}": frozenset(rng.sample(nodes, 3)) for j in range(400)}
    p = Problem(nodes, deps, {d: 1.0 for d in deps}, 5)
    t = time.perf_counter(); solve_cpsat(p); assert time.perf_counter() - t < 1.0
```

- [ ] **Step 2: Install & run — FAIL.** `.venv/Scripts/pip install -e packages/interdict && .venv/Scripts/python -m pytest packages/interdict -q`
- [ ] **Step 3: Implement.** `solve_cpsat` per NPHARD §4 (scale weights ×1000 → int; `num_search_workers=8`; return `[v for v in nodes if solver.Value(x[v])]`; if status not OPTIMAL/FEASIBLE raise `RuntimeError`). Greedy: repeatedly pick the node with max uncovered weight (ties → lexicographic id for determinism), stop at k or when gain is 0. `validate` per NPHARD §8 (raise `PlanInvalid` with message, not `assert`).
- [ ] **Step 4: Run — PASS.** Commit `feat(interdict): types, greedy, CP-SAT, validation gate`.

---

### Task 8: Interdict — reduce, annealing, router, benchmark — RELEASE GATE `test_fallback.py`

**Files:**
- Create: `src/interdict/reduce.py`, `penalties.py`, `qubo.py`, `solvers/annealing.py`, `router.py`, `benchmark.py`, `tests/test_reduce.py`, `tests/test_fallback.py`, `tests/test_qubo.py`

**Interfaces:**
- Produces:
```python
@dataclass
class Reduced:
    problem: Problem          # domains = group ids, weights = summed, nodes = kept top-C
    groups: dict[str, list[str]]   # group id -> original domain ids
    notes: list[str]          # e.g. "lowered C from 12 to 10 to fit 24 variables"
def collapse(p: Problem) -> tuple[Problem, dict[str, list[str]]]
def reduce(p: Problem, C: int = 12, max_vars: int = 24) -> Reduced
def penalties(weights: Mapping[str, float]) -> tuple[float, float]       # (lam1, lam2) = (1.2*max, 1.2*sum)
def build_qubo(p: Problem) -> tuple[dict[tuple[int,int], float], float, list[str]]
    # Q upper-triangular {(i,j): coef} i<=j, constant offset, var names ["x:<node>", ..., "y:<group>", ...]
def qubo_energy(Q, const, bits: Sequence[int]) -> float
def decode(bits, var_names) -> list[str]                                  # selected nodes
def solve_annealing(p: Problem, seed: int = 0, sweeps: int = 4000) -> list[str]
def solve(p: Problem, backend: str = "cpsat", timeout_s: float = 10.0, max_vars: int = 24) -> Plan
CHAINS = {"cpsat": ["cpsat","greedy"], "qaoa": ["qaoa","cpsat","greedy"],
          "annealing": ["annealing","cpsat","greedy"], "greedy": ["greedy"]}
def benchmark(p: Problem, backends=("cpsat","qaoa","annealing","greedy"), timeout_s=15.0) -> list[BenchmarkRow]
@dataclass
class BenchmarkRow: backend, objective, domains_killed, domains_total, coverage_pct, solve_ms, valid, targets, n_variables, qubit_count, is_best, error: str|None
```
QUBO-family solvers (annealing, qaoa) run on `reduce(p)`, then the selected nodes are evaluated **on the full problem** for `objective/killed` (honest). `n_variables` = reduced variable count; `qubit_count` set only for qaoa. `is_best` = max objective, ties → lowest solve_ms; failed rows `valid=False`, objective 0, `error` set — **every row returned**.

- [ ] **Step 1: Failing tests**

`test_reduce.py`:
```python
import random
from interdict.types import Problem
from interdict.reduce import collapse, reduce

def mk(seed):
    rng = random.Random(seed); nodes = tuple(f"n{i}" for i in range(21))
    deps = {f"d{j}": frozenset(rng.sample(nodes[:6], 2)) for j in range(400)}
    return Problem(nodes, deps, {d: 1.0 for d in deps}, 5)

def test_collapse_preserves_total_weight():
    p = mk(1); cp, groups = collapse(p)
    assert sum(cp.weights.values()) == sum(p.weights.values())
    assert sorted(d for g in groups.values() for d in g) == sorted(p.domains)

def test_reduce_fits_cap_and_logs():
    r = reduce(mk(2), C=12, max_vars=24)
    assert len(r.problem.nodes) + len(r.problem.domains) <= 24

def test_dominated_nodes_pruned():
    p = Problem(("a", "b"), {"d1": frozenset({"a", "b"}), "d2": frozenset({"b"})}, {"d1": 1, "d2": 1}, 1)
    assert reduce(p).problem.nodes == ("b",)
```
`test_qubo.py` (named `test_ising.py` portion lives in Task 9):
```python
import itertools
from interdict.types import Problem
from interdict.qubo import build_qubo, qubo_energy, decode

def test_qubo_minimum_is_the_optimal_plan():
    p = Problem(("a", "b", "c"),
                {"g1": frozenset({"a"}), "g2": frozenset({"b"}), "g3": frozenset({"b", "c"})},
                {"g1": 5.0, "g2": 1.0, "g3": 1.0}, 1)
    Q, c, names = build_qubo(p)
    assert all(i <= j for i, j in Q)                       # upper-triangular
    best = min(itertools.product([0, 1], repeat=len(names)), key=lambda b: qubo_energy(Q, c, b))
    assert decode(best, names) == ["a"]
```
`test_fallback.py`:
```python
import builtins, sys, pytest
from interdict.types import Problem
from interdict.router import solve
from interdict.benchmark import benchmark

P = Problem(("a", "b"), {"d1": frozenset({"a"}), "d2": frozenset({"b"}), "d3": frozenset({"b"})},
            {"d1": 1.0, "d2": 1.0, "d3": 1.0}, 1)

@pytest.fixture
def no_qiskit(monkeypatch):
    real = builtins.__import__
    def fake(name, *a, **kw):
        if name.startswith("qiskit"): raise ImportError("qiskit patched out")
        return real(name, *a, **kw)
    for m in [m for m in sys.modules if m.startswith("qiskit")]: monkeypatch.delitem(sys.modules, m)
    monkeypatch.setattr(builtins, "__import__", fake)

def test_qaoa_without_qiskit_falls_back_to_cpsat(no_qiskit):
    plan = solve(P, backend="qaoa")
    assert plan.valid and plan.backend == "cpsat" and plan.fell_back and plan.fallback_from == "qaoa"
    assert plan.targets == ["b"] and len(plan.killed) == 2

def test_package_imports_without_qiskit(no_qiskit):
    import importlib, interdict.router; importlib.reload(interdict.router)

def test_benchmark_reports_failed_backend_row(no_qiskit):
    rows = benchmark(P)
    assert [r.backend for r in rows] == ["cpsat", "qaoa", "annealing", "greedy"]
    q = next(r for r in rows if r.backend == "qaoa")
    assert not q.valid and "qiskit" in q.error
    assert sum(r.is_best for r in rows) == 1

def test_greedy_failure_raises(monkeypatch):
    import interdict.router as r
    monkeypatch.setitem(r.SOLVERS, "greedy", lambda p, **kw: 1 / 0)
    with pytest.raises(ZeroDivisionError): solve(P, backend="greedy")
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.** `reduce`: collapse (NPHARD §5a) → drop nodes covering nothing → prune dominated (coverage set ⊂ another node's, NPHARD §5b) → top-C by weighted coverage → while `nodes+groups > max_vars`: decrement C (and, if C reaches k, merge the lowest-weight groups into an "other" dropped bucket) with a note each time. `build_qubo` per NPHARD §6 using `penalties()`; QUBO upper-triangular accumulation helper `_add(Q,i,j,v)` storing at `(min,max)`; expand `λ2(Σx−k)²` = `λ2(Σx_i + 2Σ_{i<j}x_ix_j − 2kΣx_i + k²)` using `x²=x`. The over-coverage imperfection gets the comment from NPHARD §6. `solve_annealing`: simulated annealing on the QUBO bitstring (numpy RNG with seed, geometric temperature schedule, single-bit flips, returns best-seen decoded nodes, then trims to ≤ k by greedy contribution if the penalty was violated). Router per NPHARD §8 with `SOLVERS` dict, every exception caught except on the last solver of a chain, `validate` on each result.
- [ ] **Step 4: Run — PASS.** Commit `feat(interdict): reduction, QUBO, annealing, router with fallback, honest benchmark`.

---

### Task 9: Interdict — QAOA backend + Ising sign check

**Files:**
- Create: `src/interdict/solvers/qaoa.py`, `tests/test_ising.py`

**Interfaces:**
- Produces: `solve_qaoa(p: Problem, timeout_s: float = 15.0, p_depth: int = 3, shots: int = 1024, seed: int = 0) -> tuple[list[str], int]` (targets, qubit_count); `qubo_to_ising(Q, const, n) -> tuple[SparsePauliOp, float]`. All qiskit imports **inside** functions. Raises `ImportError` if qiskit missing, `TimeoutError` past `timeout_s` (checked in the COBYLA cost callback), `ValueError` if > 24 variables.

- [ ] **Step 1: Install quantum extra** `.venv/Scripts/pip install -r services/api/requirements-quantum.txt && .venv/Scripts/python -c "import qiskit, qiskit_aer; print(qiskit.__version__)"` → `1.2.4`. Commit lockfile `pip freeze > services/api/requirements.lock`. If install fails: report the error to the owner, keep going (fallback covers it) — QAOA is not cut but ships "benchmarked with fallback".
- [ ] **Step 2: Failing test** `test_ising.py` (`pytestmark = pytest.mark.quantum`, skip if qiskit missing):

```python
import itertools, numpy as np, pytest
qiskit = pytest.importorskip("qiskit")
from interdict.types import Problem
from interdict.qubo import build_qubo, qubo_energy
from interdict.solvers.qaoa import qubo_to_ising, solve_qaoa

def test_ising_energy_order_matches_qubo_bruteforce():
    p = Problem(("a", "b"), {"g1": frozenset({"a"}), "g2": frozenset({"b"})}, {"g1": 2.0, "g2": 1.0}, 1)
    Q, c, names = build_qubo(p); n = len(names); assert n == 4
    H, offset = qubo_to_ising(Q, c, n)
    mat = H.to_matrix().real.diagonal()
    for bits in itertools.product([0, 1], repeat=n):
        idx = sum(b << i for i, b in enumerate(bits))        # qiskit little-endian
        assert mat[idx] + offset == pytest.approx(qubo_energy(Q, c, bits))

def test_qaoa_small_instance_valid():
    p = Problem(("a", "b", "c"), {f"d{i}": frozenset({"abc"[i % 3]}) for i in range(9)},
                {f"d{i}": 1.0 + (i % 3 == 0) for i in range(9)}, 1)
    targets, q = solve_qaoa(p, timeout_s=15)
    assert len(targets) <= 1 and q <= 24
```
- [ ] **Step 3: Implement** per NPHARD §7: substitution `x=(1−z)/2`; `QAOAAnsatz(H, reps=3)`; `AerSimulator(method="statevector")` with `Estimator`/`Sampler` primitives from `qiskit_aer.primitives`; COBYLA from `scipy.optimize.minimize` (scipy arrives with qiskit); warm start = parameters initialised via greedy (bias initial mixer angles toward the greedy bitstring per standard warm-start trick: initial γ small, β = π/4; record "warm-start: greedy" in notes); sample 1024 shots, evaluate **every** sampled bitstring with `qubo_energy`, keep the best; decode; trim to ≤ k. Register in `router.SOLVERS["qaoa"]` with a lazy wrapper that calls `reduce()` first and sets `qubit_count`.
- [ ] **Step 4: Run all interdict tests — PASS**, including `test_fallback.py` (qiskit patched out). Commit `feat(interdict): QAOA backend on reduced QUBO with verified Ising mapping`.

---

### Task 10: `packages/evidence` — Merkle, Ed25519, verify, abuse report — RELEASE GATE `test_evidence.py`

**Files:**
- Create: `packages/evidence/pyproject.toml`, `src/evidence/__init__.py`, `merkle.py`, `bundle.py`, `report.py`, `tests/test_evidence.py`, `scripts/genkey.py`

**Interfaces:**
- Produces:
```python
def leaf_hash(name: str, content_sha256: bytes) -> bytes       # sha256(b"\x00" + name.encode() + b"\x00" + content_sha256)
def merkle_root(leaves: list[bytes]) -> bytes                  # sha256(b"\x01"+l+r); odd node promoted; empty -> sha256(b"")
@dataclass
class ArtifactMeta: name: str; sha256: str; size_bytes: int
@dataclass
class Bundle: bundle_id: str; root: str; signature: str; collector_pk: str; artifacts: list[ArtifactMeta]; partial: bool; dir: str
def build_bundle(out_dir: Path, bundle_id: str, artifacts: dict[str, bytes], signing_key_hex: str, partial: bool = False) -> Bundle
@dataclass
class Failure: artifact: str; expected: str | None; found: str | None; reason: Literal["hash_mismatch","missing","unexpected"]
@dataclass
class VerifyResult: valid: bool; root_matches: bool; signature_valid: bool; expected_root: str; computed_root: str; failures: list[Failure]
def verify_bundle(bundle_dir: Path, expected_root: str, signature: str, public_key: str, expected: dict[str, str]) -> VerifyResult
def render_abuse_report(*, domain: str, recipient: str | None, bundle: Bundle, signals: list[dict], enrichment: dict, campaign_label: str | None, generated_at: datetime) -> str   # markdown
```
Leaves sorted by artifact name (BLOCKCHAIN §5). Signature = Ed25519 over the 32-byte root. `collector_pk` formatted `"ed25519:<hex>"`. `meta.json` is written by the caller.

- [ ] **Step 1: Failing tests** `tests/test_evidence.py`:

```python
import nacl.signing
from pathlib import Path
from evidence.bundle import build_bundle, verify_bundle
from evidence.merkle import merkle_root, leaf_hash

KEY = nacl.signing.SigningKey.generate()
SK = KEY.encode().hex(); PK = "ed25519:" + KEY.verify_key.encode().hex()
ARTS = {"dom.html": b"<html>kit</html>", "headers.json": b"{}", "screenshot.png": b"\x89PNG..."}

def mk(tmp_path):
    b = build_bundle(tmp_path, "b1", ARTS, SK)
    return b, {a.name: a.sha256 for a in b.artifacts}

def test_roundtrip_valid(tmp_path):
    b, exp = mk(tmp_path)
    r = verify_bundle(Path(b.dir), b.root, b.signature, b.collector_pk, exp)
    assert r.valid and r.root_matches and r.signature_valid and r.failures == []

def test_one_byte_tamper_names_the_artifact(tmp_path):
    b, exp = mk(tmp_path)
    p = Path(b.dir) / "dom.html"; data = bytearray(p.read_bytes()); data[3] ^= 1; p.write_bytes(bytes(data))
    r = verify_bundle(Path(b.dir), b.root, b.signature, b.collector_pk, exp)
    assert not r.valid and not r.root_matches
    assert [(f.artifact, f.reason) for f in r.failures] == [("dom.html", "hash_mismatch")]
    assert r.failures[0].expected == exp["dom.html"] != r.failures[0].found

def test_wrong_key_fails_signature(tmp_path):
    b, exp = mk(tmp_path)
    other = "ed25519:" + nacl.signing.SigningKey.generate().verify_key.encode().hex()
    r = verify_bundle(Path(b.dir), b.root, b.signature, other, exp)
    assert not r.signature_valid and not r.valid

def test_deleted_artifact_reported_missing(tmp_path):
    b, exp = mk(tmp_path); (Path(b.dir) / "headers.json").unlink()
    r = verify_bundle(Path(b.dir), b.root, b.signature, b.collector_pk, exp)
    assert ("headers.json", "missing") in [(f.artifact, f.reason) for f in r.failures]

def test_root_independent_of_insertion_order(tmp_path):
    a = build_bundle(tmp_path / "a", "x", ARTS, SK)
    b = build_bundle(tmp_path / "b", "x", dict(reversed(list(ARTS.items()))), SK)
    assert a.root == b.root

def test_report_never_says_sent(tmp_path):
    from evidence.report import render_abuse_report
    from datetime import datetime, timezone
    b, _ = mk(tmp_path)
    md = render_abuse_report(domain="icici-verify-kyc.top", recipient="abuse@registrar.example", bundle=b,
                             signals=[{"name": "credential_post_foreign_origin", "strength": "strong",
                                       "detail": "form POST -> 203.0.113.9"}],
                             enrichment={"registrar": "Registrar A (seed)"}, campaign_label="CAMP-0001",
                             generated_at=datetime(2026, 10, 6, tzinfo=timezone.utc))
    assert "icici-verify-kyc.top" in md and b.root in md
    assert all(a.sha256 in md for a in b.artifacts)
    assert "Generated by QCertChain — not sent." in md
    assert "mailto:" not in md and "submitted" not in md.lower() and "sent to" not in md.lower()
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement.** **Step 4: Run — PASS.**
- [ ] **Step 5: `scripts/genkey.py`** — prints a new Ed25519 private key hex; run it and put the value in `.env` `COLLECTOR_PRIVATE_KEY` (never committed).
- [ ] **Step 6: Commit** `feat(evidence): Merkle bundles, Ed25519 signing, verification that names the failing artifact, unsent abuse report`.

---

### Task 11: Fingerprints — DOM structure hash stability

**Files:**
- Create: `services/enrich/__init__.py`, `services/enrich/fingerprint.py`, `services/tests/test_fingerprint.py`, `services/tests/fixtures/kit_a.html`

**Interfaces:**
- Produces: `dom_structure_hash(html: str) -> str` (hex sha256 of tag-name nesting only; `<script>`/`<style>` contents dropped; tag names lowercased; self-closing normalised; whitespace irrelevant); `favicon_hash(data: bytes) -> str` (`str(mmh3.hash(base64.encodebytes(data)))`, Shodan convention); `js_bundle_hashes(scripts: list[bytes]) -> list[str]` (sorted sha256 hex); `extract_forms(html, base_url) -> list[Form(action_url: str, method: str, has_password: bool)]`; `page_title(html) -> str|None`. Stdlib `html.parser` only.

- [ ] **Step 1: Fixture** `kit_a.html` — a realistic cloned bank login page (~80 lines: header, logo img, form with username + password posting to `https://185.243.115.22/gate.php`, footer, two scripts, inline style).
- [ ] **Step 2: Failing tests**

```python
import re
from pathlib import Path
from services.enrich.fingerprint import dom_structure_hash, extract_forms, favicon_hash

KIT = (Path(__file__).parent / "fixtures/kit_a.html").read_text()

def mutate(html: str) -> str:
    html = re.sub(r">([^<]+)<", lambda m: ">" + "Z" * len(m.group(1)) + "<", html)      # every string
    html = re.sub(r"#[0-9a-fA-F]{3,6}", "#123456", html)                                # every colour
    html = re.sub(r'src="[^"]*"', 'src="https://other.example/x.png"', html)            # every image URL
    html = re.sub(r'(class|id|style)="[^"]*"', r'\1="changed"', html)                   # attributes
    return html.replace("\n", "\n    ")                                                 # whitespace

def test_hash_stable_under_trivial_variation():
    assert dom_structure_hash(KIT) == dom_structure_hash(mutate(KIT))

def test_hash_changes_when_structure_changes():
    assert dom_structure_hash(KIT) != dom_structure_hash(KIT.replace("<form", "<div><form", 1).replace("</form>", "</form></div>", 1))

def test_forms_detect_password_and_foreign_action():
    f = extract_forms(KIT, "https://icici-verify-kyc.top/login")
    assert any(x.has_password and x.action_url.startswith("https://185.243.115.22") for x in f)

def test_relative_action_resolved():
    f = extract_forms('<form action="/p.php"><input type="password"></form>', "https://a.top/x/")
    assert f[0].action_url == "https://a.top/p.php"

def test_malformed_html_does_not_crash():
    assert dom_structure_hash("<div><p>unclosed <b>tags") and dom_structure_hash("")

def test_favicon_hash_shodan_convention():
    assert favicon_hash(b"\x00\x01") == favicon_hash(b"\x00\x01") and favicon_hash(b"a") != favicon_hash(b"b")
```
- [ ] **Step 3–4: Implement, run — PASS.** Commit `feat(enrich): kit fingerprint with stability test, forms, favicon hash`.

---

### Task 12: Enrichers + confirmation gate

**Files:**
- Create: `services/enrich/enrichers.py`, `services/enrich/fetch.py`, `services/enrich/confirm.py`, `services/tests/test_confirm.py`, `services/tests/test_enrichers.py`

**Interfaces:**
- Produces:
  - `@dataclass Enrichment: ip_addresses: list[str], asn: int|None, asn_name: str|None, country: str|None, nameservers: list[str], mx_records: list[str], cert_issuer: str|None, registrar: str|None, registered_at: datetime|None, dom_hash: str|None, favicon_hash: str|None, js_hashes: list[str], page_title: str|None, partial: bool, errors: dict[str,str]`
  - `async enrich(domain: str, page: FetchedPage | None) -> Enrichment` — each enricher independent; failure → field None, `errors[name]=msg`, `partial=True`.
  - `dns_records(name) -> dict` (A, AAAA, NS, MX, TXT via `dns.asyncresolver` with nameservers 1.1.1.1/8.8.8.8, 5 s timeout); `rdap(name) -> dict` (`httpx GET https://rdap.org/domain/{etld1}`, registrar from `entities[roles∋registrar].vcardArray`, `events[eventAction=registration]`); `asn_for_ip(ip)` — pyasn if `data/ipasn.dat` exists, else Team Cymru `dig {rev}.origin.asn.cymru.com TXT` + `AS{n}.asn.cymru.com TXT` for name (both spec-listed; record which was used in `errors`-free `meta`); `tls_chain(name) -> dict` (stdlib `ssl` → issuer O, notBefore, SANs, PEM via `ssl.get_server_certificate`).
  - `@dataclass FetchedPage: url: str, final_url: str, status: int, html: str, headers: dict, redirect_chain: list[str], screenshot: bytes|None, favicon: bytes|None, scripts: list[bytes], via: "playwright"|"httpx"`
  - `async fetch(domain, *, timeout_s, user_agent) -> FetchedPage | Unreachable(reason: str)` — Playwright Chromium (no form interaction, `page.goto` only, max 5 redirects, 15 s); httpx fallback (follow_redirects with max 5). Per-host rate limit via Redis `SET ratelimit:{host} NX EX 2` — if not acquired, return `RateLimited`.
  - `@dataclass Signal: name: str, strength: "strong"|"moderate"|"weak", detail: str`
  - `@dataclass ConfirmResult: verdict: "confirmed"|"dismissed"|"unreachable"|"candidate", confidence: float, signals: list[Signal], strong_count: int`
  - `analyze_page(page: FetchedPage, domain: str, brand: Brand|None, known_kits: set[str], brand_favicons: dict[str,set[str]], registered_at: datetime|None, issuer: str|None) -> ConfirmResult` — **pure function**, used by live confirmation and by the seed.
  - `async confirm(domain_row, brand) -> tuple[ConfirmResult, FetchedPage|None, Enrichment]`.

Gate (TRD §3 / MODELS §5):
- strong: `credential_post_foreign_origin` (form with password whose action eTLD+1 ≠ page eTLD+1 and ∉ brand legit domains; detail names the target host/IP), `kit_dom_hash_match` (dom_hash ∈ known_kits; detail includes kit label), `favicon_brand_match` (favicon_hash ∈ brand_favicons[brand]).
- moderate: `title_impersonates_brand` (brand name/token in title, domain not legit), `obfuscated_js` (`eval(`, `atob(`, `unescape(`, base64 blob > 2 KB in inline script), `password_field_present`.
- weak: `recently_registered` (< 30 days), `issuer_is_free_ca`.
- `confirmed` iff strong_count ≥ 2. Parked page (title/HTML contains "domain is for sale", "parked", "sedo", "this domain may be for sale", or HTTP ≥ 400 with < 512 bytes) or fetch failure → `unreachable`. No password field and no moderate/strong signal → `dismissed`. Otherwise stays `candidate` with stored signals ("insufficient evidence — still a candidate").
- confidence = `min(0.99, 0.5 + 0.2*strong + 0.08*moderate + 0.02*weak)` — displayed only alongside reasons.

- [ ] **Step 1: Failing tests** `test_confirm.py` (pure — no network):

```python
from datetime import datetime, timezone, timedelta
from pathlib import Path
from services.enrich.fetch import FetchedPage
from services.enrich.confirm import analyze_page
from services.enrich.fingerprint import dom_structure_hash
from services.ingest.brands import load_brands
from services.config import SETTINGS

KIT = (Path(__file__).parent / "fixtures/kit_a.html").read_text()
ICICI = next(b for b in load_brands(SETTINGS.brands_file).brands if b.name.startswith("ICICI"))

def page(html, url="https://icici-verify-kyc.top/login"):
    return FetchedPage(url, url, 200, html, {}, [], None, None, [], "httpx")

def test_two_strong_signals_confirm():
    r = analyze_page(page(KIT), "icici-verify-kyc.top", ICICI, {dom_structure_hash(KIT)}, {}, None, "Let's Encrypt")
    assert r.verdict == "confirmed" and r.strong_count == 2
    assert any("185.243.115.22" in s.detail for s in r.signals)

def test_one_strong_signal_never_confirms():
    r = analyze_page(page(KIT), "icici-verify-kyc.top", ICICI, set(), {}, None, None)
    assert r.verdict == "candidate" and r.strong_count == 1

def test_moderate_only_never_confirms():
    html = "<html><head><title>ICICI Bank login</title></head><body><form action='/x'><input type=password></form><script>eval(atob('YQ=='))</script></body></html>"
    r = analyze_page(page(html), "icici-verify-kyc.top", ICICI, set(), {}, datetime.now(timezone.utc) - timedelta(days=2), "Let's Encrypt")
    assert r.verdict == "candidate" and r.strong_count == 0 and len(r.signals) >= 3

def test_legit_brand_domain_post_is_not_foreign():
    html = KIT.replace("https://185.243.115.22/gate.php", "https://infinity.icicibank.com/auth")
    r = analyze_page(page(html, "https://icici-verify-kyc.top/"), "icici-verify-kyc.top", ICICI, set(), {}, None, None)
    assert not any(s.name == "credential_post_foreign_origin" for s in r.signals)

def test_parked_page_unreachable():
    r = analyze_page(page("<html><title>This domain is for sale</title></html>"), "x.top", None, set(), {}, None, None)
    assert r.verdict == "unreachable"

def test_blog_dismissed():
    r = analyze_page(page("<html><title>My blog</title><p>hello</p></html>"), "blog.top", None, set(), {}, None, None)
    assert r.verdict == "dismissed"
```
`test_enrichers.py`: monkeypatch each enricher to raise → `enrich()` returns `partial=True`, the other fields populated, `errors` names the failing enricher. One `@pytest.mark.network` test resolving `example.com` A record.
- [ ] **Step 2–4:** run (FAIL), implement, run (PASS). Try `pip install pyasn==1.6.2`; on failure (no compiler) use Team Cymru and note it in `data/MANIFEST.md`. Run `playwright install chromium` and the RUNBOOK §4 checkpoint; if it fails, httpx path only and report.
- [ ] **Step 5: Commit** `feat(enrich): DNS/RDAP/ASN/TLS enrichers, Playwright+httpx fetch, two-strong-signal confirmation gate`.

---

### Task 13: Persistence layer + triage worker

**Files:**
- Create: `services/api/__init__.py`, `services/api/db.py`, `services/api/repo.py`, `services/api/workers/__init__.py`, `services/api/workers/triage_worker.py`, `services/tests/test_repo.py`, `services/tests/test_triage_worker.py`

**Interfaces:**
- Produces (`repo.py`, all take a SQLAlchemy `Connection` first; SQL via `sqlalchemy.text`):
  - `upsert_cert(c, rec: CertRecord) -> int` (on conflict fingerprint do nothing; returns id)
  - `upsert_candidate(c, *, name, etld1, cert_id, triage: TriageResult, source, ct_seen_at) -> tuple[int, bool]` (insert with `candidate_at=now()`; on conflict name → update `last_seen`, keep earliest timestamps; returns (id, created))
  - `set_confirmation(c, domain_id, result: ConfirmResult)`, `save_enrichment(c, domain_id, e: Enrichment)`
  - `upsert_node(c, kind, value) -> int`, `add_edge(c, domain_id, node_id, weight)`
  - `known_kits(c) -> set[str]`, `add_known_kit(c, dom_hash, label, source)`
  - `log(c, channel, message, severity=0, context=None)` (ops_log, insert-only)
  - `enqueue_anchor(c, kind, payload) -> int`
- Produces `db.engine()` (cached `create_engine(SETTINGS.database_url, pool_pre_ping=True, pool_size=5)`).
- Triage worker: `XREADGROUP` group `triage` on `certs:raw`, batch 500; per name → `triage()`; candidates → `upsert_cert`+`upsert_candidate`, `LPUSH enrich:queue {domain_id}` when created, XACK. Also publishes every triage result (candidate or not, sampled to ≤ 20/s) to Redis pub/sub channel `certs:live` as the SSE payload shape of API_CONTRACT §1. Non-candidates are **not** written to Postgres (TRD §6 retention).

- [ ] **Step 1: Failing tests** `test_repo.py` (`db` fixture): duplicate `upsert_cert` returns the same id; `upsert_candidate` twice → one row, `created` False the second time, `candidate_at` unchanged; `set_confirmation` with a confirmed result stores signals so the DB check passes; confirmed with zero signals raises IntegrityError. `test_triage_worker.py`: fakeredis stream with 3 certs (one candidate name, one allowlisted, one duplicate of the first) → exactly 1 domain row, 1 enrich:queue item, `certs:live` publish count == 3 names.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit `feat(api): repository layer and triage worker`.

---

## Phase 2 — Campaign

### Task 14: Graph build + clustering

**Files:**
- Create: `services/graph/__init__.py`, `services/graph/build.py`, `services/graph/cluster.py`, `services/tests/test_cluster.py`

**Interfaces:**
- Produces:
  - `EDGE_WEIGHTS = {"kit_hash":1.0,"favicon_hash":0.85,"ip":0.80,"nameserver":0.60,"asn":0.35,"cert_issuer":0.15,"registrar":0.15}`; `TAKEDOWN_ROUTE = {"ip":"hosting","nameserver":"dns","registrar":"registrar"}`
  - `edges_for(e: Enrichment) -> list[tuple[str, str, float]]` (kind, value, weight)
  - `@dataclass Cluster: domain_ids: set[int], node_ids: set[int], confidence: float`
  - `cluster(edges: list[tuple[int,int,float]], threshold=0.6, medium_floor=0.3) -> list[Cluster]` — NetworkX bipartite graph; components over edges ≥ threshold; merge two components sharing ≥ 2 distinct nodes with `medium_floor ≤ w < threshold`; singleton domains are not campaigns (min 2 domains); confidence = mean weight of ≥ threshold edges inside.
  - `recluster(c) -> list[uuid]` in `build.py`: loads all edges of confirmed domains, clusters, upserts `campaigns` (stable id: reuse a campaign whose domain set overlaps most; label `CAMP-NNNN`), sets `domains.campaign_id`, `campaign_joined_at`, `campaigns.kit_hash` (most common kit node), counts, brands, `ioc_root` (Merkle root over sorted IOC strings `kind:value` + domain names via `evidence.merkle`).

- [ ] **Step 1: Failing tests** `test_cluster.py`:

```python
import random, time
from services.graph.cluster import cluster

def test_shared_kit_clusters():
    e = [(1, 100, 1.0), (2, 100, 1.0), (3, 101, 0.8)]
    cs = cluster(e); assert len(cs) == 1 and cs[0].domain_ids == {1, 2}

def test_shared_asn_or_issuer_alone_never_merges():
    e = [(1, 200, 0.35), (2, 200, 0.35), (1, 300, 0.15), (2, 300, 0.15), (3, 300, 0.15)]
    assert cluster(e) == []

def test_merge_on_two_medium_edges():
    e = [(1, 10, 1.0), (2, 10, 1.0), (3, 11, 1.0), (4, 11, 1.0),
         (1, 20, 0.35), (3, 20, 0.35), (2, 21, 0.35), (4, 21, 0.35)]
    assert [c.domain_ids for c in cluster(e)] == [{1, 2, 3, 4}]

def test_500_nodes_under_2s():
    rng = random.Random(0)
    e = [(d, 1000 + rng.randint(0, 40), rng.choice([1.0, 0.8, 0.6, 0.35, 0.15])) for d in range(500) for _ in range(4)]
    t = time.perf_counter(); cluster(e); assert time.perf_counter() - t < 2.0
```
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit `feat(graph): weighted edges, threshold clustering, campaign upsert with IOC root`.

---

### Task 15: Enrich worker + seed campaign

**Files:**
- Create: `services/api/workers/enrich_worker.py`, `services/api/seed.py`, `services/api/kit_template.html`, `services/tests/test_seed.py`

**Interfaces:**
- Consumes: `confirm`, `analyze_page`, `enrich`, `edges_for`, `recluster`, `build_bundle`, repo functions.
- Produces:
  - Enrich worker loop: `BRPOP enrich:queue` → load domain → `confirm()` → `set_confirmation` → if confirmed: `save_enrichment`, nodes/edges (including `registrar` node from RDAP), `add_known_kit(dom_hash, label, 'confirmed')`, `recluster`, **build evidence bundle** (`make_bundle(c, domain_id, page, enrichment) -> bundle_id`: artifacts `screenshot.png` (if any), `dom.html`, `headers.json`, `cert.pem`, `whois.json` (RDAP json), `dns.json`, `asn.json`, `kit.json`, `meta.json`; `partial=True` if screenshot or any enricher missing), insert `evidence_bundles` + `evidence_artifacts` + `abuse_reports` row (rendered, `recipient` = registrar abuse email from RDAP if present else NULL), `enqueue_anchor('evidence', …)`; every step logged to ops_log with channel and timing. Concurrency: `asyncio.Semaphore(SETTINGS.enrich_workers)`.
  - `seed_campaign(c, *, label, domains=400, ips=12, asns=3, nameservers=4, registrars=3, brands=["ICICI Bank"], shared_dns_fraction=0.08, seed=42) -> uuid` — generates names `{brandtoken}-{verify|kyc|secure|update|netbanking}-{n}.{top|xyz|click|buzz|rest}`; IP assignment Zipf(s=1.3) over 12 IPs from the 185.243.115.0/24 documentation-style range (use RFC 5737 `198.51.100.0/24` & `203.0.113.0/24` — never real hosts); ASN by IP block; NS: 4 attacker NS `ns{1..4}.{label}-dns.top` Zipf-assigned, plus `shared_dns_fraction` of domains on `ns.shared-dns-provider.example` which is **not** inserted as a node (not attacker infra); registrars Zipf over 3 fictional-labelled registrars `Registrar A/B/C (seed)`; kit HTML from `kit_template.html` with per-domain brand string/colour variation; runs the real `analyze_page` (kit hash registered first via `add_known_kit(...,'seed')`); writes domains with `source='seed'`, enrichment, nodes, edges, evidence bundles (no screenshot → `partial=True`), then `recluster`. Returns campaign id.

- [ ] **Step 1: Failing test** `test_seed.py` (`db`):

```python
import sqlalchemy as sa, pytest
from services.api.seed import seed_campaign
pytestmark = pytest.mark.db

def test_seed_clusters_into_one_labelled_campaign(db, tmp_path):
    cid = seed_campaign(db, label="titli-kit", domains=400, evidence_dir=tmp_path)
    n = db.execute(sa.text("select count(*) from domains where campaign_id=:c and source='seed' and status='confirmed'"), {"c": cid}).scalar()
    assert n == 400
    assert db.execute(sa.text("select count(*) from campaigns")).scalar() == 1
    kinds = dict(db.execute(sa.text("select kind, count(*) from infra_nodes group by kind")).all())
    assert kinds["ip"] == 12 and kinds["nameserver"] == 4 and kinds["registrar"] == 3
    assert db.execute(sa.text("select count(*) from evidence_bundles where campaign_id=:c"), {"c": cid}).scalar() == 400

def test_every_seed_domain_has_two_strong_reasons(db, tmp_path):
    seed_campaign(db, label="t2", domains=20, evidence_dir=tmp_path)
    rows = db.execute(sa.text("select confirm_reasons from domains where source='seed'")).scalars().all()
    assert all(sum(s["strength"] == "strong" for s in r["signals"]) >= 2 for r in rows)
```
(`seed_campaign` signature gains `evidence_dir: Path | str = SETTINGS.evidence_dir`.)
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit `feat(pipeline): enrich worker with evidence bundles; realistic labelled seed campaign`.

---

### Task 16: API — all endpoints per API_CONTRACT

**Files:**
- Create: `services/api/main.py`, `models.py`, `routes/{stream,domains,campaigns,plans,evidence,ops,seed}.py`, `services/tests/test_api.py`
- Modify: `docs/API_CONTRACT.md` (NodeKind += `registrar`; `takedown_route` ∈ hosting|dns|registrar; `Source` += email, sample; email endpoints §9 new; `POST /ledger/corroborate/{campaign_id}`; `as_org` field on attest/corroborate)

**Interfaces:**
- Produces every endpoint in TRD §5 + API_CONTRACT with exactly those shapes (Pydantic v2 models in `models.py` mirroring the contract JSON field-for-field, enums as `Literal`). RFC 7807 `Problem` exception handler for all `HTTPException`/validation errors (`application/problem+json`). CORS for the console origin(s) from env `CONSOLE_ORIGINS`.
  - `GET /certs/live` SSE: subscribes Redis pub/sub `certs:live`, server-throttled to ≤ 20 events/s (token bucket; drop excess), `event: heartbeat` every 5 s from `stream:state`.
  - `POST /stream/mode` writes `stream:mode_request`; returns state.
  - `POST /campaigns/{id}/interdict`: builds `Problem` from DB — nodes = infra nodes of kinds ip/nameserver/registrar linked to campaign domains; deps per domain; weights from `domains.weight`; `k` validated: 422 if `k > len(nodes)` (detail includes the max) or `k < 1`; 409 if `nodes` empty ("No shared infrastructure — nothing to interdict."). Calls `interdict.router.solve`, persists plan + plan_targets (rank by marginal kills in selection order, `kills` = domains this target alone removes, route from `TAKEDOWN_ROUTE`) and ops_log line `plan {id} solved · {backend} · {ms}ms · {killed}/{total}` (+ `· {from} → {backend}` on fallback).
  - `POST /plans/{id}/benchmark`: `interdict.benchmark` → persist rows → return all rows.
  - Evidence routes per contract; `/evidence/{id}/artifacts/{name}` serves files (404 problem "Artifacts no longer on disk — hashes retained." when missing); `POST /evidence/{id}/verify` uses `verify_bundle` with expected hashes from `evidence_artifacts`.
  - `/evidence/{id}/report` returns `sent: false` always.
  - `POST /seed/campaign` → `seed_campaign`; `GET /metrics`, `GET /ops/log`.

- [ ] **Step 1: Failing tests** `test_api.py` (FastAPI `TestClient`, `db` engine override via dependency `get_conn`, fakeredis):

```python
import pytest
pytestmark = pytest.mark.db

def test_health(client): assert client.get("/health").json()["status"] == "ok"

def test_seed_then_interdict_plan_shape(client):
    cid = client.post("/seed/campaign", json={"label": "smoke", "domains": 400, "ips": 12, "asns": 3, "nameservers": 4}).json()["id"]
    plan = client.post(f"/campaigns/{cid}/interdict", json={"k": 5, "backend": "cpsat"}).json()
    assert plan["valid"] and len(plan["targets"]) <= 5 and plan["solve_ms"] < 1000
    assert {t["kind"] for t in plan["targets"]} <= {"ip", "nameserver", "registrar"}
    assert plan["qubit_count"] is None and plan["coverage_pct"] > 0

def test_interdict_k_too_large_422_problem_json(client, seeded):
    r = client.post(f"/campaigns/{seeded}/interdict", json={"k": 999, "backend": "cpsat"})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    assert "max" in r.json()["detail"]

def test_benchmark_returns_all_rows_one_best(client, plan_id):
    rows = client.post(f"/plans/{plan_id}/benchmark").json()["rows"]
    assert [r["backend"] for r in rows] == ["cpsat", "qaoa", "annealing", "greedy"]
    assert sum(r["is_best"] for r in rows) == 1

def test_tamper_demo(client, seeded_bundle_path, seeded_bundle_id):
    assert client.post(f"/evidence/{seeded_bundle_id}/verify").json()["valid"]
    p = seeded_bundle_path / "dom.html"; b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(bytes(b))
    r = client.post(f"/evidence/{seeded_bundle_id}/verify").json()
    assert not r["valid"] and r["failures"][0]["artifact"] == "dom.html"

def test_report_never_sent(client, seeded_bundle_id):
    assert client.get(f"/evidence/{seeded_bundle_id}/report").json()["sent"] is False

def test_candidate_detail_has_reasons(client, seeded):
    d = client.get("/candidates?status=confirmed&limit=1").json()["items"][0]
    full = client.get(f"/domains/{d['id']}").json()
    assert full["confirmation"]["strong_count"] >= 2 and full["confirmation"]["signals"]

def test_campaign_graph_marks_targets(client, seeded, plan_id):
    g = client.get(f"/campaigns/{seeded}/graph").json()
    assert any(n["data"].get("is_target") for n in g["elements"]["nodes"])
```
(Fixtures `client`, `seeded`, `plan_id`, `seeded_bundle_id`, `seeded_bundle_path` defined in `conftest.py` building on `db_engine`, using `tmp_path_factory` for evidence_dir.)
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit `feat(api): full API per contract — stream SSE, domains, campaigns, interdiction, benchmark, evidence, ops`.

---

## Phase 3 — Ledger

### Task 17: Hardhat contracts + tests

**Files:** per `contracts/BUILD_SPEC.md` layout — `contracts/package.json`, `hardhat.config.ts`, `contracts/{OrgRegistry,CampaignRegistry,EvidenceAnchor,Attestation}.sol`, `scripts/deploy.ts`, `test/*.test.ts`, `Dockerfile`.

**Interfaces:**
- Produces: `contracts/deployments/localhost.json` (shape per BUILD_SPEC §6), ABIs at `contracts/artifacts/contracts/*.sol/*.json`. Orgs: signer[1] "Bank One SOC" (org1), signer[2] "Bank Two SOC" (org2); signer[0] = admin only. **`.env`: `ORG_PRIVATE_KEY` = Hardhat account #1 key, `ORG2_PRIVATE_KEY` = account #2** (the baseline `.env.example` said #0, which is the admin and would revert `NotOrg` — corrected here).

- [ ] **Step 1:** `npm init -y && npm i -D hardhat@^2.22.17 @nomicfoundation/hardhat-toolbox@^5.0.0 typescript ts-node` — Hardhat 2.x supports Node 22. `hardhat.config.ts` verbatim from BUILD_SPEC §1.
- [ ] **Step 2: Tests first** — write the nine tests listed in BUILD_SPEC §7, plus `Attestation`: org can attest Disputed after Confirmed; non-org reverts NotOrg. Example (CampaignRegistry):

```ts
import { expect } from "chai"; import { ethers } from "hardhat";
async function deploy() {
  const [admin, org1, org2, rando] = await ethers.getSigners();
  const reg = await (await ethers.getContractFactory("OrgRegistry")).deploy();
  const cr = await (await ethers.getContractFactory("CampaignRegistry")).deploy(await reg.getAddress());
  await reg.registerOrg(org1.address, "Bank One SOC"); await reg.registerOrg(org2.address, "Bank Two SOC");
  return { reg, cr, admin, org1, org2, rando };
}
const id = ethers.id("camp-1"), kit = ethers.id("kit-a"), root = ethers.id("ioc");
it("findByKit returns every campaign for a kit", async () => {
  const { cr, org1, org2 } = await deploy();
  await cr.connect(org1).publishCampaign(id, root, kit, 400, 94);
  await cr.connect(org2).publishCampaign(ethers.id("camp-2"), root, kit, 12, 70);
  expect(await cr.findByKit(kit)).to.deep.equal([id, ethers.id("camp-2")]);
});
it("unregistered address cannot publish", async () => {
  const { cr, rando } = await deploy();
  await expect(cr.connect(rando).publishCampaign(id, root, kit, 1, 1)).to.be.revertedWithCustomError(cr, "NotOrg");
});
it("reporter cannot corroborate own campaign", async () => {
  const { cr, org1 } = await deploy();
  await cr.connect(org1).publishCampaign(id, root, kit, 1, 1);
  await expect(cr.connect(org1).corroborate(id)).to.be.revertedWithCustomError(cr, "SelfCorroboration");
});
```
(EvidenceAnchor tamper test: `verify(bundleId, tamperedRoot)` → `false`; re-anchor → `AlreadyAnchored`.)
- [ ] **Step 3:** `npx hardhat test` → FAIL (no contracts). **Step 4:** add contracts verbatim from BUILD_SPEC §2–5. **Bug fix vs BUILD_SPEC §5 `Attestation.attest`:** the spec's `_attestors` push condition (`== Confirmed && length == 0`) is wrong (default enum value is `Confirmed`, so it only records the very first caller). Replace with a `mapping(bytes32 => mapping(address => bool)) _hasAttested` and push on first attestation by each org. Note this in a code comment. **Step 5:** tests PASS. Deploy script verbatim from §6; `npx hardhat node` + `npx hardhat run scripts/deploy.ts --network localhost` → `deployments/localhost.json` has 4 addresses + 2 orgs.
- [ ] **Step 6: Commit** `feat(contracts): org registry, campaign registry with kit-hash inheritance, evidence anchor, attestation`.

---

### Task 18: Ledger service, anchor worker, ledger endpoints, second org

**Files:**
- Create: `services/api/ledger_service.py`, `services/api/workers/anchor_worker.py`, `services/api/routes/ledger.py`, `services/tests/test_ledger.py`

**Interfaces:**
- Produces (`ledger_service.py`, web3.py, ABIs from artifacts, addresses from `deployments/localhost.json` — never hardcoded):
  - `class Ledger(rpc, deploy_path, org_keys: dict[str,str])`; `.available() -> bool`
  - `.publish_campaign(campaign_id: uuid, ioc_root_hex, kit_hash_hex, domain_count, confidence_0_100, as_org="org1") -> tx_hash`
  - `.anchor_evidence(bundle_id: uuid, root_hex, campaign_id: uuid, as_org="org1") -> tx_hash`
  - `.attest(subject_hash_hex, verdict: "confirmed"|"dismissed"|"disputed", as_org) -> tx_hash`
  - `.corroborate(campaign_id, as_org="org2") -> tx_hash`
  - `.find_by_kit(kit_hash_hex) -> list[dict]` (campaign struct + reporter name from OrgRegistry + `CampaignPublished` event tx hash/time + corroborations from events)
  - `.verify_anchor(bundle_id, root_hex) -> bool`
  - IDs: `bytes32` = `keccak256(uuid string)` for campaign/bundle ids; kit hash = the 32-byte sha256 dom hash as bytes32.
- Anchor worker: polls `anchor_queue where not done order by id`, executes via `Ledger`, on success sets `done`, writes `ledger_events`, updates `campaigns.published_tx` / `evidence_bundles.anchored_tx, anchored_at`; on failure increments `attempts`, `last_error`, exponential backoff (cap 60 s); never blocks anything else.
- Routes: `POST /ledger/publish/{campaign_id}` → enqueue → `{"queued":true,"queue_position":n}`; `GET /ledger/by-kit/{kit_hash}` → contract §6 shape incl. `"local_telemetry_received": false`; `POST /ledger/attest {subject_hash, verdict, as_org}`; `POST /ledger/corroborate/{campaign_id} {as_org}`; when the chain is down: publish/attest still queue (202), by-kit returns 503 problem "Ledger unreachable — queued writes: n".

- [ ] **Step 1: Failing tests** `test_ledger.py` — `@pytest.mark.chain` (skipped unless `CHAIN_RPC` responds): publish as org1 → `find_by_kit` as org2's perspective returns it with reporter "Bank One SOC"; corroborate as org2 appears; anchor + `verify_anchor` true; tampered root false. Non-chain unit test: anchor worker with a fake `Ledger` raising `ConnectionError` → item stays queued with attempts=1, last_error set, and the function returns without raising.
- [ ] **Step 2–4:** FAIL → implement → PASS (run `npx hardhat node` + deploy first). Commit `feat(ledger): web3 ledger service, non-blocking anchor queue, inheritance query, second-org writes`.

---

## Phase 4 — Email headers

### Task 19: Email-header analysis module

**Files:**
- Create: `services/email/__init__.py`, `parse.py`, `signals.py`, `analyze.py`, `samples/*.eml` (≥ 12), `samples/labels.json`, `services/api/routes/email.py`, `services/tests/test_email.py`

**Interfaces:**
- Produces:
```python
@dataclass
class ParsedEmail:
    from_display: str | None; from_addr: str | None; from_etld1: str | None
    reply_to_etld1: str | None; return_path_etld1: str | None; message_id_domain: str | None
    auth: dict[str, str]          # {"spf": "pass|fail|softfail|neutral|none|absent", "dkim": ..., "dmarc": ...}
    received: list[dict]          # [{"from_host","by_host","ip","at": iso|None}] oldest first
    urls: list[str]; link_etld1s: list[str]
    absent: list[str]             # header names not present
def parse_email(raw: str | bytes) -> ParsedEmail          # stdlib email, policy.default; bytes decoded with errors="replace"; body-only/garbage -> all None + absent list, never raises
def compute_signals(p: ParsedEmail, *, brands: BrandIndex, lookup: Callable[[str], DomainLookup]) -> list[Signal]
@dataclass
class DomainLookup: domain_id: int | None; status: str | None; campaign_id: str | None; campaign_label: str | None
@dataclass
class EmailVerdict: verdict: Literal["malicious","suspicious","clean"]; signals: list[Signal]; strong_count: int; parsed: ParsedEmail; linked_campaign_ids: list[str]; linked_domain_ids: list[int]
def analyze(raw, *, brands, lookup, triage_fn=triage) -> EmailVerdict
def persist_and_correlate(c, v: EmailVerdict, source: Literal["analyst","sample"]) -> uuid   # inserts email_analyses; triages link+sender domains, upsert_candidate(source='email') for candidates, LPUSH enrich:queue; NEVER sets confirmed
```
Signals and gate exactly per spec §3.2–3.3. `Signal` is the same dataclass as `services.enrich.confirm.Signal`. Bodies: URL extraction from text/plain and text/html parts (href + bare URLs), then body discarded.
- Routes: `POST /email/analyze` (JSON `{"raw","source"}` or multipart file field `eml`, max 2 MB → 413 problem), `GET /email/analyses`, `GET /email/analyses/{id}`.
- Samples: synthetic `.eml` files (RFC 5322, fictional senders on `.example`/`.top` names, IPs from RFC 5737 ranges) covering: brand display-name spoof + DMARC fail on brand domain (malicious), link to seeded campaign domain + lookalike sender (malicious), Reply-To mismatch only (suspicious), clean newsletter from a legit brand domain with DMARC pass (clean), missing auth headers (suspicious/weak), folded headers, non-UTF-8 bytes, body-only paste. `labels.json` maps filename → expected verdict. Header lines `X-QCertChain-Sample: synthetic` in each.

- [ ] **Step 1: Failing tests** `test_email.py`:

```python
from pathlib import Path
from services.email.analyze import analyze
from services.email.parse import parse_email
from services.email.analyze import DomainLookup
from services.ingest.brands import load_brands
from services.config import SETTINGS

BR = load_brands(SETTINGS.brands_file)
NONE = lambda d: DomainLookup(None, None, None, None)
SPOOF = b"""From: "SBI Alerts" <alerts@sbi-kyc-update.top>
Reply-To: help@sbi-support.click
Return-Path: <bounce@mailer.example>
Message-ID: <x1@mailer.example>
Authentication-Results: mx.example; spf=fail smtp.mailfrom=mailer.example; dkim=none; dmarc=fail header.from=sbi-kyc-update.top
Received: from mailer.example (unknown [203.0.113.9]) by mx.example; Mon, 5 Oct 2026 03:00:00 +0000
Subject: KYC pending

Update now: https://sbi-kyc-update.top/login
"""

def test_auth_results_parsed():
    p = parse_email(SPOOF)
    assert p.auth == {"spf": "fail", "dkim": "none", "dmarc": "fail"} and p.received[0]["ip"] == "203.0.113.9"

def test_display_name_spoof_plus_confirmed_link_is_malicious():
    look = lambda d: DomainLookup(7, "confirmed", "c1", "CAMP-0001") if d == "sbi-kyc-update.top" else NONE(d)
    v = analyze(SPOOF, brands=BR, lookup=look)
    assert v.verdict == "malicious" and v.strong_count >= 2 and v.linked_campaign_ids == ["c1"]

def test_moderate_only_never_malicious():
    v = analyze(SPOOF.replace(b'"SBI Alerts"', b'"Alerts"'), brands=BR, lookup=NONE)
    assert v.verdict == "suspicious" and v.strong_count < 2

def test_legit_brand_dmarc_pass_clean():
    raw = b"From: SBI <alerts@sbi.co.in>\nAuthentication-Results: mx; spf=pass; dkim=pass; dmarc=pass header.from=sbi.co.in\nMessage-ID: <a@sbi.co.in>\n\nhello https://sbi.co.in/x\n"
    assert analyze(raw, brands=BR, lookup=NONE).verdict == "clean"

def test_garbage_and_body_only_never_raise():
    for raw in [b"", b"\xff\xfe\x00junk", "just a body with https://x.top", b"From: =?bad?=\n\n"]:
        v = analyze(raw, brands=BR, lookup=NONE)
        assert v.verdict in {"clean", "suspicious"}

def test_folded_header_parsed():
    raw = b"From: a@b.example\nAuthentication-Results: mx;\n spf=fail;\n dmarc=fail header.from=b.example\n\nx"
    assert parse_email(raw).auth["dmarc"] == "fail"

def test_samples_match_labels():
    import json
    d = Path("services/email/samples"); labels = json.loads((d / "labels.json").read_text())
    for f, want in labels.items():
        assert analyze((d / f).read_bytes(), brands=BR, lookup=NONE).verdict == want, f
```
DB test (`db`): `persist_and_correlate` on SPOOF creates a domain with `source='email'`, `status='candidate'` — never confirmed — and an `email_analyses` row.
- [ ] **Step 2–4:** FAIL → implement → PASS. (Samples whose label depends on a seeded campaign use `lookup` stubs in the DB-backed test, not in `test_samples_match_labels`; label those `suspicious` there and document.) Update `docs/PRD.md` §6 (email in scope, paste/upload only) and `docs/API_CONTRACT.md` §9. Commit `feat(email): header analysis with two-strong-signal gate, correlation into the domain pipeline`.

---

## Phase 5 — Console

### Task 20: Console shell, tokens, SSE stream rail, verdict chip, mode indicator

**Files:** `apps/console/` scaffold (`npm create vite@latest console -- --template react-ts`), `tailwind.config.ts`, `src/styles/tokens.css` (DESIGN §3 verbatim + §4 fonts via Google Fonts IBM Plex), `src/lib/{api.ts,sse.ts}`, `src/components/{VerdictChip,ModeIndicator,StreamLine,Mono}.tsx`, `src/layout/{Header,LeftRail,Main,StreamRail}.tsx`, `src/App.tsx`, `src/test/{verdict_chip,mode,sse}.test.tsx`, `src/fixtures/*.json` (API_CONTRACT shapes).

**Interfaces:**
- Produces: `VerdictChip({status: DomainStatus | EmailVerdict})`; `ModeIndicator({mode, connection, certsPerSec, replayFile})`; `createThrottledStream(url, onLines, {maxPerSec:20, cap:200})` returning `close()`; `api.ts` typed fetchers for every endpoint + `VITE_API_URL`; Tailwind theme maps tokens; radius scale `{none:0, sm:'2px'}` only.

- [ ] **Step 1: Tests first** (vitest + RTL + jsdom):

```tsx
// verdict_chip.test.tsx
import { render } from "@testing-library/react";
import { VerdictChip } from "../components/VerdictChip";
const VERDICT = ["#C0392B", "#4A5D52", "#9A760C"].map(h => h.toLowerCase());
it("candidate never renders a verdict colour", () => {
  const { container, getByText } = render(<VerdictChip status="candidate" />);
  getByText("CANDIDATE");
  const html = container.innerHTML.toLowerCase();
  VERDICT.forEach(c => expect(html).not.toContain(c));
  expect(container.querySelector("[data-swatch]")!.getAttribute("style")).toContain("var(--v-candidate)");
});
it("suspicious email renders grey like a candidate", () => {
  const { container } = render(<VerdictChip status="suspicious" />);
  expect(container.querySelector("[data-swatch]")!.getAttribute("style")).toContain("var(--v-candidate)");
});
it("confirmed shows word and red swatch", () => {
  const { getByText, container } = render(<VerdictChip status="confirmed" />);
  getByText("CONFIRMED");
  expect(container.querySelector("[data-swatch]")!.getAttribute("style")).toContain("var(--v-confirmed)");
});
```
```tsx
// mode.test.tsx — replay and live visually distinct
it("replay differs from live in colour token and label", () => {
  const live = render(<ModeIndicator mode="live" connection="connected" certsPerSec={3204} />).container.innerHTML;
  const rep = render(<ModeIndicator mode="replay" connection="replay" certsPerSec={10} replayFile="capture.jsonl" />).container.innerHTML;
  expect(live).toContain("--state-live"); expect(rep).toContain("--state-replay");
  expect(rep).toContain("REPLAY"); expect(rep).toContain("capture.jsonl"); expect(live).not.toContain("REPLAY");
});
```
```ts
// sse.test.ts — throttle holds at 20/sec under 3000/sec input
import { throttleBuffer } from "../lib/sse";
it("emits <= 20 lines per second and caps at 200", () => {
  vi.useFakeTimers(); const out: string[] = [];
  const t = throttleBuffer((ls) => out.push(...ls), { maxPerSec: 20, cap: 200 });
  for (let i = 0; i < 3000; i++) t.push(String(i));
  vi.advanceTimersByTime(1000); expect(out.length).toBeLessThanOrEqual(20);
});
```
- [ ] **Step 2–4:** FAIL → implement → PASS. Layout per DESIGN §5 (220px / fluid / 300px; stream rail never collapses; < 1100px → 120px bottom strip). Header copy "QCertChain". Commit `feat(console): shell, tokens, SSE stream rail with throttle, verdict chip, mode indicator`.

### Task 21: Console — candidates, domain detail, campaigns, graph

**Files:** `src/views/{DomainDetail,CampaignGraph}.tsx`, `src/lib/cyto.ts`, LeftRail lists, `src/test/graph.test.ts`.
- Domain detail per apps BUILD_SPEC §4 (verdict + every reason with strength, triage reasons + provenance label `rules`/`model`, enrichment, screenshot if present, `source` shown).
- Graph per §5: cose-bilkent, 400 ms settle then `layout.stop()`, dragging disabled (`autoungrabify: true`), 1000-node cap (server truncates; client asserts), targets ringed 2px `--ink-000`. Node kinds include `registrar`.
- Test: `buildStyle()` contains no colour outside tokens; `runLayout()` stops after settle (mock cytoscape layout `stop` called); > 1000 nodes → truncated badge rendered.
- Commit `feat(console): candidates, domain detail with reasons, campaign graph`.

### Task 22: Console — plan, benchmark, evidence tamper, second org, ops log, email analyzer

**Files:** `src/views/{PlanPanel,EvidenceViewer,SecondOrg,OpsLog,EmailAnalyzer}.tsx`, `src/components/BenchmarkTable.tsx`, router (`/`, `/org2`, `/email`), tests `src/test/{benchmark,evidence}.test.tsx`.
- Plan panel per BUILD_SPEC §6: `k` control clamped to max from 422 detail; backend select `cpsat` default; fallback text `qaoa timed out → cpsat`; `n_variables · qubit_count qubits` only when present; quantum framing sentence verbatim under the benchmark (not a heading); hovering a target highlights killed domains in the graph.
- Benchmark test: winning row has `--ink-000` left border whichever backend wins (render with qaoa winning and cpsat winning); failed row shows error text.
- Evidence viewer: tamper flow shows failing row in `--v-confirmed` with expected/found; report preview labelled "Report generated — not sent".
- SecondOrg: starts empty; kit-hash input; shows reporter, timestamp, corroborations; "Inherited from ledger. No raw telemetry received."; Corroborate / Dispute buttons (as org2).
- EmailAnalyzer: paste box + `.eml` drop; signals checklist reused from DomainDetail; links to correlated domains/campaign.
- Design pass: grep the console for `gradient|backdrop|purple|violet|indigo|magenta|rounded-(md|lg|xl|full)|box-shadow` → zero hits.
- Commit `feat(console): plan + benchmark, evidence tamper demo, second org, ops log, email analyzer`.

---

## Phase 6 — Model, measurement, report, deploy

### Task 23: Triage model training (rules first, then train)

**Files:** `services/ml/{datasets,split,train_triage,evaluate,brand_refs}.py`, `services/tests/test_model_checks.py`, artifacts under `services/ml/artifacts/`.
- `datasets.py`: OpenPhish `https://openphish.com/feed.txt` (snapshot with fetch time; free feed has no per-URL timestamps → record snapshot date; accumulate snapshots across runs into `data/openphish_snapshots/` so a temporal split is possible), Tranco 200k random sample negatives, hard negatives = Tranco domains containing any brand token whose eTLD+1 is not a brand legit domain, **excluding** any domain present in the phishing set. **Report counts to the owner** (positives after campaign dedup; hard negatives) before training. Rules from MODELS §8: < 200 hard negatives → tell the owner; positives < 5,000 → stop, keep rules provenance.
- `split.py`: temporal (snapshot date) and campaign-disjoint (group by `etld1` pattern skeleton: digits → `#`, plus shared IP when available).
- `train_triage.py`: `LogisticRegression(class_weight="balanced", max_iter=2000)` + `CalibratedClassifierCV(method="isotonic", cv=5)` on `features.extract(...).vector()`; export `triage_lr.joblib`, `triage_coefficients.json` (`{"features":[...], "coef":[...], "passed_checks": bool}`), `triage_metrics.json`.
- `evaluate.py`: recall@threshold, precision at 1:1000 base rate (`TP_rate*1 / (TP_rate*1 + FP_rate*999)`), hard-negative FP rate, threshold sweep 0.20–0.80 → `threshold_sweep.json`, AUC for both splits. Never balanced precision.
- `test_model_checks.py` — MODELS §7 four checks as failing tests (skip if no model artifact): Tranco top-1000 below threshold; brand legit domains < 0.1; hard-negative FP < 5%; top coefficient share < 0.40. `passed_checks` set true only when all four pass; triage only loads the model when true.
- `brand_refs.py`: fetch each brand legit homepage's favicon (observe only), store `data/brand_favicons.json` {brand: [favicon_hash]} — feeds `favicon_brand_match`. CLIP: not built (MODELS: only if time; owner can request).
- Commit `feat(ml): datasets, temporal + campaign-disjoint splits, calibrated LR, base-rate evaluation, hard checks`.

### Task 24: Measurement — `scripts/evaluate.py` → `reports/metrics.json`

- Sections exactly per spec §4.2. Each metric object: `{"value", "unit", "n", "dataset", "measured_at", "method"}` or `{"unavailable": "<reason>"}`.
- Confirmation precision/recall: start a local `http.server` on 127.0.0.1 serving labelled pages (`services/tests/fixtures/eval_pages/` — kit pages positive; brand-like legit login page replicas negative, all local), run `analyze_page` via the real `fetch` (httpx) against `http://127.0.0.1:<port>/<name>/`. Kit knowledge seeded from a disjoint kit sample to avoid leakage.
- Response time: from DB stage timestamps over the last N live/replay domains (`ct_seen_at → candidate_at → confirmed_at → campaign_joined_at`) plus plan/bundle/anchor timestamps; p50/p95. Run a 20-minute replay at 5× and a seeded run before measuring.
- Lead time: for current OpenPhish entries, look up first CT appearance via crt.sh JSON (`not_before` / `entry_timestamp`); if crt.sh unreachable → `unavailable` (no substitute).
- Interdiction: benchmark on the seeded campaign at k ∈ {3,4,5,6}, 5 repetitions, median ms.
- Test: `services/tests/test_evaluate.py` — given a tiny fixture DB state, `evaluate.py --only response_time` emits correct p50 for known timestamps; metrics never contain balanced precision keys.
- Commit `feat(report): measured precision, latency and response-time metrics`.

### Task 25: `docs/REPORT.md` generator

- `scripts/build_report.py` renders `docs/REPORT.md` from `reports/metrics.json` + `docs/report_template.md`: abstract, problem (PRD §1 numbers with their sources), architecture diagram (ARCHITECTURE §1), method per stage, email module, results tables (every number from metrics.json, with n and date), honest positioning (CLAUDE §2.3/2.4 verbatim framing), limits (HTTP-only phishing, wildcard certs, paste-only email, ≤ 24-qubit QAOA, seed/sample data labelled), demo script (WORKFLOW §5).
- Test: rendering with a metric marked `unavailable` prints "not measured — <reason>", never a number.
- Commit `docs: generated technical report`.

### Task 26: Docker, deploy configs, end-to-end smoke, stale-string sweep

- `services/api/Dockerfile` (python:3.11-slim, `playwright install --with-deps chromium`, requirements + quantum extra), compose services `api`, `ingest`, `triage`, `enrich` (replicas 4, shm 1gb), `anchor`, `certstream`, `hardhat`, `redis`; all read `.env`.
- `railway.json` / per-service config (api, workers, certstream, hardhat, redis); `apps/console/vercel.json` (SPA rewrite, `VITE_API_URL`).
- RUNBOOK §7 smoke sequence passes against Supabase: replay 60 s at 5× → candidates > 0; seed → interdict coverage > 90 %, solve < 1000 ms; tamper demo; org2 inheritance.
- Release gates: `pytest packages/interdict packages/evidence services/tests/test_triage.py services/tests/test_email.py` + `npx hardhat test` + `npm test` in console — all green.
- RUNBOOK §11 sweep + `grep -rni "sever"` → zero hits.
- Commit `chore: containers, deploy configs, smoke-tested end to end`.

### Task 27: Deploy (only on owner's go-ahead)

- Stop and ask the owner for Railway + Vercel tokens and explicit "deploy". Then `railway up` per service with env vars (Supabase pooler URL, keys), `vercel --prod` for the console, warm every endpoint, report URLs. Never put secrets in repo files.

---

## Execution notes

- Order: Tasks 1–3 strictly first (capture runs in background from Task 3 onward). Tasks 7–10 (packages) are independent of 4–6 and of each other's internals.
- Every task ends with its tests green and a commit. Release gates re-run at Task 26.
- Stop-and-ask triggers (from CLAUDE.md §7 + spec): any new dependency not in Global Constraints; any weight/threshold change; any external source unreachable; any performance claim not measured; certstream volume trimming; deploy.
