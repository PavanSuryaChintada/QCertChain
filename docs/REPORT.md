# QCertChain — technical report

*Generated 2026-10-06T19:18:24.150444+00:00 from `reports/metrics.json` by `scripts/build_report.py`. Every number below was measured by `scripts/evaluate.py`; anything not measured says so.*

## Summary

QCertChain watches the public Certificate Transparency (CT) logs for lookalike domains, confirms phishing only on page evidence, groups confirmed domains into campaigns by shared infrastructure, and computes the smallest set of takedowns (hosting IPs, nameservers, registrars) that removes the most of a campaign. Each confirmed domain gets a signed, Merkle-rooted evidence bundle and a registrar-ready abuse report — **generated, never sent**. Campaign commitments and evidence roots go to a permissioned ledger so a second organisation can inherit a campaign without receiving the first one's telemetry. An email-header module links sender and link domains in a pasted message to the same pipeline.

What the measurements show, in one paragraph: the evidence gate held — on labelled pages it never confirmed a legitimate page (precision 1.0), every stored evidence bundle re-verified and every one-byte tamper was caught and named, and the takedown optimiser plans a 400-domain campaign in under a quarter of a second. The weak points are upstream: at the specified triage threshold the rules missed every real phishing domain naming our brands that the public feeds contained, and a 30-minute CT capture could not demonstrate a lead time over the feeds. Both are stated below with the numbers and the open decision.

## How it works

```
CT logs ──► self-hosted certstream ──► ingest (dedup) ──► triage (candidate, never a verdict)
   ──► confirmation: fetch + observe the page; CONFIRMED only with ≥ 2 independent strong signals
   ──► enrichment (DNS, RDAP, ASN, TLS) ──► campaign graph ──► takedown plan (max coverage, CP-SAT)
   ──► evidence bundle (SHA-256 Merkle root + Ed25519) + abuse report (never sent) ──► ledger (hashes only)
email headers ──► signals ──► sender/link domains enter the same candidate queue
```

| Stage | Method |
|---|---|
| Ingest | certstream-server-go v1.10.1, self-hosted (the public endpoint was dead), RFC 6962 and static-ct tiled logs; one certificate seen in several logs is processed once |
| Triage | 40 Indian brands; exact token, Damerau-Levenshtein lookalike, Unicode homoglyph skeleton, risky TLD, keywords, name shape; allowlist (Tranco top 100k + brand domains + brand-owned TLDs) checked first |
| Confirmation | strong: credential form posting off-site, known phishing-kit DOM structure, brand favicon; moderate: brand in title, obfuscated JS, password field; weak: new domain, free CA. Confirmed needs two strong |
| Campaigns | bipartite graph domain → infrastructure; components over edges ≥ 0.6 (kit 1.0, favicon 0.85, IP 0.8, nameserver 0.6); ASN/issuer/registrar never link on their own |
| Takedown plan | maximum coverage under a budget k over IP / nameserver / registrar targets; CP-SAT in production, greedy, simulated annealing and QAOA on the same QUBO, with a benchmark of all four |
| Evidence | screenshot, DOM, headers, certificate, RDAP, DNS, ASN, kit hashes; SHA-256 leaves sorted by name → Merkle root → Ed25519; verification names the failing file |
| Ledger | Solidity on a permissioned EVM (Hardhat): org registry, campaign registry queryable by kit hash, evidence anchors, attestations including *disputed*; hashes and commitments only |

Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.

## Results

### Detection: triage (deployed rules)

| Metric | Value | Data |
|---|---|---|
| Latency per name (p50 / p95 / p99) | 294.5 / 1519.2 / 5333.8 µs | 200,000 unique live CT names |
| Candidates per minute of live stream | 1.5 | same capture |
| Legitimate domains made candidates | 0 of 60,000 | held-out Tranco domains |
| Hard-negative candidate rate | 2.4% | 584 legitimate domains containing a brand token |
| Recall on real phishing naming our brands | 0.0 (9 domains) | PhishTank + OpenPhish, 90 days |

