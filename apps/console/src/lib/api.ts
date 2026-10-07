// Typed client for the QCertChain API. The console talks only to this API, always with the X-API-Key header.
import { authHeaders, setKey } from "./auth";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export type DomainStatus = "candidate" | "confirmed" | "dismissed" | "unreachable";
export type EmailVerdict = "malicious" | "suspicious" | "clean";
export type Backend = "cpsat" | "qaoa" | "annealing" | "greedy" | "bruteforce";
export type Source = "certstream" | "replay" | "seed" | "email" | "sample";
export type ComponentStatus = "ok" | "degraded" | "failed";
export type KeyKind = "org" | "demo" | "admin";
export type NodeKind = "ip" | "asn" | "nameserver" | "cert_issuer" | "kit_hash" | "favicon_hash" | "registrar";
export type Route = "hosting" | "dns" | "registrar";

export interface Problem { type: string; title: string; status: number; detail?: string | null; instance?: string | null }
export interface Page<T> { items: T[]; limit: number; next_cursor: string | null }

/** Anything a section may report instead of a measurement. */
export interface Unavailable { unavailable: string }
export const isUnavailable = (x: unknown): x is Unavailable =>
  !!x && typeof x === "object" && typeof (x as Unavailable).unavailable === "string";

// ---------- health / status ----------
export interface EndpointTiming { count: number; p50_ms: number | null; p95_ms: number | null }
export interface Health {
  status: string; service: string;
  regions: { api: string | null; api_city: string | null; database: string | null; database_city: string | null; colocated: boolean | null };
  database_round_trip_ms: number | null;
  endpoints: Record<string, EndpointTiming>;
  window_s: number;
}
export interface StreamState {
  mode: "live" | "replay"; connection: "connected" | "reconnecting" | "down" | "replay";
  certs_per_sec: number; names_per_sec: number; candidates_per_min: number;
  queue_depth: { certs_raw?: number; enrich?: number; [k: string]: number | undefined };
  replay_file: string | null; last_heartbeat: string | null;
  /** replay only: the replayed certificates' ORIGINAL CT time, and the speed (360 = 24 h in 4 min) */
  virtual_time?: string | null; replay_speed?: number | null;
}
export interface Metrics {
  campaigns_active: number; domains_confirmed: number; domains_candidate: number; certs_per_sec: number;
  plans_today: number; bundles_today: number; anchor_queue_depth: number;
}
export type ComponentKey = "ct" | "triage" | "confirm" | "enrich" | "graph" | "interdiction" | "evidence" | "ledger" | "email";
export interface ComponentState { status: ComponentStatus; detail: string | null }
export interface SystemStatus {
  org: { slug: string; name: string };
  key_kind: KeyKind;
  stream: StreamState;
  metrics: Metrics & { candidates_last_hour: number; confirmations_last_hour: number };
  ledger: { available: boolean; queue_depth: number };
  components: Partial<Record<ComponentKey, ComponentState>>;
  health: Health;
}

// ---------- candidates / domains ----------
export interface Reason { feature: string; value: unknown; contribution: number }
export interface TriageReasons { score: number | null; provenance: "rules" | "model" | string; threshold: number; reasons: Reason[] }
export interface CandidateItem {
  id: number; name: string; etld1: string; status: DomainStatus; triage_score: number | null;
  brand_matched: string | null; confidence: number | null; campaign_id: string | null; first_seen: string; source: Source;
  triage_reasons: TriageReasons | null;
}
export interface CandidateCounts { all: number; candidate: number; confirmed: number; dismissed: number; unreachable: number }
export interface Signal { name: string; strength: "strong" | "moderate" | "weak"; detail: string }
export interface Enrichment {
  ip_addresses: string[]; asn: number | null; asn_name: string | null; country: string | null;
  nameservers: string[]; cert_issuer: string | null; registrar: string | null; registered_at: string | null;
  dom_hash: string | null; favicon_hash: string | null; partial: boolean; errors: Record<string, string> | null;
}
export interface DomainDetail {
  id: number; name: string; etld1: string; status: DomainStatus; source: Source; first_seen: string; last_seen: string;
  triage: TriageReasons;
  confirmation: null | { verdict: string; confidence: number | null; confirmed_at: string | null; signals: Signal[];
    strong_count: number; screenshot_url: string | null };
  enrichment: Enrichment | null;
  campaign_id: string | null; evidence_bundle_id: string | null;
}

