// Typed client for docs/API_CONTRACT.md. The console talks only to the QCertChain API.
import { authHeaders, setKey } from "./auth";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export type DomainStatus = "candidate" | "confirmed" | "dismissed" | "unreachable";
export type EmailVerdict = "malicious" | "suspicious" | "clean";
export type Backend = "cpsat" | "qaoa" | "annealing" | "greedy";
export type Source = "certstream" | "replay" | "seed" | "email" | "sample";

export interface Problem { type: string; title: string; status: number; detail?: string | null; instance?: string | null }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }

export interface StreamState {
  mode: "live" | "replay"; connection: "connected" | "reconnecting" | "down" | "replay";
  certs_per_sec: number; names_per_sec: number; candidates_per_min: number;
  queue_depth: Record<string, number>; replay_file: string | null; last_heartbeat: string | null;
}
export interface Metrics {
  campaigns_active: number; domains_confirmed: number; domains_candidate: number; certs_per_sec: number;
  plans_today: number; bundles_today: number; anchor_queue_depth: number;
}
export interface CandidateItem {
  id: number; name: string; etld1: string; status: DomainStatus; triage_score: number | null;
  brand_matched: string | null; confidence: number | null; campaign_id: string | null; first_seen: string; source: Source;
}
export interface Signal { name: string; strength: "strong" | "moderate" | "weak"; detail: string }
export interface Reason { feature: string; value: unknown; contribution: number }
export interface DomainDetail {
  id: number; name: string; etld1: string; status: DomainStatus; source: Source; first_seen: string; last_seen: string;
  triage: { score: number | null; provenance: "rules" | "model"; threshold: number; reasons: Reason[] };
  confirmation: null | { verdict: string; confidence: number | null; confirmed_at: string | null; signals: Signal[];
    strong_count: number; screenshot_url: string | null };
  enrichment: null | { ip_addresses: string[]; asn: number | null; asn_name: string | null; country: string | null;
    nameservers: string[]; cert_issuer: string | null; registrar: string | null; registered_at: string | null;
    dom_hash: string | null; favicon_hash: string | null; partial: boolean; errors: Record<string, string> | null };
  campaign_id: string | null; evidence_bundle_id: string | null;
}
export interface Campaign {
  id: string; label: string | null; kit_hash: string | null; domain_count: number; infra_count: number;
  confidence: number | null; brands: string[]; status: string; first_seen: string; published_tx: string | null;
}
export interface GraphNodeData {
  id: string; kind: string; label: string; status?: DomainStatus; domain_count?: number; is_target?: boolean; target_rank?: number;
}
export interface Graph {
  campaign_id: string; truncated: boolean; node_count: number;
  elements: { nodes: { data: GraphNodeData }[]; edges: { data: { id: string; source: string; target: string; weight: number } }[] };
}
export interface Target { rank: number; node_id: number; kind: string; value: string; kills: number; takedown_route: string }
export interface Plan {
  plan_id: string; campaign_id: string; budget_k: number; backend: Backend; fell_back: boolean; fallback_from: string | null;
  objective: number; domains_killed: number; domains_total: number; coverage_pct: number; n_variables: number;
  qubit_count: number | null; solve_ms: number; valid: boolean; targets: Target[]; killed_domain_ids: number[]; notes: string[];
}
export interface BenchmarkRow {
  backend: Backend; objective: number; domains_killed: number; coverage_pct: number; solve_ms: number; valid: boolean;
  qubit_count: number | null; n_variables: number; is_best: boolean; error: string | null; notes: string[];
}
export interface Benchmark { plan_id: string; n_variables: number; rows: BenchmarkRow[]; note: string }
export interface Artifact { name: string; sha256: string; size_bytes: number | null; url: string }
export interface Evidence {
  id: string; domain_id: number | null; campaign_id: string | null; bundle_root: string; signature: string;
  collector_pk: string; partial: boolean; created_at: string; anchored_tx: string | null; anchored_at: string | null;
  artifacts: Artifact[];
}
export interface VerifyResult {
  valid: boolean; root_matches: boolean; signature_valid: boolean; expected_root: string | null; computed_root: string | null;
  failures: { artifact: string; expected: string | null; found: string | null; reason: string }[];
}
export interface Report { bundle_id: string; recipient: string | null; format: "markdown"; body: string; sent: false; generated_at: string }
export interface OpsItem { id: number; at: string; channel: string; severity: number; message: string; context: unknown }
export interface InheritedCampaign {
  campaign_id: string | null; yours: boolean; chain_campaign_id: string; ioc_root: string; kit_hash: string; domain_count: number; confidence: number;
  reporter: { address: string; name: string }; published_at: string; tx_hash: string | null;
  corroborations: { address: string; name: string; at: string }[];
}
export interface ByKit { kit_hash: string; campaigns: InheritedCampaign[]; local_telemetry_received: false }
export interface LedgerStatus {
  available: boolean; queue_depth: number; you: string; orgs: Record<string, { address: string; name: string | null }>;
}
export interface EmailAnalysis {
  id: string; source: "analyst" | "sample"; verdict: EmailVerdict; strong_count: number; from_addr: string | null;
  from_etld1: string | null; reply_to_etld1: string | null; return_path_etld1: string | null;
  auth: Record<string, string>; received: { from_host: string | null; ip: string | null; at: string | null }[];
  urls: string[]; signals: Signal[]; linked_campaigns?: { id: string; label: string | null }[];
  linked_domain_ids: number[]; new_candidate_ids?: number[]; absent?: string[];
}