Precision at the real 1:1000 base rate is not meaningful here: recall on the global feeds is zero because the public phishing feeds are dominated by brands outside our list of 40 (e.g. Bradesco, Allegro); a brand-list triage scores those 0 by design, so global recall measures feed composition. Balanced-set precision is never reported.

Latency: p99 5333.8 µs sits at the 5 ms budget on this laptop; the median is 294.5 µs.

Missed at the 0.45 threshold: `amazon-refund.cc`, `amazon-annulation.com`, `amazon-paiement.com`, `hdfc8-7v8vtyu.vercel.app`, `amazonstocksgo.co`, `prime-amazonfr.com`, `amazon-video-musique.com`, `chouhdfcom.com`, `yon0sbl.vercel.app`. Each carries a brand token (0.35) but no second signal from the TRD list.

Threshold options (owner decision pending — the default is unchanged):

| Threshold | Candidates / min (live) | Brand phishing caught | Hard-negative candidate rate |
|---|---|---|---|
| 0.3 | 17.0 | 9/9 | 72.1% |
| 0.35 | 11.5 | 8/9 | 72.1% |
| 0.4 | 2.0 | 0/9 | 2.4% |
| 0.45 | 1.5 | 0/9 | 2.4% |

### Detection: trained model (not deployed)

A calibrated logistic regression on the same 12 features was trained on PhishTank + OpenPhish positives (de-duplicated by campaign) and Tranco negatives. Temporal split AUC 0.787, campaign-disjoint AUC 0.8443; at 0.45 recall 0.2103, precision at 1:1000 0.0772. **Decision: rules stay (provenance 'rules'): a hard check failed.** Failed checks: Tranco top-1000 flagged ['aws.dev', 'amazon.dev'], brand domains above 0.1 ['onlinesbi.sbi'], release-gate misses ['icicibannk-login.top'] and flags ['netbanking.hdfcbank.com']. The public feeds barely cover Indian brands, so the model learned TLD and name shape rather than brand impersonation.

### Confirmation gate

Precision **1.0**, recall **0.5** on 45 labelled pages (45 labelled pages served over real HTTP from 127.0.0.1: 10 known-kit phishing, 10 unknown-kit phishing, 10 legit brand-like logins posting to the brand, 10 blogs, 5 parked; kit knowledge from a disjoint sample). Verdicts by truth: `{"phishing": {"confirmed": 10, "candidate": 10}, "legit": {"candidate": 10, "dismissed": 10, "unreachable": 5}}`. False confirmations of legitimate pages: **0**. Every missed phishing page is an unknown kit with a single strong signal: it stays a visible candidate rather than being accused on one fact.

### Email headers

| Condition | Phishing rated malicious | Phishing rated suspicious | Legit rated malicious |
|---|---|---|---|
| cold | 0/8 | 7/8 | 0/5 |
| warm | 6/8 | 2/8 | 0/5 |

Cold = empty database; warm = the email's link domains already confirmed by the CT pipeline. The sample set is synthetic and small (13 messages), so these numbers are directional. With a cold database a header-only spoof has at most one strong signal, so it is shown grey as *suspicious — not verified*. No legitimate message was rated malicious in either condition. Whether to relax the two-strong rule for email is an open decision; the rule is unchanged.

### Response time (live pipeline)

| Stage | p50 (s) | p95 (s) | n |
|---|---|---|---|
| upstream aggregator stamp → our receipt | 20.994 | 30.233 | 114 |
| our receipt → candidate stored | 2.053 | 5.443 | 114 |
| CT seen → candidate (total) | 23.654 | 32.122 | 114 |
| candidate → verdict (target < 20 s) | 1.552 | 22.653 | 106 |

The candidate → verdict p95 (22.653 s) misses the 20 s target: the tail is sites that never answer and hit the 15 s page-load timeout. The median verdict takes 1.552 s. Most of the CT → candidate time is the upstream aggregator's own delay, before our pipeline receives the certificate.