// ---------- campaigns / interdiction ----------
export interface Campaign {
  id: string; label: string | null; kit_hash: string | null; domain_count: number; infra_count: number;
  confidence: number | null; brands: string[]; status: string; first_seen: string; published_tx: string | null;
  last_seen?: string | null; has_plan?: boolean; anchored?: boolean;
}
/** [id, name, status] */
export type GraphDomain = [number, string, DomainStatus];
/** [id, kind, value, domain_count, targetable] */
export type GraphNode = [number, NodeKind, string, number, boolean];
/** [domain_id, node_id, weight] */
export type GraphEdge = [number, number, number];
export interface CampaignGraph {
  campaign_id: string; n_targetable: number; search_space_log2: number;
  domains: GraphDomain[]; nodes: GraphNode[]; edges: GraphEdge[]; targets: [number, number][]; built_at: string;
  /** domains whose only infrastructure is non-targetable (shared DNS): no plan at any k reaches them */
  uncoverable_domain_ids?: number[];
}
export interface SweepTarget { node_id: number; kind: NodeKind; value: string; kills: number; route: Route }
export interface SweepPoint {
  k: number; backend: Backend; domains_killed: number; domains_total: number; coverage_pct: number; solve_ms: number;
  valid: boolean; notes: string[]; targets: SweepTarget[]; killed_ids: number[];
}
export interface Sweep {
  campaign_id: string; n_targetable: number; search_space_log2: number; cached: boolean; points: SweepPoint[];
  /** domains no takedown at any k can reach, and the ceiling that leaves */
  uncoverable_domain_ids?: number[]; coverable_total?: number; domains_total?: number;
}
export interface Target { rank: number; node_id: number; kind: string; value: string; kills: number; takedown_route: string }
export interface Plan {
  plan_id: string; campaign_id: string; budget_k: number; backend: Backend; fell_back: boolean; fallback_from: string | null;
  objective: number; domains_killed: number; domains_total: number; coverage_pct: number; n_variables: number;
  qubit_count: number | null; solve_ms: number; valid: boolean; targets: Target[]; killed_domain_ids: number[]; notes: string[];
}
export interface BenchmarkRow {
  backend: Backend; domains_covered: number | null; domains_total: number | null; targets_used: number | null;
  solve_ms: number | null; gap_vs_cpsat_pct: number | null; valid: boolean; is_best: boolean; error: string | null; notes: string[];
  /** bruteforce only: the k-target plans checked, C(n, k) */
  subsets_checked?: number | null;
}
export interface Formulation {
  qubo_variables: number; qubit_count: number; circuit_depth: number | null; p_layers: number; shots: number; warm_start: string;
  reduction: { original_nodes: number; original_domains: number; collapsed_groups: number; kept_nodes: number;
    pruned_nodes: number; unreachable_weight: number; notes: string[] };
}
export interface Benchmark {
  campaign_id: string; k: number; cached: boolean; computed_at: string; rows: BenchmarkRow[]; formulation: Formulation; framing: string;
  n_targetable?: number; /** C(n, k): the plans an exhaustive search checks at this budget */ plans_at_k?: number;
}
/** One synthetic campaign size on GET /scaling. Times are ms; bruteforce_ms is extrapolated from the fit when flagged. */
export interface ScalingPoint {
  n: number; k?: number; subsets_log2: number; plans_log2?: number;
  bruteforce_ms: number | null; bruteforce_extrapolated: boolean;
  cpsat_ms: number | null; cpsat_status: string | null; greedy_ms: number | null;
  qaoa_ms: number | null; qaoa_note: string | null;
  coverage: { cpsat: number | null; greedy: number | null; qaoa: number | null; bruteforce: number | null };
}
export interface Scaling {
  generated_at: string; k: number | string | null; k_rule?: string; method: string; machine: string;
  fit: { ns_per_subset: number };
  thresholds: { one_second: { n: number | null }; one_hour: { n: number | null }; one_year: { n: number | null } };
  points: ScalingPoint[];
}