export class ApiError extends Error {
  constructor(public problem: Problem) { super(problem.detail ?? problem.title); }
}

/** Every request carries the key. A 401 means the key is missing, revoked or wrong: drop it so the key gate shows. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const r = await fetch(API_URL + path, { ...init, headers: { ...authHeaders(), ...(init?.headers ?? {}) } });
  if (r.status === 401) setKey(null);
  return r;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  if (!r.ok) {
    let p: Problem;
    try { p = await r.json(); } catch { p = { type: "about:blank", title: r.statusText, status: r.status }; }
    throw new ApiError(p);
  }
  return r.json() as Promise<T>;
}
const post = <T,>(path: string, body?: unknown) => call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  streamState: () => call<StreamState>("/stream/state"),
  metrics: () => call<Metrics>("/metrics"),
  candidates: (q = "") => call<Page<CandidateItem>>(`/candidates${q}`),
  domain: (id: number) => call<DomainDetail>(`/domains/${id}`),
  reconfirm: (id: number) => post<{ queued: boolean }>(`/domains/${id}/confirm`),
  campaigns: () => call<Page<Campaign>>("/campaigns?limit=100"),
  campaign: (id: string) => call<Campaign>(`/campaigns/${id}`),
  graph: (id: string) => call<Graph>(`/campaigns/${id}/graph`),
  interdict: (id: string, k: number, backend: Backend) => post<Plan>(`/campaigns/${id}/interdict`, { k, backend }),
  plan: (id: string) => call<Plan>(`/plans/${id}`),
  benchmark: (planId: string) => post<Benchmark>(`/plans/${planId}/benchmark`),
  evidence: (id: string) => call<Evidence>(`/evidence/${id}`),
  verify: (id: string) => call<VerifyResult>(`/evidence/${id}/verify`),  // GET: verification writes nothing
  report: (id: string) => call<Report>(`/evidence/${id}/report`),
  publish: (campaignId: string) => post<{ queued: boolean; queue_position: number }>(`/ledger/publish/${campaignId}`),
  byKit: (kit: string) => call<ByKit>(`/ledger/by-kit/${kit}`),
  ledgerStatus: () => call<LedgerStatus>("/ledger/status"),
  // The signing organisation is the key's organisation: there is no "as org" to choose.
  corroborate: (chainCampaignId: string) => post<{ queued: boolean; as_org: string }>(`/ledger/corroborate/${chainCampaignId}`),
  attest: (subject: string, verdict: "confirmed" | "dismissed" | "disputed") =>
    post<{ queued: boolean; as_org: string }>("/ledger/attest", { subject_hash: subject, verdict }),
  ops: (channel?: string) => call<Page<OpsItem>>(`/ops/log?limit=200${channel ? `&channel=${channel}` : ""}`),
  analyzeEmail: (raw: string) => post<EmailAnalysis>("/email/analyze", { raw, source: "analyst" }),
  analyzeEmailFile: async (f: File) => {
    const fd = new FormData();
    fd.append("eml", f);
    const r = await apiFetch("/email/analyze", { method: "POST", body: fd });
    if (!r.ok) throw new ApiError(await r.json());
    return (await r.json()) as EmailAnalysis;
  },
  /** Binary artifacts (the screenshot) need the key too, so they are fetched, not linked. */
  artifactBlobUrl: async (path: string) => {
    const r = await apiFetch(path);
    if (!r.ok) throw new ApiError({ type: "about:blank", title: r.statusText, status: r.status });
    return URL.createObjectURL(await r.blob());
  },
  emailAnalyses: () => call<Page<EmailAnalysis>>("/email/analyses?limit=50"),
};
