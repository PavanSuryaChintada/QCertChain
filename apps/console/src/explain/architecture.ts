/** "How it works, step by step" below the Architecture diagram (owner request 2026-10-10): plain words, the code
 *  behind each step, the tech stack. Describes only what runs today; no typed numbers (live and measured figures come
 *  from the API and from measured.ts). The takedown step shows FRAMING verbatim (CLAUDE.md §2.3). */
import type { MeasuredId } from "./measured";

export interface ArchStep {
  id: string;
  title: string;
  text: string;
  /** repository paths of the code that does it */
  code: string[];
  live?: { label: string; to: string };
  /** the generated measurement for this step, when there is one */
  measured?: MeasuredId;
}

export const ARCH_INTRO =
  "What happens to a certificate from the moment it is logged to a takedown plan, and which code does each part.";

export const ARCH_STEPS: ArchStep[] = [
  {
    id: "feed", title: "The certificate feed",
    text: "Every HTTPS certificate is published in public Certificate Transparency logs. Our own copy of certstream-server-go, running in Docker, reads those logs and streams each new certificate over a websocket.",
    code: ["docker-compose.yml"], measured: "relay",
  },
  {
    id: "ingest", title: "Ingest",
    text: "One process reads that websocket, pulls out each certificate's domain names, issuer and time, drops certificates it has already seen, and adds the rest to a Redis stream.",
    code: ["services/ingest/stream.py", "services/ingest/certparse.py"],
  },
  {
    id: "redis", title: "Redis, the waiting room",
    text: "Redis keeps the work in memory: a stream of incoming certificates that the triage workers share (a crashed worker's items are picked up again), a to-do list of pages to check with the newest first, and a broadcast channel for the live screens. It never drops queued work when it is full, and it keeps bursts away from the database.",
    code: ["docker-compose.yml", "services/api/workers/triage_worker.py"],
  },
  {
    id: "triage", title: "Triage, the quick filter",
    text: "Workers read certificates in batches and score every name: a brand from the brand list, look-alikes built from confusable characters, phishing words and risky top-level domains. A high score makes a candidate, saved to the database and put on the page-check list of the organisation that owns the brand's sector. A candidate is suspicious, not verified.",
    code: ["services/api/workers/triage_worker.py", "services/ingest/triage.py", "services/ingest/homoglyph.py", "data/brands.yaml"],
    live: { label: "See the live queue", to: "/queue?status=all" }, measured: "triage",
  },
  {
    id: "check", title: "Page check, the proof",
    text: "A worker opens the newest candidate in a headless Chrome and only looks: it never fills in a form or clicks. It collects the screenshot, the page, the TLS certificate, DNS, WHOIS and the hosting network, then looks for strong signals: a cloned login form, passwords sent to a foreign site, a known phishing kit. Two strong signals confirm the domain; the database refuses a confirmation with fewer.",
    code: ["services/api/workers/enrich_worker.py", "services/enrich/fetch.py", "services/enrich/enrichers.py", "services/enrich/confirm.py", "services/enrich/exfil.py", "services/enrich/fingerprint.py"],
    live: { label: "See confirmed domains", to: "/queue?status=confirmed" }, measured: "verdict",
  },
  {
    id: "evidence", title: "Evidence",
    text: "Each collected file gets a SHA-256 fingerprint. The fingerprints are combined into one Merkle root, and the root is signed with an Ed25519 key. Change one byte of any file and the check fails.",
    code: ["packages/evidence"],
    live: { label: "See the evidence bundles", to: "/evidence" }, measured: "verify",
  },
  {
    id: "ledger", title: "The ledger",
    text: "A worker writes each root to a permissioned EVM chain, signed with the organisation's own key. Only hashes go on chain, never page content or personal data, and another organisation can find a report by its kit hash.",
    code: ["services/api/workers/anchor_worker.py", "contracts"],
    live: { label: "See the ledger", to: "/ledger" },
  },
  {
    id: "campaigns", title: "Campaigns",
    text: "Confirmed domains are linked by what they share: a hosting address, a nameserver, a registrar or a phishing kit. Each linked group is one campaign, run by one operator.",
    code: ["services/graph"],
    live: { label: "See the campaigns", to: "/campaigns" },
  },
  {
    id: "takedown", title: "Takedown plan",
    text: "The planner picks the fewest hosting, DNS or registrar targets that take the most domains offline, and writes the abuse reports for an analyst to review. Nothing is ever sent automatically.",
    code: ["packages/interdict"],
    live: { label: "Open a campaign's takedown plan", to: "/campaigns" }, measured: "plan",
  },
  {
    id: "api", title: "API and database",
    text: "A FastAPI service serves everything. The database is Supabase Postgres with row-level security: every query sees only the data of the organisation whose key made it. Keys are stored as hashes.",
    code: ["services/api/main.py", "services/api/schema.sql"],
    live: { label: "See system health", to: "/health" },
  },
  {
    id: "console", title: "This console",
    text: "React, Vite and TypeScript, with TanStack Query for data. It talks only to the API, always with its key.",
    code: ["apps/console"],
  },
  {
    id: "served", title: "How it is served",
    text: "The console is hosted on Vercel. The API runs on the presenting laptop behind a free Cloudflare quick tunnel, whose address is published in Supabase for the site to look up.",
    code: ["scripts/tunnel.py", "apps/console/src/lib/apiUrl.ts"],
  },
];

export const STACK: { part: string; tech: string }[] = [
  { part: "Certificate feed", tech: "certstream-server-go, self-hosted in Docker" },
  { part: "Queues", tech: "Redis: a stream, a list and a broadcast channel" },
  { part: "Workers and API", tech: "Python, FastAPI, SQLAlchemy" },
  { part: "Page checks", tech: "Playwright with headless Chrome, dnspython, WHOIS and RDAP" },
  { part: "Database", tech: "Supabase Postgres with row-level security" },
  { part: "Evidence", tech: "SHA-256, a Merkle tree, Ed25519 signatures (PyNaCl)" },
  { part: "Ledger", tech: "Solidity contracts on a permissioned EVM chain (Hardhat)" },
  { part: "Campaigns", tech: "NetworkX graph clustering" },
  { part: "Takedown plan", tech: "OR-Tools CP-SAT; the same formulation on QAOA (Qiskit)" },
  { part: "Console", tech: "React, Vite, TypeScript, TanStack Query" },
  { part: "Hosting", tech: "Vercel for the console, a Cloudflare quick tunnel for the API" },
];