// ---------- evidence ----------
export interface Artifact { name: string; sha256: string; size_bytes: number | null; url: string }
export interface Evidence {
  id: string; domain_id: number | null; campaign_id: string | null; bundle_root: string; signature: string;
  collector_pk: string; partial: boolean; created_at: string; anchored_tx: string | null; anchored_at: string | null;
  artifacts: Artifact[];
}
export interface VerifyFailure { artifact: string; expected: string | null; found: string | null; reason: "hash_mismatch" | "missing" | "unexpected" }
export interface VerifyResult {
  valid: boolean; root_matches: boolean; signature_valid: boolean; expected_root: string | null; computed_root: string | null;
  failures: VerifyFailure[];
  anchor: { status: "matches" | "mismatch" | "not_anchored" | "unavailable"; tx: string | null };
  tree: { leaves: { name: string; leaf: string }[]; levels: string[][] };
  attestations: Record<string, "confirmed" | "dismissed" | "disputed" | string>;
  disputed: boolean;
  simulated_tamper: string | null;
}
export interface Report { bundle_id: string; recipient: string | null; format: string; body: string; generated_at: string }

// ---------- email ----------
export interface EmailAnalysis {
  id: string; source: string; verdict: EmailVerdict; strong_count: number; from_addr: string | null;
  from_etld1: string | null; reply_to_etld1: string | null; return_path_etld1: string | null;
  auth: { spf?: string; dkim?: string; dmarc?: string; [k: string]: string | undefined };
  received: { from_host: string | null; by_host?: string | null; ip: string | null; at: string | null }[];
  urls: string[]; signals: Signal[]; linked_campaigns: { id: string; label: string | null }[];
  linked_domain_ids: number[]; new_candidate_ids: number[]; absent: string[];
  verdict_history?: { at: string; from: string; to: string; reason: string }[]; rescored_at?: string | null;
  created_at?: string;
}

// ---------- ledger ----------
export interface LedgerStatus {
  available: boolean; queue_depth: number; you: string; orgs: Record<string, { address: string; name: string | null }>; reason?: string | null;
}
export interface LedgerCampaign {
  chain_campaign_id: string; ioc_root: string; kit_hash: string; domain_count: number; confidence: number;
  reporter: { address: string; name: string }; published_at: string; tx_hash: string | null;
  corroborations: { address: string; name: string; at: string }[]; campaign_id: string | null; yours: boolean;
}
export interface ByKit { kit_hash: string; campaigns: LedgerCampaign[]; local_telemetry_received: false }
export interface LedgerEvent {
  id: number; kind: "campaign_published" | "evidence_anchored" | "attested" | "corroborated"; tx_hash: string;
  block_number: number; subject: string; org_address: string; payload: Record<string, unknown> | null; observed_at: string;
}
export interface Queued { queued: boolean; queue_position?: number; as_org?: string }

