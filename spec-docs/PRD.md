# PRD — SEVER

Phishing campaign interdiction. Scope, users, features.

---

## 1. The crisis, in numbers

| | |
|---|---|
| **21 seconds** | Median time to click a phishing link after delivery |
| **28 minutes** | Median time for a human to report it |
| **4.5 days** | Average time for Google Safe Browsing to detect a phishing site |
| **83.9%** | Phishing sites already taken down *before* Safe Browsing notices them |
| **3.8 million** | Phishing attacks recorded in 2025 |
| **54 hours** | Average phishing site lifespan |

The blocklist arrives after the crime. Reporting arrives 27 minutes after the first victim.

## 2. Why the standard answer fails

Every submission on this problem builds a **URL classifier**. Paste a URL, get "malicious: 94%."

**It is structurally too late.** A URL only enters a dataset after it has been sent to someone. The click happened 21 seconds after delivery.

**It kills one head of a hydra.** Attackers deploy hundreds of domains from one phishing kit on shared infrastructure. Filing per-URL reports leaves the campaign's remaining domain inventory and reusable kit intact and ready to redeploy.

> **Detecting a phishing email is solved, crowded and useless. Killing the campaign behind it is not.**

## 3. What we do instead

**Catch the certificate, not the click.** Every HTTPS certificate is published to a public, append-only log within seconds, and Chrome rejects unlogged certificates. Attackers must announce their own domains to get a padlock. We listen to that firehose.

**Rebuild the campaign, not the URL.** Shared hosting, ASN, nameservers, certificate patterns, DOM structure hash and favicon hash link one domain to the other 399.

**Compute the minimum kill.** Which smallest set of takedowns fragments the campaign — *"take down these 4, 387 of 400 die."* This is maximum coverage, NP-hard, and it is the contribution.

**Share the detection with proof.** A permissioned ledger so the second organisation inherits the first organisation's work, with tamper-evident chain of custody.

---

## 4. Users

**SOC analyst** — desktop. Watches the live feed, reviews confirmed campaigns, approves or rejects the takedown plan, exports evidence. Wants to stop reading 400 rows.

**Threat intelligence lead** — wants campaign-level attribution: which operator, which kit, which infrastructure, reappearing where.

**Second organisation** — a different bank or brand. Wants to inherit intelligence without receiving another company's internal telemetry, and wants to know who vouched for it.

---

## 5. Features

### F1 · Live CT monitoring
Streaming certificate consumption, brand-token and lookalike triage, real-time feed in the console with a visible connection state. Supports **live** and **replay** modes, always labelled.

### F2 · Confirmation, not prediction
Automated page fetch, screenshot, DOM capture. Rule-based detection: cloned login form, credential POST to a foreign origin, brand asset reuse, obfuscated JS. Explicit `candidate` / `confirmed` / `dismissed` status, always visible.

### F3 · Campaign graph
Infrastructure and domain nodes linked by shared attributes. Connected-component clustering into campaigns. Interactive graph view.

### F4 · Interdiction plan
Maximum-coverage optimisation over the campaign graph under a takedown budget. Output: ranked targets, kill count, coverage percentage, solver used, and a benchmark comparison.

### F5 · Evidence bundles
Per-target signed artifact set with Merkle root. Generated abuse report in registrar-ready format. **Never submitted.**

### F6 · Cross-organisation ledger
Campaign commitments and evidence anchors on a permissioned chain. Signed reporter attestations. Second-org inheritance with provenance.

### F7 · Analyst console
Live feed, campaign list, graph, plan review, evidence viewer, cross-org feed, metrics.

---

## 6. Out of scope — decisions, not gaps

- **Submitting takedown requests.** Generated only. One false positive takes a legitimate business offline.
- **ML phishing classifier.** Confirmation is rule-based because the output is an accusation.
- **HTTP-only phishing.** No certificate, no CT record. Stated limit.
- **Wildcard certificate subdomains.** `*.example.com` hides the phishing host. Stated limit.
- **Real victim or customer data.** None enters the system.
- **Email scanning.** We work upstream of the inbox, on purpose.

---

## 7. Success criteria

**Must be true at demo:**
- Live CT stream visibly running with real certificates
- At least one real candidate surfaced from the live stream during the window
- A seeded campaign clusters correctly into 400+ domains
- Interdiction returns a plan in under 1 second with CP-SAT, and a benchmark table against QAOA and greedy
- A tampered evidence artifact provably fails verification, on screen
- Second-org console shows the campaign inherited from the ledger with reporter provenance
- Everything works with Qiskit uninstalled

**Judged on:**
- The timing argument — 6 hours before the first email, 4 days before Safe Browsing
- Campaign-level interdiction rather than per-URL blocking
- Confirmation discipline — candidates are never coloured as verdicts
- Honest benchmarking, losses included

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Nothing interesting in the live demo window | Replay mode + seeded campaign, both labelled |
| False positives accuse a real business | Hard `candidate`/`confirmed` separation; allowlist; never auto-submit |
| Triage can't keep up with 200k certs/min | Profile on day 1; target < 5 ms/cert; Redis Streams backpressure |
| Playwright is heavy and flaky | `httpx` fallback path; partial evidence bundles marked as such |
| "Netcraft already does this" | True for CT monitoring. **Our differentiator is campaign interdiction, cross-org ledger and evidence chain — not CT monitoring itself.** Never claim to have invented it. |
| Chain setup eats the build | Hardhat local node, not Hyperledger Fabric. Anchoring is non-blocking. |
