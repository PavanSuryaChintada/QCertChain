import { FRAMING } from "./framing";

/** `live`: a button to the console page where this part can be seen working (owner request 2026-10-09). */
export interface TechSection { id: string; title: string; paragraphs: string[]; live?: { label: string; to: string } }

/** The Technical approach page, in reading order. Describes what exists; measured figures live on the Metrics page. */
export const TECHNICAL: TechSection[] = [
  {
    id: "problem",
    title: "The problem",
    paragraphs: [
      "A phishing link is usually blocked only after someone has received it, clicked it and reported it. By then the damage is done, and the attacker has many more domains ready.",
      "Every HTTPS certificate is published to public Certificate Transparency logs, because browsers reject certificates that are not logged. An attacker who wants a padlock on a phishing page has to announce the domain first. QCertChain listens to those logs and sees the domain before the first email is sent.",
      "Hundreds of thousands of certificates are logged every minute and only a tiny share are phishing. At that base rate even a very accurate classifier flags far more legitimate domains than malicious ones, so a classifier alone cannot decide. The design is a cheap filter that nominates, followed by a hard evidence gate that decides.",
    ],
  },
  {
    id: "stages",
    title: "The five stages",
    live: { label: "See the live queue", to: "/queue?status=all" },
    paragraphs: [
      "Ingest: a self-hosted certstream server relays the Certificate Transparency logs, and each certificate's names enter a Redis stream.",
      "Triage: every name is scored against the brand list (brand tokens, keywords, the top-level domain, confusable characters and homographs). It produces candidates, never verdicts.",
      "Confirmation: the candidate's page is fetched in a headless browser and inspected. A domain is confirmed only when two independent strong signals are found, such as a cloned login form or credentials posted to a foreign site, from different detectors and sharing no artifact. The database itself rejects a confirmation with fewer.",
      "Clustering: confirmed domains are linked by shared hosting addresses, nameservers, registrars, certificate patterns and the phishing kit's page structure and favicon, which turns single domains into campaigns.",
      "Interdiction: for each campaign the system works out which few takedowns cover the most domains within a budget, and writes the abuse requests that would carry them out.",
    ],
  },
  {
    id: "selection",
    title: "Choosing the takedowns",
    live: { label: "See a takedown plan", to: "/campaigns" },
    paragraphs: [
      "Only a hosting provider, a DNS provider or a registrar can act, so only hosting addresses, nameservers and registrars are targets. Hashes and certificates are evidence, not targets.",
      "Picking the few targets that together cover the most domains is the maximum coverage problem, which is NP-hard. The planner also reports which domains no budget can reach.",
      FRAMING,
      "Greedy search, simulated annealing and exhaustive search run beside it as benchmarks, and every result is shown, losses included.",
    ],
  },
  {
    id: "evidence",
    title: "Evidence and chain of custody",
    live: { label: "See confirmed domains", to: "/queue?status=confirmed" },
    paragraphs: [
      "For a confirmed domain the system keeps the screenshot, the page, the certificate, and the DNS and WHOIS records. Each is hashed with SHA-256, the hashes form a Merkle tree, and the root is signed with Ed25519.",
      "Changing a single byte of any artifact changes the root, so the signature and the anchored copy no longer match. The Verify button on every bundle checks exactly that.",
    ],
  },
  {
    id: "ledger",
    title: "The shared ledger",
    live: { label: "Open the ledger", to: "/ledger" },
    paragraphs: [
      "Organisations share fingerprints, never data. A permissioned chain holds Merkle roots, kit hashes, counts, confidence and who reported what. Pages, screenshots, domain names and personal data never go on chain.",
      "It exists for four reasons: one organisation's detection reaches the next immediately; the evidence has a tamper-proof chain of custody; nobody can deny what they reported or sign as someone else; and there is no central store of everyone's data to attack.",
    ],
  },
  {
    id: "platform",
    title: "One platform, many organisations",
    paragraphs: [
      "Each organisation signs in with its own key, and the database's row-level security filters every table by organisation. Another organisation's campaign or bundle is not forbidden but absent: the API answers 404.",
      "The public certificate feed is shared by everyone. Campaigns, evidence, plans and email analyses belong to the organisation that produced them.",
    ],
  },
  {
    id: "serving",
    title: "How it is served",
    paragraphs: [
      "The API, its workers, Redis, the certstream server and the demo chain run on one machine. The database is Supabase PostgreSQL in Singapore.",
      "The public console is a static site on Vercel, and it reaches the API through a Cloudflare tunnel.",
    ],
  },
  {
    id: "limits",
    title: "What it does not do",
    live: { label: "See the metrics", to: "/metrics" },
    paragraphs: [
      "Phishing served over plain HTTP has no certificate and is invisible here. A wildcard certificate hides the phishing subdomain behind the wildcard.",
      "On live data the pipeline currently ends at the confirmation gate: modern phishing kits are JavaScript applications, so the original strong signals rarely fire. The Metrics page shows how many live domains have been confirmed and why. Campaigns, interdiction and evidence are demonstrated on seeded campaigns.",
      "No abuse report is ever sent. Reports are generated for review only.",
    ],
  },
];