Verdicts on live candidates: `{"unreachable": 102, "candidate": 10, "dismissed": 2}` — most fresh lookalike domains are not yet serving a page when their certificate appears; they stay candidates (`unreachable`) and are never guessed. Window since 2026-10-06T19:00:00Z.

### Ingest

One ingest process sustains **1839.6 unique certificates/s** into Redis (target 3,000/s). Live, the CT logs delivered 218.5 unique certificates/s (688.7 log entries/s; 56.4% of messages are the same certificate from another log; 37.4% from tiled logs), and triage consumer lag stayed at 0–3 entries.

### Takedown planning

Seeded campaign (400 synthetic domains, 19 takedown candidates; 3 repetitions per k, median solve time):

| k | cpsat | qaoa | annealing | greedy |
|---|---|---|---|---|
| 2 | 342 in 228 ms | 342 in 7615 ms | 342 in 310 ms | 342 in 1 ms |
| 3 | 400 in 162 ms | 400 in 8747 ms | 400 in 285 ms | 400 in 6 ms |
| 4 | 400 in 87 ms | 400 in 6381 ms | 400 in 164 ms | 400 in 1 ms |
| 5 | 400 in 58 ms | 400 in 6069 ms | 400 in 191 ms | 400 in 1 ms |

All backends reach the same coverage on this campaign; CP-SAT is the fastest exact method and greedy carries the (1 − 1/e) guarantee. QAOA uses a warm start: its initial state is biased toward the greedy plan (ε = 0.25) and it returns the best sampled bitstring, so matching greedy here is not independent evidence of the quantum search. The seed assigns each domain one of three registrars, so three registrar reports cover every domain — a property of this synthetic campaign, not of the method.

### Evidence and ledger

| Check | Result |
|---|---|
| Stored bundles that re-verify (Merkle root + Ed25519) | 25/25 |
| One-byte tamper of `dom.html` detected, with the file named | 25/25 |
| Bundles anchored on the permissioned chain | 400 of 400 |
| Anchored roots matching the chain on re-check | 10/10 |
| Campaigns published (second organisation can inherit by kit hash) | 1 |
| Abuse reports generated / sent | 400 / 0 |

The second-organisation view queries the ledger by kit fingerprint and receives the campaign's size, reporter and transaction — never the first organisation's domains or telemetry.

### Lead time over phishing feeds

11 phishing hostnames from PhishTank had their own certificate in our capture; 0 were seen in CT before being listed (the rest were certificate renewals for hosts already reported). The capture covers 30 minutes, so only certificates issued in that window can match. **No lead time is claimed from this data.**

## Trust boundaries

The ledger and the API are different trust boundaries, on purpose.

- **The ledger is deliberately public to every member organisation.** It carries hashes and counts only: the campaign's IOC Merkle root, the kit fingerprint, a domain count, a confidence, the reporting organisation and a timestamp — no domain names, IP addresses or page content. A second organisation can find the first one's campaign by kit fingerprint and corroborate or dispute it, without receiving any of its telemetry. That is the point of sharing through a ledger.
- **The API and database are strictly org-scoped.** Every request carries an API key that maps to one organisation. Each request runs as a restricted database role with that organisation set, and row-level security filters every organisation-owned table: campaigns, verdicts, enrichment, the campaign graph, evidence, abuse reports, takedown plans, email analyses and ledger writes. Another organisation's resource returns 404, never 403, so a response does not even reveal that it exists.
- **Shared by design:** certificates and candidates from the public CT feed. Each organisation sees only its own verdict on a shared candidate; whether another organisation confirmed it is never visible.

Both halves are tested in `services/tests/test_tenancy.py`: the second organisation gets 404 on every first-organisation campaign, graph, domain, evidence bundle, artifact, report, email analysis and plan, and can read the first organisation's anchored campaign on the chain.

