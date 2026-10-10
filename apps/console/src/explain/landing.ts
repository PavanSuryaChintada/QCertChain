/** The public home page's words (owner request 2026-10-09: a SaaS page that pulls clients, without AI slop).
 *  Rules: describe only what runs today; anything else lives in ROADMAP and nowhere else; no typed measurements;
 *  nothing is ever described as sent automatically (CLAUDE.md §2.1). */

export interface Item { title: string; text: string }

export const HERO = {
  title: "Catch the phishing domain the moment its certificate is issued, before the first email is sent.",
  lead: "QCertChain watches the public Certificate Transparency logs for domains that imitate your brand, confirms the dangerous ones with evidence, maps the whole campaign behind them, and gives your security team the fewest takedowns that stop it.",
};

/** The life of a phishing domain. QCertChain acts at the first step; most defences act at the last two. */
export const LIFELINE: { step: string; note: string; ours?: boolean }[] = [
  { step: "Certificate logged", note: "QCertChain sees the domain here", ours: true },
  { step: "Phishing email sent", note: "The campaign starts" },
  { step: "First victim clicks", note: "Credentials are taken" },
  { step: "Someone reports it", note: "A person notices" },
  { step: "Blocklists catch up", note: "Most defences act here" },
];

export const OFFER: Item[] = [
  { title: "Early warning from certificate logs", text: "Every new certificate is checked against the brands you protect: look-alike names, homographs built from confusable characters, risky top-level domains. Suspicious names become candidates seconds after they are logged." },
  { title: "Confirmation with evidence, not a score", text: "A candidate is opened in an isolated headless browser. It is confirmed only when two independent strong signals are found, such as a cloned login form and passwords posted to a foreign site. The database itself rejects anything less." },
  { title: "Whole campaigns, not single links", text: "Confirmed domains are linked by the hosting, nameservers, registrars and phishing kit they share, so one operator's many domains show up as one campaign." },
  { title: "The fewest takedowns that stop it", text: "For each campaign the planner picks the few hosting providers, DNS providers or registrars whose action takes the most domains offline, and writes the abuse reports for your analysts." },
  { title: "Evidence that holds up", text: "Screenshot, page, certificate, DNS and WHOIS are fingerprinted, sealed into one signed Merkle root and anchored on a ledger, so anyone can check later that nothing was changed." },
  { title: "One organisation's detection protects the next", text: "Organisations share fingerprints of campaigns on the ledger, never their data. A phishing kit seen at one bank is recognised at the next." },
];

export const EVIDENCE: Item[] = [
  { title: "Open the page, never interact", text: "A headless Chromium opens the page from an isolated worker. It observes only: it fills in no form and clicks nothing." },
  { title: "Capture the artifacts", text: "The screenshot, the page source, the TLS certificate, the DNS records and the WHOIS record, with the abuse contact the registrar publishes." },
  { title: "Fingerprint each one", text: "Each artifact gets a SHA-256 hash. Change one byte of a file and its hash changes completely." },
  { title: "Seal the bundle", text: "The hashes are combined in pairs into one Merkle root, and the root is signed with the collector's Ed25519 key." },
  { title: "Anchor the root", text: "The root is written to a permissioned EVM ledger with the time it was recorded. Only the hash goes on chain, never the content." },
  { title: "Verify at any time", text: "Anyone holding the files can recompute the root and compare it with the ledger. The console's Verify button does exactly that, and Tamper shows the check failing." },
];

export interface Stage { name: string; what: string; why: string }
/** The pipeline, in three lanes. Shown on the home page and the Technical approach page. */
export const PIPELINE: { lane: string; stages: Stage[] }[] = [
  { lane: "Find", stages: [
    { name: "Certificate Transparency logs", what: "Every HTTPS certificate is published here before browsers trust it.", why: "The attacker has to announce the domain." },
    { name: "Ingest", what: "A self-hosted certstream server relays the logs.", why: "One reader, so each certificate is read once." },
    { name: "Redis stream", what: "Certificates wait here, in memory.", why: "It absorbs bursts, so a spike never reaches the database." },
    { name: "Triage workers", what: "Score every name against the brand list.", why: "Cheap and fast: they nominate, they never decide." },
  ] },
  { lane: "Prove", stages: [
    { name: "Page-check workers", what: "Headless browser, DNS, RDAP and network (ASN) lookups.", why: "A page takes seconds to check: workers keep the API fast, scale on their own and crash alone." },
    { name: "Evidence", what: "A SHA-256 hash per artifact, one Merkle root, an Ed25519 signature.", why: "Proof that the files were not changed." },
    { name: "Ledger", what: "The root anchored on a permissioned EVM chain.", why: "A timestamp nobody can rewrite later." },
  ] },
  { lane: "Act", stages: [
    { name: "Database", what: "PostgreSQL on Supabase, with row-level security per organisation.", why: "One organisation's data does not exist for another." },
    { name: "Campaigns and planner", what: "Shared infrastructure links domains; CP-SAT picks the takedowns.", why: "It stops the operation, not one link." },
    { name: "Consoles", what: "Your security team's console, and the super admin's panel.", why: "Each signs in with its own key." },
  ] },
];

export const AFTER: Item[] = [
  { title: "Evidence sealed and anchored", text: "The bundle's Merkle root is signed and written to the ledger with its time." },
  { title: "Campaign updated", text: "The domain joins its campaign through the infrastructure it shares." },
  { title: "Takedown plan", text: "The planner names the targets and whom to ask for each: hosting abuse, DNS abuse or registrar suspension." },
  { title: "Abuse reports written", text: "Each report carries the evidence and its ledger reference, addressed to the abuse contact the registrar or host publishes, the abuse@ mailbox that RFC 2142 standardises. Your analysts review and send it; it is never sent automatically, because one false positive would take a legitimate business offline." },
  { title: "Shared with the network", text: "The campaign's fingerprint goes on the ledger, so the next organisation that meets the same kit finds your report." },
];

