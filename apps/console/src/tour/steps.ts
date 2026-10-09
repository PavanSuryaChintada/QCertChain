import { FRAMING } from "../explain/framing";
import type { TermId } from "../explain/glossary";
import type { Campaign, CampaignGraph, DomainDetail, Page, Sweep } from "../lib/api";
import { fmtInt } from "../lib/format";

/** Live values a step can quote. Read once when the tour starts and stored formatted, so steps type no numbers. */
export interface TourCtx {
  campaignId?: string;
  domainCount?: string;
  kitHash?: string;
  bundleId?: string;
  coverage?: { k: string; killed: string; total: string };
}

export interface TourStep {
  id: string;
  /** where the step happens; a step whose item is missing falls back to the list page */
  route: (c: TourCtx) => string;
  /** the element to highlight: the page marks it data-tour="<target>" */
  target: string;
  title: string;
  body: (c: TourCtx) => string;
  /** what the card says while the element is not on the page: still loading, or no data yet */
  missing: (c: TourCtx) => string;
  /** the words on this page the card defines (from the glossary) */
  terms: TermId[];
}

/** The largest takedown budget the tour quotes (the demo's slider value). */
export const TOUR_K = 5;

const campaign = (c: TourCtx) => (c.campaignId ? `/campaigns/${encodeURIComponent(c.campaignId)}` : "/campaigns");
const bundle = (c: TourCtx) => (c.bundleId ? `/evidence/${encodeURIComponent(c.bundleId)}` : "/evidence");
// The queue opens on Confirmed (owner decision 2026-10-09); the arriving-certificates steps ask for All.
const allRows = () => "/queue?status=all";

export const STEPS: TourStep[] = [
  {
    id: "pipeline", route: () => "/", target: "architecture", title: "The pipeline",
    body: () => "Every HTTPS certificate is published to public Certificate Transparency logs before browsers trust it. QCertChain listens to those logs and moves each lookalike domain through triage, confirmation, campaign clustering, interdiction, evidence and the ledger. Each square is that stage's live status.",
    missing: () => "The pipeline diagram appears here once the page has loaded.",
    terms: ["ct", "triage", "statusSquare"],
  },
  {
    id: "queue", route: allRows, target: "queue", title: "Certificates arriving",
    body: () => "Domains that triage nominates appear here as their certificates are logged. Triage is cheap and errs towards catching too many: it nominates, it never decides.",
    missing: () => "The queue is loading, or empty right now; it fills as certificates arrive.",
    terms: ["triage", "candidate", "source"],
  },
  {
    id: "score", route: allRows, target: "score", title: "Why a domain was nominated",
    body: () => "Hover a score to see its parts: the brand it imitates, keywords, the top-level domain and confusable characters. A candidate is suspicious, not verified, and is never shown in red.",
    missing: () => "Scores appear on each row once the queue has loaded its candidates.",
    terms: ["score", "brandToken", "homograph", "tld"],
  },
  {
    id: "confirmed", route: () => "/queue?status=confirmed", target: "status-filter", title: "Confirmation needs evidence",
    body: () => "A domain is confirmed only after its page is fetched and two independent strong signals are found, such as a cloned login form and credentials posted to a foreign site. The database rejects a confirmation with fewer.",
    missing: () => "The status filter is at the top of the queue.",
    terms: ["confirmed", "strongSignal", "independent"],
  },
  {
    id: "graph", route: campaign, target: "graph", title: "One operator, many domains",
    body: (c) => `${c.domainCount ? `This campaign's ${c.domainCount} domains are` : "A campaign's domains are"} linked by the hosting, nameservers, registrars and phishing kit they share. Blocking one domain leaves the rest running.`,
    missing: (c) => (c.campaignId ? "The campaign graph is still loading; it is highlighted when it arrives." : "Your organisation has no campaign yet. Campaigns appear once confirmed domains share infrastructure."),
    terms: ["campaign", "infraNode", "kitHash"],
  },
  {
    id: "budget", route: campaign, target: "budget", title: "The fewest takedowns",
    body: (c) => `${c.coverage ? `With a budget of ${c.coverage.k} takedowns, the best plan covers ${c.coverage.killed} of ${c.coverage.total} domains. ` : ""}Choosing which few targets cover the most domains is maximum coverage, an NP-hard problem, solved here with CP-SAT. Drag the budget to see the plan change.`,
    missing: (c) => (c.campaignId ? "The campaign is still loading; the planner is highlighted when it arrives." : "The takedown planner appears on a campaign's page."),
    terms: ["takedown", "budget", "coverage", "reachable", "npHard"],
  },
  {
    id: "solvers", route: campaign, target: "solvers", title: "Solvers compared",
    body: () => `${FRAMING} Every solver's result is shown, losses included.`,
    missing: (c) => (c.campaignId ? "The campaign is still loading; the solver table is highlighted when it arrives." : "The solver comparison appears on a campaign's page."),
    terms: ["cpsat", "greedy", "annealing", "qubo", "gap"],
  },
  {
    id: "report", route: bundle, target: "report", title: "Generated, never sent",
    body: () => "For each target the system writes an evidence-backed abuse request to the hosting provider, DNS provider or registrar. It is never submitted: one false positive would take a legitimate business offline.",
    missing: (c) => (c.bundleId ? "The evidence bundle is still loading; its report is highlighted when it arrives." : "Abuse reports belong to evidence bundles, which exist only for confirmed domains."),
    terms: ["abuseReport", "route", "takedown"],
  },
  {
    id: "evidence", route: bundle, target: "verify", title: "Tamper-evident evidence",
    body: () => "The screenshot, page, certificate, DNS and WHOIS records are hashed into one Merkle root and signed with Ed25519. Verify recomputes the root and compares it with the copy anchored on the chain. Only the hash is on the chain, never the content.",
    missing: (c) => (c.bundleId ? "The evidence bundle is still loading; Verify is highlighted when it arrives." : "Verification appears on an evidence bundle's page."),
    terms: ["artifact", "fileHash", "merkleRoot", "signature", "anchored"],
  },
  {
    id: "ledger", route: (c) => (c.kitHash ? `/ledger?kit=${encodeURIComponent(c.kitHash)}` : "/ledger"), target: "kit-lookup",
    title: "One organisation protects the next",
    body: () => "Looking up a phishing kit's hash shows every organisation that published a campaign built with it: counts, confidence, reporter and time. Domain names, addresses and page content are never shared.",
    missing: () => "The kit-hash lookup is at the top of the ledger page.",
    terms: ["kitHash", "iocRoot", "corroborate", "dispute", "transaction", "confidence"],
  },
  {
    id: "metrics", route: () => "/metrics", target: "metrics", title: "Measured, not asserted",
    body: () => "Every figure on this page comes from a measurement script, and what could not be measured says so. That is the end of the tour.",
    missing: () => "The metrics appear once the report has loaded.",
    terms: ["precision", "recall", "baseRate", "leadTime"],
  },
];

