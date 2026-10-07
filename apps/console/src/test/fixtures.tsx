import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import type { CampaignGraph, Evidence, MetricsReport, Sweep, VerifyResult } from "../lib/api";
import { ToastProvider } from "../components/Toast";

export function renderWith(ui: ReactElement, { route = "/", qc }: { route?: string; qc?: QueryClient } = {}) {
  const client = qc ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc: client, ...render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>{ui}</ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  ) };
}

export const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

export const GRAPH: CampaignGraph = {
  campaign_id: "c1", n_targetable: 3, search_space_log2: 23, built_at: "2026-10-07T00:00:00Z",
  domains: [[101, "a-bank.top", "confirmed"], [102, "b-bank.top", "confirmed"], [103, "c-bank.top", "candidate"],
            [104, "d-bank.top", "confirmed"], [105, "e-bank.top", "confirmed"], [106, "f-bank.top", "confirmed"]],
  nodes: [[1, "ip", "203.0.113.10", 3, true], [2, "ip", "203.0.113.20", 3, true], [3, "nameserver", "ns1.kit-dns.example", 4, true],
          [4, "asn", "64496", 6, false], [5, "kit_hash", "c9c69097bd87d4386220b7aa", 6, false]],
  edges: [[101, 1, 1], [102, 1, 1], [103, 1, 1], [104, 2, 1], [105, 2, 1], [106, 2, 1],
          [101, 3, 1], [102, 3, 1], [104, 3, 1], [105, 3, 1],
          [101, 4, 1], [102, 4, 1], [103, 4, 1], [104, 4, 1], [105, 4, 1], [106, 4, 1], [101, 5, 1]],
  targets: [],
};

export const SWEEP: Sweep = {
  campaign_id: "c1", n_targetable: 3, search_space_log2: 23, cached: true,
  points: [
    { k: 1, backend: "cpsat", domains_killed: 4, domains_total: 6, coverage_pct: 66.7, solve_ms: 12, valid: true, notes: [],
      targets: [{ node_id: 3, kind: "nameserver", value: "ns1.kit-dns.example", kills: 4, route: "dns" }], killed_ids: [101, 102, 104, 105] },
    { k: 2, backend: "cpsat", domains_killed: 6, domains_total: 6, coverage_pct: 100, solve_ms: 31, valid: true, notes: [],
      targets: [{ node_id: 1, kind: "ip", value: "203.0.113.10", kills: 3, route: "hosting" },
                { node_id: 2, kind: "ip", value: "203.0.113.20", kills: 3, route: "hosting" }], killed_ids: [101, 102, 103, 104, 105, 106] },
    { k: 3, backend: "cpsat", domains_killed: 6, domains_total: 6, coverage_pct: 100, solve_ms: 405, valid: true, notes: [],
      targets: [{ node_id: 1, kind: "ip", value: "203.0.113.10", kills: 3, route: "hosting" },
                { node_id: 2, kind: "ip", value: "203.0.113.20", kills: 3, route: "hosting" },
                { node_id: 3, kind: "nameserver", value: "ns1.kit-dns.example", kills: 0, route: "registrar" }], killed_ids: [101, 102, 103, 104, 105, 106] },
  ],
};

const H = (c: string) => c.repeat(64);
export const BUNDLE: Evidence = {
  id: "b1", domain_id: 1, campaign_id: null, bundle_root: "c8e1a4f0" + "0".repeat(56), signature: "sig".padEnd(128, "a"),
  collector_pk: "ed25519pk".padEnd(64, "b"), partial: false, created_at: "2026-10-06T00:00:00Z", anchored_tx: null, anchored_at: null,
  artifacts: [
    { name: "dom.html", sha256: "a4f2c9" + "0".repeat(58), size_bytes: 31204, url: "/evidence/b1/artifacts/dom.html" },
    { name: "screenshot.png", sha256: H("3"), size_bytes: 867234, url: "/x" },
  ],
};

const TREE = { leaves: [{ name: "dom.html", leaf: H("1") }, { name: "screenshot.png", leaf: H("2") }], levels: [[H("1"), H("2")], [H("9")]] };
export const VERIFY_OK: VerifyResult = {
  valid: true, root_matches: true, signature_valid: true, expected_root: BUNDLE.bundle_root, computed_root: BUNDLE.bundle_root,
  failures: [], anchor: { status: "matches", tx: "0x" + "d".repeat(64) }, tree: TREE,
  attestations: { "Bank One SOC": "confirmed", "Bank Two SOC": "disputed" }, disputed: true, simulated_tamper: null,
};
export const VERIFY_TAMPERED: VerifyResult = {
  ...VERIFY_OK, valid: false, root_matches: false, computed_root: "5e88b1" + "0".repeat(58), simulated_tamper: "dom.html",
  anchor: { status: "mismatch", tx: "0x" + "d".repeat(64) },
  failures: [{ artifact: "dom.html", expected: "a4f2c9" + "0".repeat(58), found: "a4f2c8" + "0".repeat(57) + "7", reason: "hash_mismatch" }],
};

export const REPORT: MetricsReport = {
  triage_rules: {
    threshold: 0.35,
    precision_at_1_in_1000_base_rate: { value: 0.0024, method: "Bayes from measured FP rate and recall" },
    hard_negative_fp_rate: { value: 0.031, n: 2000 }, false_positive_rate: { value: 0.0004, n: 100000 },
    recall_on_phishing_naming_our_40_brands: { value: 0.91, n: 412 }, latency_us_per_name: { p50: 38, p95: 71, p99: 120 },
  },
  triage_threshold_options: { precision_method: "Bayes at 1:1000", options: [0.2, 0.35, 0.5, 0.65, 0.8].map((t, i) => ({
    threshold: t, precision_at_1_in_1000: 0.001 + i * 0.001, recall_our_brands: 0.95 - i * 0.1, recall_global_feeds: 0.6 - i * 0.1,
    fp_rate_random_tranco: 0.001, hard_negative_fp_rate: 0.03, candidates_per_hour_live: 900 - i * 150 })) },
  response_time: { triage: { p50_ms: 0.04, p95_ms: 0.07 }, confirm: { p50_ms: 8200, p95_ms: 17400 } },
  lead_time: { unavailable: "OpenPhish feed not yet joined against CT timestamps" },
  confirmation: { unavailable: "no labelled set" }, interdiction: { solve_ms_p50: 405 }, evidence_ledger: { anchored: 12 },
  generated_at: "2026-10-07T00:00:00Z",
};