**The consortium moment, in three steps.** Both organisations hold a populated, seeded campaign: Bank One an ICICI-themed kit of 400 domains, Bank Two an HDFC-themed kit of 50 domains on the same kit, sharing one hosting IP and one nameserver with Bank One's. Neither organisation can see the other; the overlap is found only through the ledger.

1. Bank Two lists its own campaigns and sees one campaign, its 50 `hdfc-*` domains and its own infrastructure, which happens to include the shared IP and nameserver.
2. Bank Two requests Bank One's campaign by id and gets 404. Bank One requesting Bank Two's gets 404 too.
3. Bank Two takes the kit hash from its own campaign and queries the ledger. It finds Bank One's report: IOC root, kit hash, domain count (400), confidence, reporter (Bank One SOC) and timestamp. No names, no IP addresses, no page content, and not Bank One's local campaign id.

Steps 1–3 are `test_consortium_steps_a_and_b_two_populated_orgs_neither_sees_the_other` and `test_consortium_step_c_org2_finds_org1_report_by_kit_hash_on_chain`, and were repeated against the hosted database with real keys.

**Defence in depth, demonstrated.** The isolation tests were checked against two deliberate breakages. Disabling the per-request organisation binding made all 5 tenancy tests fail, so the tests detect a leak rather than pass for the wrong reason. Stripping the code's own organisation filters from the repository queries still left the second organisation blocked, because row-level security in the database enforces the boundary independently of the application code.

## Limits

- HTTP-only phishing has no certificate and is invisible to CT monitoring.
- Wildcard certificates hide the phishing subdomain; the parent is caught.
- The email module analyses pasted or uploaded messages only; it never connects to a mailbox.
- QAOA runs on a reduced problem of at most 24 qubits on a simulator.
- Demonstration campaign data is synthetic, labelled `source: seed` everywhere, and uses only reserved `.example` names and documentation IP ranges, so it can never name a real business.
- Takedown requests are generated, never sent. No code in the repository sends email, files abuse forms or calls registrar APIs; the database rejects a report marked sent.

## Corrections made to the original specification

- QUBO (NPHARD §6): the specified coverage penalty rewards redundant coverage; replaced by an x-only inclusion–exclusion formulation (≤ 12 qubits instead of 26). It is exact up to second order: exact when no domain depends on more than two selected targets, an approximation beyond that. The ground state was checked by brute force against true coverage on 25 random instances with at most two dependencies per domain.
- Attestation contract: the specified logic recorded only the first attesting organisation; fixed and proven by a test that fails on the original.
- Organisation keys: the specified admin account would have been rejected as an organisation; orgs use accounts #1 and #2.
- Lookalike matching uses tokens of five or more characters; a flat edit distance of 2 on 3-letter tokens matches ordinary words.
- The campaign graph uses a deterministic radial layout: force-directed layouts took 17–22 s on a 400-domain campaign.
- Takedown targets are hosting IPs, nameservers and registrars only (hashes and whole networks cannot be taken down).

## AI assistance

This project was built with an AI coding agent (Claude Code). The agent wrote most of the code, tests and documentation, ran the measurements in this report, and reviewed its own work through a separate review pass. The work was human-directed: the project owner set the scope, made every product and architecture decision recorded in `docs/BUILD_DECISIONS.md` and the design spec, and reviewed the results. Every number in this report comes from `reports/metrics.json`, produced by `scripts/evaluate.py`, not from the agent's claims. The task-by-task log of what the agent did and how each step was verified is in `docs/AI_USAGE_LOG.md`.

## Reproduce

```bash
docker compose up -d redis certstream            # database: Supabase (DATABASE_URL in .env)
python -m scripts.apply_schema --url "$DATABASE_URL"
uvicorn services.api.main:app --port 8000
python -m services.ingest.stream & python -m services.api.workers.triage_worker &
python -m services.api.workers.enrich_worker & python -m services.api.workers.anchor_worker &
cd contracts && npx hardhat node & npx hardhat run scripts/deploy.ts --network localhost
cd apps/console && npm run dev                   # http://localhost:5180
python -m scripts.evaluate && python -m scripts.build_report
```