export const SECURITY: Item[] = [
  { title: "Isolation in the database", text: "Row-level security filters every table by organisation. Another organisation's campaign is not forbidden to you: it does not exist for you." },
  { title: "Keys you control", text: "Keys are stored as hashes plus an encrypted copy, and can be rotated or revoked at once from the platform panel. Read-only keys can look and never change anything." },
  { title: "Nothing personal on chain", text: "The ledger holds hashes, counts and who reported what. No page content, no domain lists, no personal data." },
  { title: "Nothing happens on its own", text: "No part of the system submits a takedown, files a form or contacts a registrar." },
  { title: "Guarded administration", text: "The super admin's sign-in is throttled per client and overall, before any password is checked." },
];

/** Not built. Listed only here, and labelled as such. */
export const ROADMAP: Item[] = [
  { title: "Send after review", text: "Send a reviewed abuse report from the console with one click, evidence attached." },
  { title: "Alerts where your team works", text: "Webhooks to Slack, PagerDuty and your SIEM." },
  { title: "Browser blocklists", text: "Submit reviewed, confirmed domains to Google Safe Browsing and Microsoft SmartScreen." },
  { title: "Your brands, your rules", text: "Per-organisation brand keywords, legitimate domains and look-alike rules." },
  { title: "Single sign-on", text: "Sign in through your identity provider (SSO)." },
  { title: "A feed for your resolvers", text: "Confirmed domains as a blocklist feed for corporate DNS." },
];

export const POSITIONING =
  "Certificate Transparency monitoring itself is established practice. What QCertChain adds is campaign-level takedown planning and a shared evidence ledger, offered to many organisations on one platform.";

/** The hero's certificate-log illustration: what the system does with each new certificate. Fictitious names on the
 *  reserved .example domain; the panel is labelled as an illustration. */
export const LOG_ILLUSTRATION: { name: string; verdict: "passed" | "candidate" | "confirmed"; why: string }[] = [
  { name: "cdn.northwind-traders.example", verdict: "passed", why: "no brand imitated" },
  { name: "mail.fabrikam.example", verdict: "passed", why: "no brand imitated" },
  { name: "sbi-kyc-verify.example", verdict: "candidate", why: "brand token and a phishing keyword" },
  { name: "status.contoso.example", verdict: "passed", why: "no brand imitated" },
  { name: "icici-netbanking-login.example", verdict: "confirmed", why: "cloned login form, passwords sent to a foreign site" },
];

/** "How long each step takes" (owner decision 2026-10-10). The words only: every number comes from measured.ts,
 *  generated from reports/metrics.json. A step that was not measured is not shown. */
export const TIMING = {
  title: "How long each step takes",
  intro: "Measured on our own runs. Each step shows its median time, the time almost every run finished within, and how many were measured. Steps we have not measured are not shown.",
};
export const TIMING_STEPS: Record<"relay" | "triage" | "candidate" | "verdict" | "plan" | "verify", Item> = {
  relay: { title: "The public certificate relay", text: "The open certificate-stream service hands each logged certificate to our ingest. This wait is outside our code." },
  triage: { title: "Triage scores each name", text: "Brand tokens, look-alikes built from confusable characters, phishing keywords and risky top-level domains, for every name in every certificate." },
  candidate: { title: "Candidate stored", text: "From our receipt of the certificate to a candidate row in the database, queued for a page check." },
  verdict: { title: "First verdict on the page", text: "A page-check worker opens the candidate in an isolated browser and records what it found: confirmed, dismissed, unreachable or still a candidate." },
  plan: { title: "Takedown plan", text: "CP-SAT picks the hosting, DNS or registrar targets that take the most domains offline, requested through the API." },
  verify: { title: "Evidence verified", text: "Recompute a bundle's Merkle root, check its Ed25519 signature and compare it with the ledger." },
};

/** Why the approach differs, section by section. A contrast of method, never a speed race with blocklists: our own
 *  lead-time measurement did not show us ahead of them (reports/metrics.json, lead_time). */
export const CONTRASTS: Record<"offer" | "timing" | "evidence" | "pipeline" | "after" | "security", { usual: string; ours: string }> = {
  offer: {
    usual: "A link is blocked after someone has reported it, one URL at a time, often on a model's score alone.",
    ours: "A look-alike domain becomes a candidate from its own certificate, with no report needed. It is confirmed only on evidence, and handled together with its whole campaign.",
  },
  timing: {
    usual: "Speed is quoted as a target or a promise.",
    ours: "Every time on this page was measured on our own runs, with how many were measured. What we have not measured is left out.",
  },
  evidence: {
    usual: "Screenshots and notes sit in a ticket, and nobody outside the team can check they were not changed.",
    ours: "Each artifact is hashed into one signed Merkle root anchored on a ledger, so anyone holding the files can check them at any time.",
  },
  pipeline: {
    usual: "One service does everything, so a burst of certificates or one slow page holds up the rest.",
    ours: "A stream absorbs bursts, workers check pages away from the API, and each part can fail and restart on its own.",
  },
  after: {
    usual: "Each domain is reported on its own, one abuse request per domain.",
    ours: "The planner names the few hosting, DNS or registrar targets that take the most domains offline at once, and writes each report for an analyst to review and send.",
  },
  security: {
    usual: "Customers are kept apart by filters in application code, where one missed filter is a leak.",
    ours: "Row-level security in the database: another organisation's data does not exist for your key, whatever the code asks for.",
  },
};