/** The GET-only reads the tour needs; injected so tests can stub them. */
export interface TourReads {
  campaigns: (p: { limit?: number }, signal?: AbortSignal) => Promise<Page<Campaign>>;
  graph: (id: string, signal?: AbortSignal) => Promise<CampaignGraph>;
  sweep: (id: string, signal?: AbortSignal) => Promise<Sweep>;
  domain: (id: number, signal?: AbortSignal) => Promise<DomainDetail>;
}

/** The organisation's largest campaign, its coverage within the tour budget, one evidence bundle and its kit hash. */
export async function resolveCtx(a: TourReads, signal?: AbortSignal): Promise<TourCtx> {
  const ctx: TourCtx = {};
  try {
    const page = await a.campaigns({ limit: 50 }, signal);
    const best = [...page.items].sort((x, y) => y.domain_count - x.domain_count)[0];
    if (!best) return ctx;
    ctx.campaignId = best.id;
    ctx.domainCount = fmtInt(best.domain_count);
    if (best.kit_hash) ctx.kitHash = best.kit_hash;
    const [graph, sweep] = await Promise.all([
      a.graph(best.id, signal).catch(() => null),
      a.sweep(best.id, signal).catch(() => null),
    ]);
    const point = sweep?.points.filter((p) => p.k <= TOUR_K).sort((x, y) => y.k - x.k)[0];
    if (point) ctx.coverage = { k: String(point.k), killed: fmtInt(point.domains_killed), total: fmtInt(point.domains_total) };
    for (const d of (graph?.domains ?? []).filter((x) => x[2] === "confirmed").slice(0, 5)) {
      const detail = await a.domain(d[0], signal).catch(() => null);
      if (detail?.evidence_bundle_id) { ctx.bundleId = detail.evidence_bundle_id; break; }
    }
  } catch {
    /* the tour still runs; steps without live values say so */
  }
  return ctx;
}
