# RUNBOOK — QCertChain

Setup, verification, and the things that actually break.

**Run every checkpoint.** Each one takes seconds and catches a class of failure that costs hours if discovered later. The most expensive hackathon failures are environment failures found at hour 30.

---

## Order matters

```
0.  Earthdata-equivalent long pole   → START THE CT CAPTURE FIRST
1.  Toolchain versions
2.  Infrastructure (postgres, redis)
3.  Python environment
4.  Playwright
5.  Node + Hardhat
6.  Data files
7.  End-to-end smoke test
```

---

## 0 · Start the CT capture — before anything else

The public certstream endpoint goes down periodically. Discovering that at hour 34 is unrecoverable.

```bash
mkdir -p data
python -m services.ingest.capture --minutes 30 --out data/capture.jsonl &
```

**✓ Checkpoint:** after 2 minutes, `wc -l data/capture.jsonl` shows thousands of lines.
**✗ If empty:** endpoint may be down. Try `wss://certstream.cloudflare.com/`, or fall back to direct CT log polling per `docs/DATA.md` §1.

Leave it running while you do everything below.

---

## 1 · Toolchain

```bash
python --version      # 3.11.x  — NOT 3.12, qiskit-aer wheels lag
node --version        # 20.x
docker --version      # 24+
docker compose version
```

**✗ Python 3.12:** `qiskit-aer==0.15.1` has no 3.12 wheel on some platforms and will try to build from source. Use 3.11.

---

## 2 · Infrastructure

```bash
cp .env.example .env
docker compose up -d postgres redis
docker compose ps        # both healthy
```

**✓ Checkpoint:**
```bash
docker compose exec postgres psql -U qcertchain -d qcertchain -c "\dt"
# should list ~15 tables — schema.sql runs automatically on first boot
```

**✗ No tables:** the volume was created before `schema.sql` existed. Nuke and retry:
```bash
docker compose down -v && docker compose up -d postgres redis
```

**Redis is configured `noeviction` deliberately.** Silently dropping queued certificates under memory pressure would corrupt the pipeline invisibly. If Redis fills, you want a loud failure.

---

## 3 · Python environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r services/api/requirements.txt
```

**✓ Checkpoint — run this now, not later:**
```bash
python -c "
import fastapi, sqlalchemy, redis, websockets, httpx
import dns.resolver, tldextract, rapidfuzz, mmh3, nacl, networkx
from ortools.sat.python import cp_model
print('core ok')
"
python -c "import qiskit, qiskit_aer; print('quantum ok', qiskit.__version__)"
```

**✗ If quantum fails and core passes:** fine. The system runs without Qiskit by design (`CLAUDE.md` §2.3). Note it and move on — do not spend an hour here.

**✗ If `ortools` fails:** this one matters, it is the production solver. Try `pip install ortools --no-cache-dir`.

**Commit the lockfile now:**
```bash
pip freeze > services/api/requirements.lock
git add services/api/requirements.lock && git commit -m "lock deps"
```

Version drift across `qiskit` / `qiskit-aer` is the single most likely thing to eat a night.

---

## 4 · Playwright

```bash
playwright install chromium
playwright install-deps chromium     # Linux only
```

**✓ Checkpoint:**
```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); pg.goto('https://example.com')
    print('playwright ok:', pg.title())
    b.close()
"
```

**✗ If this fails:** confirmation falls back to `httpx` + raw HTML. You lose screenshots; evidence bundles get `partial: true`. **Do not let this block you** — note it and continue.

**In Docker:** `shm_size: 1gb` is already set in `docker-compose.yml`. Chromium crashes on the default 64 MB.

---

## 5 · Node and Hardhat

```bash
cd contracts && npm install && npx hardhat compile
npx hardhat node &                                  # separate terminal
npx hardhat run scripts/deploy.ts --network localhost
cat deployments/localhost.json
```

**✓ Checkpoint:** the JSON lists four contract addresses and two orgs.

**✗ If `npm install` hangs:**
```bash
rm -rf node_modules package-lock.json
npm cache clean --force
npm install --prefer-offline --no-audit --no-fund
# still hanging → npm config set registry https://registry.npmmirror.com
# still hanging → npm i -g pnpm && pnpm install
```

**Try this on a second machine in parallel.** If it installs there, the problem is the environment, not the project, and you verify from that machine instead of debugging.

---

## 6 · Data files

```bash
# allowlist — Tranco top 100k
curl -sL https://tranco-list.eu/top-1m.csv.zip -o /tmp/t.zip
unzip -p /tmp/t.zip | head -100000 | cut -d, -f2 > data/allowlist.txt
wc -l data/allowlist.txt        # 100000

# ASN dataset (offline after this)
pyasn_util_download.py --latest
pyasn_util_convert.py --single rib.*.bz2 data/ipasn.dat