// ---------- metrics / ops ----------
export interface ThresholdOption {
  threshold: number; precision_at_1_in_1000: number | null; recall_our_brands: number | null; recall_global_feeds: number | null;
  fp_rate_random_tranco: number | null; hard_negative_fp_rate: number | null; candidates_per_hour_live: number | null;
}
export interface StageTiming {
  p50_ms?: number | string | null; p95_ms?: number | string | null; p50?: number | string | null; p95?: number | string | null; n?: number;
}
export interface LeadTime {
  // shape written by scripts/evaluate.py: matched_domains, ct_first, listed_before_ct_seen, lead_hours {p50,p95,max}
  matched_domains?: number; ct_first?: number; listed_before_ct_seen?: number;
  lead_hours?: { p50?: number | null; p95?: number | null; max?: number | null }; dataset?: string; caveat?: string;
  n?: number; n_matched?: number; n_ct_first?: number; median_lead_s?: number | null; median_lead_minutes?: number | null;
  p25_lead_s?: number | null; p75_lead_s?: number | null; method?: string; [k: string]: unknown;
}
type Section<T> = T | Unavailable;
export interface MetricsReport {
  triage_rules: Section<{
    threshold: number;
    precision_at_1_in_1000_base_rate: { value: number | null; method: string };
    hard_negative_fp_rate: { value: number | null; n: number };
    false_positive_rate: { value: number | null; n: number };
    recall_on_phishing_naming_our_40_brands: { value: number | null; n: number };
    latency_us_per_name: { p50: number; p95: number; p99: number };
  }>;
  triage_threshold_options: Section<{ options: ThresholdOption[]; precision_method: string }>;
  response_time: Section<Record<string, StageTiming | unknown>>;
  lead_time: Section<LeadTime>;
  confirmation: Section<Record<string, unknown>>;
  interdiction: Section<Record<string, unknown>>;
  evidence_ledger: Section<Record<string, unknown>>;
  generated_at: string;
}
export interface OpsItem { id: number; at: string; channel: string; severity: number; message: string; context: unknown }

// ---------- transport ----------
export class ApiError extends Error {
  readonly status: number;
  constructor(public problem: Problem, public retryAfter: number | null = null) {
    super(problem.detail ?? problem.title);
    this.status = problem.status;
  }
}

/** Every request carries the key. A 401 means the key is missing, revoked or wrong: drop it so the key gate shows. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const r = await fetch(API_URL + path, { ...init, headers: { ...authHeaders(), ...(init?.headers ?? {}) } });
  if (r.status === 401) setKey(null);
  return r;
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError({ type: "about:blank", title: "Network error", status: 0, detail: (e as Error)?.message ?? null });
}

async function readProblem(r: Response): Promise<ApiError> {
  let p: Problem | null = null;
  try { p = (await r.json()) as Problem; } catch { /* not problem+json */ }
  if (!p || typeof p !== "object" || typeof p.status !== "number") {
    p = { type: "about:blank", title: r.statusText || "Request failed", status: r.status, detail: null };
  }
  const ra = Number(r.headers.get("retry-after"));
  return new ApiError(p, Number.isFinite(ra) && ra > 0 ? ra : null);
}

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const json: Record<string, string> = typeof init?.body === "string" ? { "content-type": "application/json" } : {};
  let r: Response;
  try {
    r = await apiFetch(path, { ...init, headers: { accept: "application/json", ...json, ...((init?.headers ?? {}) as Record<string, string>) } });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new ApiError({ type: "about:blank", title: "Network error", status: 0, detail: `Could not reach the API at ${API_URL}.` });
  }
  if (!r.ok) throw await readProblem(r);
  if (r.status === 204) return undefined as T;
  const text = await r.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const get = <T,>(path: string, signal?: AbortSignal) => call<T>(path, { signal });
