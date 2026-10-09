import { FRAMING } from "../explain/framing";
import type { TermId } from "../explain/glossary";

/** What the ? panel says about one page. Plain words; no measured numbers (spec §8b). */
export interface HelpEntry {
  title: string;
  what: string;
  read: { label: string; text: string }[];
  data: string;
  notClaimed: string;
  /** the words on this page, defined in the glossary */
  terms?: TermId[];
}

const HELP_ENTRIES = {
  "/": {
    title: "Architecture",
    terms: ["ct", "statusSquare", "triage"],
    what: "The whole pipeline on one diagram, from the certificate stream to the console, with each stage's live status.",
    read: [
      { label: "Boxes", text: "Dashed grey boxes are inputs, white boxes are pipeline stages, and boxes with a thick left edge store records. Click a box to open its page." },
      { label: "Status squares", text: "Filled means ok, half-filled degraded, crossed and grey failed, hollow no report yet. Failed is grey on purpose: a failing system is not a threat." },
      { label: "Figures on the arrows", text: "Certificates per second entering triage, candidates per hour leaving it, and confirmations per hour leaving confirmation." },
      { label: "The three panels", text: "Three positions the database itself enforces: nothing is ever sent, two strong signals are needed to confirm, and only hashes go on chain." },
    ],
    data: "One batched status request every five seconds, answered by the API from the database, Redis and the chain.",
    notClaimed: "A filled square means the stage reported in and is keeping up. It does not mean anything malicious was found.",
  },
  "/queue": {
    title: "Live queue",
    terms: ["candidate", "confirmed", "score", "brandToken", "homograph", "tld", "source"],
    what: "Every domain triage has nominated, from the certificate stream and from links in analysed emails. It opens on confirmed domains; Candidates and All show what triage nominated, newest first.",
    read: [
      { label: "Status filter", text: "All, candidates, confirmed or dismissed, with a count on each. A candidate is suspicious, not verified." },
      { label: "Triage score", text: "Hover it for the breakdown: the brand it imitates, keywords, the top-level domain and confusable characters. Above the threshold, a name becomes a candidate." },
      { label: "Rows", text: "Click a row, or press Enter on it, to open the domain: why triage nominated it, what enrichment found, and the confirmation signals." },
      { label: "New rows", text: "While the pointer is over the table, new rows wait behind a bar so the list does not move under you. Click the bar to show them." },
    ],
    data: "Candidates from the certificate stream and from links in analysed emails, refreshed every five seconds.",
    notClaimed: "A candidate is not an accusation. Only a confirmed domain, with two independent strong signals found on its fetched page, is treated as phishing, and candidates are never shown in red.",
  },
  "/campaigns": {
    title: "Campaigns",
    terms: ["campaign", "confidence", "infraNode"],
    what: "Confirmed domains grouped into campaigns by the infrastructure they share.",
    read: [
      { label: "Each row", text: "One campaign: how many domains and infrastructure nodes it has, its confidence, and when it was first seen. Open it to see the graph and plan the takedowns." },
      { label: "Confidence", text: "How sure the clustering is that these domains belong to one operation." },
    ],
    data: "Your organisation's campaigns only. Other organisations' campaigns do not exist for you.",
    notClaimed: "A campaign groups confirmed domains by shared infrastructure. It does not name the attacker.",
  },
  "/campaigns/:id": {
    title: "Campaign",
    terms: ["campaign", "infraNode", "kitHash", "takedown", "budget", "coverage", "reachable", "npHard", "cpsat", "greedy", "annealing", "qubo", "gap"],
    what: "One campaign: the graph of its domains and shared infrastructure, the takedown plan for a budget, and the solvers compared.",
    read: [
      { label: "Graph", text: "Domains around the infrastructure they share. Filled squares are takedown targets (hosting address, nameserver, registrar). Dashed circles are evidence only, such as kit and favicon hashes: nobody can take down a hash." },
      { label: "Takedown budget", text: "Choose how many takedowns you can ask for. Targets light up and the domains they cover go dark. The coverage curve flattens towards the reachable line, because some domains sit only on infrastructure no takedown reaches." },
      { label: "Why this plan", text: "Each target, whom to ask (hosting abuse, DNS abuse or registrar suspension), and the domains it covers." },
      { label: "Solvers", text: "The same problem solved several ways, with domains covered, targets chosen, time taken and the gap to CP-SAT. Run again solves it live." },
      { label: "Solver formulation", text: "The QUBO the problem becomes: its variables, the qubits and circuit depth it needs, and what the reduction removed first." },
    ],
    data: "The campaign graph, the coverage for each budget and the solver benchmark, computed by the API for your organisation's campaign.",
    notClaimed: `${FRAMING} No takedown request is ever submitted.`,
  },
  "/evidence": {
    title: "Evidence",
    terms: ["artifact", "merkleRoot"],
    what: "Where evidence bundles open. A bundle is built for each confirmed domain.",
    read: [{ label: "Bundle id", text: "Enter a bundle id, or open a bundle from a confirmed domain's detail in the live queue." }],
    data: "Your organisation's bundles only.",
    notClaimed: "Only hashes are anchored on the ledger, never the evidence itself.",
  },
  "/evidence/:id": {
    title: "Evidence bundle",
    terms: ["artifact", "fileHash", "merkleRoot", "signature", "anchored", "abuseReport", "route"],
    what: "Everything kept for one confirmed domain, how it is sealed against tampering, and the abuse report generated from it.",
    read: [
      { label: "Bundle contents", text: "Each artifact (screenshot, page, certificate, DNS and WHOIS records) with its SHA-256 hash and size." },
      { label: "Merkle tree", text: "The artifact hashes combined in pairs up to a single root, which is signed with Ed25519." },
      { label: "Verify", text: "Recomputes the root from the stored bytes, checks the signature and compares the root with the copy anchored on the chain. Tamper flips one byte in memory to show the check failing; the stored evidence is never touched. Restore undoes it." },
      { label: "Attestations", text: "Which organisations confirmed or disputed this evidence on the chain." },
      { label: "Abuse report", text: "The request generated for the hosting provider, DNS provider or registrar, marked not sent." },
    ],
    data: "The bundle from your organisation's evidence store, and its anchor transaction on the chain.",
    notClaimed: "The report is generated for review and never sent. A bundle missing an artifact, such as a screenshot, is marked partial.",
  },
  "/email": {
    title: "Email analyzer",
    terms: ["strongSignal", "candidate"],
    what: "Paste the headers of a suspicious email, or the whole message, to see whether it is spoofed and where its links lead.",
    read: [
      { label: "Parsed headers", text: "Sender, return path, the relays it passed through, and the SPF, DKIM and DMARC results with pass or fail." },
      { label: "Signals", text: "What the headers reveal, by strength. The rule is the same as for domains: an email is malicious only with two strong signals." },
      { label: "Extracted link domains", text: "Each link's domain with its triage score. A new one becomes a candidate in the live queue, and when it is confirmed this email is re-scored automatically." },
      { label: "Recent analyses", text: "Your organisation's earlier analyses." },
    ],
    data: "Only what you paste or drop here. Nothing connects to a mailbox; message bodies are read for links and are not stored.",
    notClaimed: "Suspicious is not malicious: with fewer than two strong signals the verdict stays suspicious.",
  },
  "/ledger": {
    title: "Ledger",
    terms: ["kitHash", "iocRoot", "corroborate", "dispute", "transaction", "confidence", "anchored"],
    what: "The shared chain: what your organisation anchored and published, and lookups across organisations by kit hash.",
    read: [
      { label: "Kit-hash lookup", text: "Paste the hash of a phishing kit seen on one of your domains. The result lists every organisation that published a campaign built with that kit: domain count, confidence, reporter and time. Corroborate or Dispute records your organisation's answer on the chain, signed with its own key." },
      { label: "Anchored records", text: "Everything your organisation wrote to the chain, with transaction hashes." },
    ],
    data: "The permissioned demo chain, read through the API. Writes wait in a queue while the chain is unreachable.",
    notClaimed: "Only hashes, counts and who reported them are shared. Domain names, addresses and page content never leave the organisation.",
  },
  "/metrics": {
    title: "Metrics",
    terms: ["precision", "recall", "baseRate", "leadTime"],
    what: "How the system measures up: triage precision and recall, the threshold sweep, lead time, response time per stage, and the interdiction, evidence and ledger figures.",
    read: [
      { label: "Triage precision", text: "Precision at a realistic base rate, worked out from the measured false-positive rate and recall, not from a balanced test set." },
      { label: "Threshold sweep", text: "Recall, false positives and candidates per hour at each threshold. A lower threshold costs page fetches, not accusations." },
      { label: "Lead time", text: "How much earlier a domain appears in Certificate Transparency than in a public phishing feed, or why it has not been measured yet." },
      { label: "Per-stage response time", text: "From certificate seen to candidate, confirmed, campaign, plan, bundle and anchor." },
    ],
    data: "Measurement scripts write one metrics file; this page and the written report are both rendered from it.",
    notClaimed: "A figure that could not be measured says so instead of showing an estimate.",
  },
  "/health": {
    title: "System health",
    what: "Whether each component is up, how fast the API answers, and where everything runs.",
    read: [
      { label: "Components", text: "Each stage's status, with the reason when it is degraded or failed." },
      { label: "Endpoint latency", text: "Median and slow-tail response time for each API endpoint over the last few minutes." },
      { label: "Queues and regions", text: "Queue depths, the database round trip, and the regions of the API and the database." },
    ],
    data: "The same status request as the top bar, every five seconds.",
    notClaimed: "Failed is grey: a failing system is not a threat.",
  },
  "/ops": {
    title: "Ops log",
    what: "Every degradation the system hits, written as it happens.",
    read: [
      { label: "Channel", text: "Show entries from one component only." },
      { label: "Entries", text: "Newest first, with severity and context." },
    ],
    data: "An append-only log in the database.",
    notClaimed: "An entry is an operational event, not a security finding.",
  },
  "/technical": {
    title: "Technical approach",
    terms: ["ct", "triage", "strongSignal", "merkleRoot", "iocRoot", "kitHash"],
    what: "How QCertChain works and why it is built this way, on one page.",
    read: [
      { label: "Sections", text: "The problem, the five stages, choosing the takedowns, evidence, the shared ledger, organisations, how it is served, and what it does not do." },
      { label: "Diagram", text: "The same pipeline diagram as the Architecture page, without live status." },
    ],
    data: "A written description. Live figures are on the Metrics page.",
    notClaimed: "It describes the design. Measured results are only on the Metrics page and in the report.",
  },
  "/tour": {
    title: "How it works",
    what: "A guided tour of the real console: each step opens a page and highlights the part that matters.",
    read: [
      { label: "Controls", text: "Next step and Back move through the tour. The arrow keys do the same, and Esc ends it." },
      { label: "Live data", text: "Each step uses your organisation's real data. The tour only highlights; it changes nothing." },
    ],
    data: "Your organisation's campaigns, evidence and ledger, read with your key when the tour starts.",
    notClaimed: "Figures in the tour are read live when it starts; they are not fixed claims.",
  },
  superadmin: {
    title: "Platform administration",
    what: "The super admin's panel: every organisation on the platform, by category, and their keys. It shows no organisation's data.",
    read: [
      { label: "New organisation", text: "A name and a category. The organisation gets a full key, shared privately, and a read-only key, shown on the sign-in page." },
      { label: "Open console", text: "Signs in as that organisation with its full key, to see exactly what it sees." },
      { label: "Rotate", text: "Revokes a key and issues a new one at once; the old key stops working within half a minute." },
      { label: "Deactivate", text: "Its keys stop working and it leaves the sign-in page. The pipeline organisation stays active." },
    ],
    data: "The platform's own records: organisations, categories and keys. Keys are stored as hashes plus an encrypted copy.",
    notClaimed: "A new organisation sees the shared certificate feed now; its own sector feed and seeded campaign come with the next update.",
  },
  signin: {
    title: "Home",
    what: "What QCertChain does for a security team, how it collects evidence and how it is built, with every organisation's read-only key on the right.",
    read: [
      { label: "Try the console", text: "Every organisation by category, each with a read-only key: one click opens its console to look, never to change anything." },
      { label: "Sign in", text: "For the platform's super admin: email and password. It creates organisations and manages their keys." },
      { label: "Request access", text: "A demo form: sign-up is by invitation during the pilot, and the form sends and stores nothing." },
      { label: "On the roadmap", text: "What is not built yet is listed there and only there." },
      { label: "Technical approach", text: "Open without a key: how the system works and why it is built this way." },
      { label: "How it works", text: "A guided tour of the live console. Sign in first; the tour starts on its own." },
    ],
    data: "The API checks each key against its hash; an encrypted copy lets the platform show read-only keys here.",
    notClaimed: "Signing in with the demo key never changes any data.",
  },
} satisfies Record<string, HelpEntry>;

export type HelpKey = keyof typeof HELP_ENTRIES;
export const HELP: Record<HelpKey, HelpEntry> = HELP_ENTRIES;

/** The help entry for a pathname: `/`, `/section`, or `/section/:id` for any detail page. */
export function helpKeyFor(pathname: string): HelpKey | null {
  const parts = pathname.split("/").filter(Boolean);
  const key = parts.length === 0 ? "/" : parts.length === 1 ? `/${parts[0]}` : `/${parts[0]}/:id`;
  return key in HELP ? (key as HelpKey) : null;
}