# brands.yaml — hand-written, ~40 Indian brands, see docs/DATA.md §4
```

**✓ Checkpoint — the single most important test in this document:**
```bash
python -c "
from services.ingest.triage import triage
for d in ['google.com','sbi.co.in','hdfcbank.com','paytm.com','amazon.in']:
    r = triage(d)
    assert r.score < 0.45, f'FAIL: {d} scored {r.score}'
print('allowlist ok — no legitimate domain flagged')
"
```

**✗ If any legitimate domain scores above threshold, stop and fix it.** Flagging `google.com` during a demo is unrecoverable. This check is a CI gate in `docs/MODELS.md` §7.

---

## 7 · End-to-end smoke test

```bash
# API
cd services/api && uvicorn main:app --reload &
curl -s localhost:8000/health | jq

# workers
python -m services.api.workers.triage_worker &
python -m services.api.workers.enrich_worker &

# stream, in replay mode so it is deterministic
curl -sX POST localhost:8000/admin/stream/mode -H "X-API-Key: $QCC_KEY_ADMIN" -H 'content-type: application/json' \
     -d '{"mode":"replay","speed":5.0}' | jq
python -m services.ingest.stream &

sleep 60
curl -s -H "X-API-Key: $QCC_KEY_ORG1" 'localhost:8000/candidates?limit=5' | jq '.total'
```

**✓ Checkpoint:** `total` is greater than zero.
**✗ If zero after 60 s at 5× replay:** either triage threshold is too high, or the replay file has no interesting names. Check `data/capture.jsonl` contains variety — a 30-minute capture should surface several candidates.

```bash
# seed a campaign and run the full contribution path
CAMP=$(curl -sX POST localhost:8000/admin/seed -H "X-API-Key: $QCC_KEY_ADMIN" -H 'content-type: application/json' \
  -d '{"label":"smoke","domains":400,"ips":12,"asns":3,"nameservers":4,"org":"org1"}' | jq -r .campaign_id)

curl -sX POST "localhost:8000/campaigns/$CAMP/interdict" -H "X-API-Key: $QCC_KEY_ORG1" -H 'content-type: application/json' \
  -d '{"k":5,"backend":"cpsat"}' | jq '{domains_killed, coverage_pct, solve_ms}'
```

**✓ Checkpoint:** `coverage_pct` above 90, `solve_ms` under 1000.

```bash
# console
cd apps/console && npm install && npm run dev
```

**✓ Final checkpoint:** open the console. Stream rail scrolling. Mode indicator says REPLAY. Campaign visible. Plan renders.

---

## 8 · Release gates — green before demo

```bash
cd packages/interdict && pytest        # test_interdict, test_fallback
cd packages/evidence   && pytest       # test_evidence
cd contracts && npx hardhat test       # findByKit, tamper detection
cd services && pytest tests/test_triage.py
```

Four gates from `CLAUDE.md` §6. Do not demo without all four green.

---

## 9 · Demo preflight

Run this **30 minutes before** presenting, not five.

```
[ ] Both deploys warm — hit every endpoint once so nothing cold-starts on stage
[ ] Live stream connected, or replay file confirmed present
[ ] Seeded campaign exists and renders as a graph
[ ] Interdiction returns a plan in under 1 second
[ ] Evidence tamper demo rehearsed — you know which byte to change
[ ] Second-org view inherits from the chain
[ ] Backup video on two laptops and a phone
[ ] Mode indicator reads correctly for whatever mode you are in
[ ] Console zoom level set — 1440p projector, not your laptop screen
```

---

## 10 · Failures ranked by likelihood

| Rank | Failure | Fix |
|---|---|---|
| 1 | certstream endpoint down | Replay mode. **This is why §0 is first.** |
| 2 | `npm install` hangs | §5 escalation, and try a second machine in parallel |
| 3 | Playwright won't install | `httpx` fallback; partial bundles; continue |
| 4 | qiskit-aer version conflict | Ship CP-SAT only; reframe as "quantum backend pending" |
| 5 | Triage too slow | Profile; length-bucketed Levenshtein index; raise threshold last |
| 6 | Clustering merges everything | Raise the edge threshold. **Never lower it to inflate the demo.** |
| 7 | Hardhat unstable | Contracts still unit-testable; anchoring queues |
| 8 | Postgres volume has stale schema | `docker compose down -v` and retry |

---

## 11 · Stale-string sweep — do this in Phase 6

```bash
grep -ri "TODO\|FIXME\|placeholder\|lorem\|QCERTCHAIN_PLACEHOLDER" --include="*.py" --include="*.tsx" --include="*.ts" .
```

Previous builds have shipped with a stale region name rendering live on a demo page. Grep before freezing.
