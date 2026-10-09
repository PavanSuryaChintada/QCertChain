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
