# Deploying QCertChain

**Not deployed yet.** Deployment is an outward-facing action and waits for the owner's explicit go-ahead
with Railway and Vercel tokens (spec D6). Nothing here has been run against a hosted account.

## Before a public deploy: decide on access control

The API has **no authentication**. On localhost that is fine; on a public URL anyone who finds it could call
`POST /seed/campaign`, `POST /stream/mode`, `POST /ledger/*` (queued chain writes) and `POST /email/analyze`.
Options, for the owner to choose before deploying:

1. Keep the API on Railway's **private network only** and expose just the console through a proxy that
   allows read-only routes plus the demo actions.
2. Add a shared-secret header (one environment variable, checked by a FastAPI dependency) for every
   `POST` route.
3. Deploy only for the demo window and tear down afterwards.

The Hardhat node uses Hardhat's publicly known test keys: it must **never** be publicly reachable — private
networking only.

## Topology

| Service | Where | Image / config |
|---|---|---|
| Database | Supabase (existing project, session pooler, IPv4) | `services/api/schema.sql` applied |
| Redis | Railway Redis plugin | — |
| certstream | Railway, private | `deploy/certstream/Dockerfile` (pinned v1.10.1, reviewed config baked in) |
| hardhat | Railway, private | `contracts/Dockerfile` (node + deploy on boot) |
| api | Railway, public (see access control) | `deploy/railway/api.json` |
| ingest (1 replica), triage, enrich, anchor | Railway, private | `deploy/railway/<name>.json` |
| console | Vercel | `apps/console/vercel.json`, `VITE_API_URL` = the api URL |

## Environment (Railway, shared by api + workers)

```
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
REDIS_URL=${{Redis.REDIS_URL}}
CERTSTREAM_URL=ws://certstream.railway.internal:8080/
CHAIN_RPC=http://hardhat.railway.internal:8545
EVIDENCE_DIR=/data/evidence          # attach a Railway volume at /data, or bundles vanish on redeploy
COLLECTOR_PRIVATE_KEY=<python -m scripts.genkey>
ORG_PRIVATE_KEY=<Hardhat account #1>  ORG2_PRIVATE_KEY=<Hardhat account #2>
CONSOLE_ORIGINS=https://<vercel-app>.vercel.app
USER_AGENT=QCertChain-Scanner/0.1 (phishing research; contact: <owner email>)
```

Secrets go into Railway/Vercel variables only — never into the repository.

## Known constraints

- Chromium needs `/dev/shm`; if confirmation fails on Railway, the enrich worker falls back to httpx and
  bundles are marked `partial` (by design).
- QAOA runs in a worker process inside the api service (~200 MB extra).
- A fresh Hardhat node always deploys to the addresses committed in `contracts/deployments/localhost.json`;
  redeploying the hardhat service resets the chain (the anchor queue re-sends from Postgres).