const post = <T,>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const api = {
  status: (signal?: AbortSignal) => get<SystemStatus>("/status", signal),
  health: (signal?: AbortSignal) => get<Health>("/health", signal),
  streamState: (signal?: AbortSignal) => get<StreamState>("/stream/state", signal),
  metrics: (signal?: AbortSignal) => get<Metrics>("/metrics", signal),
  metricsReport: (signal?: AbortSignal) => get<MetricsReport>("/metrics/report", signal),

  candidates: (p: { status?: string; min_score?: number; limit?: number; cursor?: string | null }, signal?: AbortSignal) =>
    get<Page<CandidateItem>>(`/candidates${qs(p)}`, signal),
  candidateCounts: (signal?: AbortSignal) => get<CandidateCounts>("/candidates/counts", signal),
  domain: (id: number, signal?: AbortSignal) => get<DomainDetail>(`/domains/${id}`, signal),
  reconfirm: (id: number) => post<Queued>(`/domains/${id}/confirm`),

  campaigns: (p: { min_size?: number; status?: string; limit?: number; cursor?: string | null } = {}, signal?: AbortSignal) =>
    get<Page<Campaign>>(`/campaigns${qs(p)}`, signal),
  campaign: (id: string, signal?: AbortSignal) => get<Campaign>(`/campaigns/${encodeURIComponent(id)}`, signal),
  graph: (id: string, signal?: AbortSignal) => get<CampaignGraph>(`/campaigns/${encodeURIComponent(id)}/graph`, signal),
  sweep: (id: string, signal?: AbortSignal) => get<Sweep>(`/campaigns/${encodeURIComponent(id)}/sweep`, signal),
  benchmark: (id: string, k: number, run: boolean, signal?: AbortSignal) =>
    get<Benchmark>(`/campaigns/${encodeURIComponent(id)}/benchmark${qs({ k, run })}`, signal),
  scaling: (signal?: AbortSignal) => get<Scaling | Unavailable>("/scaling", signal),
  interdict: (id: string, k: number, backend: Backend) => post<Plan>(`/campaigns/${encodeURIComponent(id)}/interdict`, { k, backend }),
  plan: (id: string, signal?: AbortSignal) => get<Plan>(`/plans/${id}`, signal),

  evidence: (id: string, signal?: AbortSignal) => get<Evidence>(`/evidence/${encodeURIComponent(id)}`, signal),
  verify: (id: string, tamper?: string | null, signal?: AbortSignal) =>
    get<VerifyResult>(`/evidence/${encodeURIComponent(id)}/verify${qs({ tamper: tamper ?? undefined })}`, signal),
  report: (id: string, signal?: AbortSignal) => get<Report>(`/evidence/${encodeURIComponent(id)}/report`, signal),
  /** Binary artifacts (the screenshot) need the key too, so they are fetched, not linked. */
  artifactBlobUrl: async (path: string) => {
    const r = await apiFetch(path);
    if (!r.ok) throw await readProblem(r);
    return URL.createObjectURL(await r.blob());
  },

  analyzeEmail: (raw: string) => post<EmailAnalysis>("/email/analyze", { raw, source: "analyst" }),
  analyzeEmailFile: async (f: File) => {
    const fd = new FormData();
    fd.append("eml", f);
    return call<EmailAnalysis>("/email/analyze", { method: "POST", body: fd });
  },
  emailAnalyses: (cursor?: string | null, signal?: AbortSignal) =>
    get<Page<EmailAnalysis>>(`/email/analyses${qs({ limit: 50, cursor })}`, signal),
  emailAnalysis: (id: string, signal?: AbortSignal) => get<EmailAnalysis>(`/email/analyses/${encodeURIComponent(id)}`, signal),

  ledgerStatus: (signal?: AbortSignal) => get<LedgerStatus>("/ledger/status", signal),
  ledgerEvents: (cursor?: string | null, signal?: AbortSignal) => get<Page<LedgerEvent>>(`/ledger/events${qs({ limit: 100, cursor })}`, signal),
  byKit: (kit: string, signal?: AbortSignal) => get<ByKit>(`/ledger/by-kit/${encodeURIComponent(kit)}`, signal),
  publish: (campaignId: string) => post<Queued>(`/ledger/publish/${encodeURIComponent(campaignId)}`),
  // The signing organisation is the key's organisation: there is no "as org" to choose.
  corroborate: (chainCampaignId: string) => post<Queued>(`/ledger/corroborate/${encodeURIComponent(chainCampaignId)}`),
  attest: (subject: string, verdict: "confirmed" | "dismissed" | "disputed") =>
    post<Queued>("/ledger/attest", { subject_hash: subject, verdict }),

  ops: (p: { channel?: string; limit?: number; cursor?: string | null }, signal?: AbortSignal) =>
    get<Page<OpsItem>>(`/ops/log${qs(p)}`, signal),
};
