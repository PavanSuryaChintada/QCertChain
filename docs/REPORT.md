# QCertChain — technical report

*Generated 2026-10-08T18:18:54.331931+00:00 from `reports/metrics.json` by `scripts/build_report.py`. Every number below was measured by `scripts/evaluate.py`; anything not measured says so.*

## Summary

QCertChain watches the public Certificate Transparency (CT) logs for lookalike domains, confirms phishing only on page evidence, groups confirmed domains into campaigns by shared infrastructure, and computes the smallest set of takedowns (hosting IPs, nameservers, registrars) that removes the most of a campaign. Each confirmed domain gets a signed, Merkle-rooted evidence bundle and a registrar-ready abuse report — **generated, never sent**. Campaign commitments and evidence roots go to a permissioned ledger so a second organisation can inherit a campaign without receiving the first one's telemetry. An email-header module links sender and link domains in a pasted message to the same pipeline.

What the measurements show, in one paragraph: the evidence gate held — on labelled pages it never confirmed a legitimate page (precision 1.0), every stored evidence bundle re-verified and every one-byte tamper was caught and named, and the takedown optimiser plans a 400-domain campaign in under a quarter of a second. The weak points are upstream: at the specified triage threshold the rules missed every real phishing domain naming our brands that the public feeds contained, and lead time over OpenPhish is not measured: 0 CT-first matches on the exact hostname (fewer than 10); 589 OpenPhish entries, 589 excluded (E1 259, E2 0, E3 322, E4 8), 0 listed before CT showed them, 0 with no CT sighting. Both are stated below with the numbers and the open decision.

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

**Counts used in this report** for live confirmation (capture window 2026-10-07T06:30:36Z to 2026-10-07T18:33:46Z, before the S4 re-check). Each term is defined once, here, and used with exactly this meaning below.

| Term | Count | Meaning |
|---|---|---|
| live domains in the capture window | 1,435 | public-feed candidates of the pipeline operator (org 1; never the seeded demo data) whose verdict was written between capture start and the snapshot |
| assessed | 659 | a page was fetched and analysed: the verdict is confirmed or dismissed, or a candidate with recorded evidence |
| unreachable | 776 (318 from kennelstudio.com) | no assessable page: the name did not resolve, an error or parked page, a TLS or protocol error, a timeout, or the SSRF guard |
| with a favicon | 432 | the domain's page served a favicon that we fetched and hashed, at any check |
| with their own brand's icon | 0 | that favicon's hash equals a reference hash of the brand the domain was triaged as impersonating |
| with any strong signal | 0 | at least one strong detector fired on the page |

**Where the live pipeline stops.** Clustering, takedown planning, evidence bundles and ledger anchoring all take confirmed domains as their input, and no live domain has been confirmed. So the live pipeline currently ends at the confirmation gate: live candidates are triaged and assessed, and none goes further. The known-kit list grows only from confirmations too, so it has not learned a live kit. Everything downstream of confirmation in this report is demonstrated on the seeded campaign (synthetic data, labelled as such).

| Measured after the S4 re-check (2026-10-08T02:09:52Z) | Count | Meaning |
|---|---|---|
| live domains confirmed | 0 | live domains in the capture window with a confirmed verdict |
| live domains in a campaign | 0 | live domains in the capture window whose verdict carries a campaign |


### Detection: triage (deployed rules)

| Metric | Value | Data |
|---|---|---|
| Latency per name (p50 / p95 / p99) | 294.5 / 1519.2 / 5333.8 µs | 200,000 unique live CT names |
| Candidates per minute of live stream | 1.5 | same capture |
| Legitimate domains made candidates | 18 of 60,000 | held-out Tranco domains |
| Hard-negative candidate rate | 72.1% | 584 legitimate domains containing a brand token |
| Recall on real phishing naming our brands | 1.0 (8 domains) | PhishTank + OpenPhish, 90 days |

Precision at the real 1:1000 base rate: 0.0024. Balanced-set precision is never reported.

Latency: p99 5333.8 µs sits at the 5 ms budget on this laptop; the median is 294.5 µs.

Missed at the 0.35 threshold: none of the brand-phishing set.

**Threshold: 0.35 (owner decision, 2026-10-07).** A candidate is not a verdict. A domain is marked confirmed only after its page is fetched and two strong signals are found, and the database itself rejects a confirmation with fewer. Precision is therefore protected downstream, while recall lost at triage cannot be recovered: a name that is never a candidate is never fetched. Lowering the threshold costs fetch budget, not false accusations. The cost is measured in candidates per hour at live CT volume, below; fetch volume is the real constraint.

Full sweep, rules as deployed (1,837,672 live names per hour; 9 real phishing domains naming our brands; 2,767 from the global feeds; 60,000 random Tranco domains; 584 hard negatives). Precision uses a 1-in-1000 base rate, never an even phishing/benign mix: TPR × 0.001 / (TPR × 0.001 + FPR × 0.999), with TPR over all phishing and FPR over random Tranco.

| Threshold | Precision at 1:1000 | Recall, our brands | Recall, all phishing | FP rate, random | Hard-negative FP | Candidates / hour |
|---|---|---|---|---|---|---|
| 0.20 | 0.0113 | 1.00 | 0.0072 | 0.0633% | 72.1% | 2,417 |
| 0.25 | 0.0113 | 1.00 | 0.0072 | 0.0633% | 72.1% | 2,417 |
| 0.30 | 0.0012 | 1.00 | 0.0007 | 0.0617% | 72.1% | 1,020 |
| 0.35 | 0.0024 | 1.00 | 0.0007 | 0.0300% | 72.1% | 689 |
| 0.40 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 2.4% | 119 |
| 0.45 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 2.4% | 92 |
| 0.50 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 2.2% | 9 |
| 0.55 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 0.0% | 0 |
| 0.60 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 0.0% | 0 |
| 0.65 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 0.0% | 0 |
| 0.70 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 0.0% | 0 |
| 0.75 | 1.0000 | 0.11 | 0.0004 | 0.0000% | 0.0% | 0 |
| 0.80 | — | 0.00 | 0.0000 | 0.0000% | 0.0% | 0 |

Reading it: recall on our brands falls from 100% to 11% between 0.35 and 0.40, while candidates per hour fall from 689 to 119.
The precision of 1.0 at 0.40 and above rests on zero false positives in 60,000 random domains with near-zero recall, so it says nothing either way. The brand-phishing set is small (9 domains); the recall column is indicative, not a tight estimate. The hard-negative rate (legitimate domains containing a brand token) is the cost of 0.35: those become candidates, are fetched, and fail the two-strong-signal gate.

Exact confusable-skeleton matches (a 0.75 signal on its own, owner decision 3) fired on 0 of 60,000 random Tranco domains.

### Detection: trained model (not deployed)

A calibrated logistic regression on the same 12 features was trained on PhishTank + OpenPhish positives (de-duplicated by campaign) and Tranco negatives. Temporal split AUC 0.787, campaign-disjoint AUC 0.8443; at 0.45 recall 0.2103, precision at 1:1000 0.0772. **Decision: rules stay (provenance 'rules'): a hard check failed.** Failed checks: Tranco top-1000 flagged ['aws.dev', 'amazon.dev'], brand domains above 0.1 ['onlinesbi.sbi'], release-gate misses ['icicibannk-login.top'] and flags ['netbanking.hdfcbank.com']. The public feeds barely cover Indian brands, so the model learned TLD and name shape rather than brand impersonation.

### Confirmation gate

Precision **1.0**, recall **0.3704** on 54 labelled pages (54 labelled pages served over real HTTP from 127.0.0.1: 10 known-kit and 10 unknown-kit static-era phishing (HTML form posts), 7 modern JS-kit phishing (S3d: Telegram/Discord/form-relay exfil, foreign POSTs, a same-origin relay), 10 legit brand-like logins posting to the brand, 10 blogs, 5 parked, 2 legit modern logins; kit knowledge from a disjoint sample). Verdicts by truth: `{"phishing": {"confirmed": 10, "candidate": 17}, "legit": {"candidate": 12, "dismissed": 10, "unreachable": 5}}`. False confirmations of legitimate pages: **0**. A missed phishing page has at most one independent strong signal: it stays a visible candidate rather than being accused on one fact.

| Family | Truth | Pages | Confirmed |
|---|---|---|---|
| static known kit | phishing | 10 | 10 |
| static unknown kit | phishing | 10 | 0 |
| legit brand like login | legit | 10 | 0 |
| legit blog | legit | 10 | 0 |
| legit parked | legit | 5 | 0 |
| modern js kit | phishing | 7 | 0 |
| modern js legit | legit | 2 | 0 |

The first 20 phishing pages are static-era kits (HTML form posts). On live data that era is over (see below), so the set could not see its own blind spot: neither new signal fired on any of them. The modern JS-kit cases were added so the evaluation tests the code that ships. With the shipped strengths, 0 of the 7 modern JS-kit cases are confirmed: S1 alone is one strong signal and S2 is moderate. The same-origin relay case would stay unconfirmed even with both signals strong; it is counted as a miss, not removed.

### Live confirmation: a measured zero, its cause, and what changed

Of the 1,435 live domains in the capture window, 659 were assessed and 776 were unreachable. Of the 659 assessed, **0** came back with any strong signal, so none could be confirmed under the original three strong signals (a credential form posting to a foreign origin, a known-kit DOM hash, the brand's real favicon). The cause, measured:

- **Modern kits are JavaScript applications.** The login form is built in the browser and credentials leave by fetch/XHR, so a check that reads `<form action>` cannot fire. Worked example: `meesho-all.cfd` (titled "Meesho", password field rendered) has no `<form>` element in its raw HTML at all.
- **Favicons:** of the 432 live domains with a favicon, 0 appeared with their own brand's icon (3 with another brand's). References: 73 icon hashes for 34 of 40 brands; the rest block our crawler.
- **Known kits:** the kit-signature check only knows the seeded kits, so it cannot match a novel live kit.
- **Unreachable:** 776 live domains in the capture window were unreachable: HTTP 404 error page 391, dns: name does not resolve 142, tls / http protocol error 70, timeout 47, parked page (HTTP 2xx/3xx) 42, HTTP 401 error page 23. `kennelstudio.com` alone accounts for 318 of them (auto-generated subdomains that answer 404): subdomain-wildcard noise, reported here rather than carried silently.

**What was added.** Two signals that read what a JS-era kit ships, by static inspection only (nothing is ever typed, clicked or submitted), both firing only on a page whose rendered DOM asks for a password or OTP: **S1** a hardcoded exfiltration endpoint (a Telegram bot API URL with its token, a Discord webhook, a mail or form-relay API; a bare `t.me` link never fires) and **S2** a credential POST written in the page's code to a site that is neither the page's own, the brand's, nor a listed analytics/captcha service. And one shared independence rule (S3b), in code and in the database: two strong signals count together only if they come from different detectors and rest on different artifacts (destination site, DOM hash, favicon hash), so one POST to `api.telegram.org` seen by S1 and S2 is one piece of evidence, not two.

| False-positive gate run | Legitimate login pages that rendered a credential field | S1 false positives | S2 false positives |
|---|---|---|---|
| 1: as first built (development pages) | 18 | 0 | 6 |
| 2: after the one refinement (same pages) | 14 | 0 | 0 |
| 2b: re-test of development pages that did not render in run 2 | 2 | 0 | 0 |
| held-out set, run once | 13 | 0 | 1 |

Run 1's S2 false positives were legitimate pages' own telemetry: 14 of its hits were requests fired while the page loaded and 1 was the string `https://www.`, not a URL. The one approved refinement dropped load-time requests and required a real hostname.

**Method, stated because the result depends on it.** S2 was refined against the 18 development pages (the legitimate login pages that rendered a credential field in run 1). A clean re-run on those same pages proves nothing, because the refinement was designed against them. So S2 was then evaluated once on 45 held-out legitimate login pages that played no part in development (13 of them rendered a credential field when loaded, the only ones that can exercise S1 or S2, alongside 27 labelled legitimate pages). It produced **1 false positive**: `www.twitch.tv`, whose own code (`assets.twitch.tv`) POSTs to `eppo.cloud`. S2 was **not** re-tuned against the held-out set: tuning on it would turn it into a training set and its result into one more development number. Therefore S2 ships as moderate (it can support a verdict, never count as one of the two strong signals), S1 ships as strong (0 false positives in every run), and live confirmations remain zero.

**The zero is evidence, not proof:** it rests on 18 development pages, 13 held-out pages that rendered a credential field and the labelled legitimate pages. A runtime kill switch (`POST /admin/signals`, admin key) lowers S1 or S2 without a redeploy if a false positive appears during evaluation; it can only lower a strength, never raise it.

Shipped strengths: S1 `strong`, S2 `moderate`.

**S4 re-check.** The same 1,435 live domains in the capture window were re-checked through the real enrichment worker with the shipped logic (measured 2026-10-08T02:09:52Z): **0 confirmed**; verdicts `{"unreachable": 788, "candidate": 435, "dismissed": 212}`; 647 assessed; 0 with any strong signal (by detector: none); 788 unreachable: HTTP 404 error page 391, dns: name does not resolve 144, tls / http protocol error 77, timeout 46, parked page (HTTP 2xx/3xx) 40, HTTP 401 error page 24.

Which signals fired: S1 fired on 0 live domains; S2 fired on 6 live domains (moderate), destination sites: contaboserver.net 3, shopifysvc.com 2, mydukaan.io 1. Where those destinations are hosting platforms' own services, these are the false positives the held-out gate predicted, now seen on live traffic, which is why S2 is not a strong signal.

**What the zero means, and what it does not.** Triage works on live traffic at scale: 4,841 unique candidate names at the 0.35 threshold in the CT capture. Clustering and takedown planning are demonstrated on seeded data: the seeded 400-domain campaign (synthetic data, labelled as such) is clustered and its takedown plan solved by CP-SAT in 131 ms (median, through the API). The page-content confirmation layer does not fire on modern JS kits, and because clustering takes confirmed domains as its input, no live domain has reached the campaign layer. The system detects at live scale and clusters and plans on seeded data; it does not currently confirm by page content on live traffic.

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

### CT capture (22.58 h): integrity and coverage

Window 2026-10-07T06:30:36Z → 2026-10-08T05:05:22Z (22.58 h); 247,671 certstream messages in 3 recorder runs (one gzip member each). Dataset: data/replay/ct_live.jsonl.gz (complete capture), certstream-server-go lite stream. Measured 2026-10-08T17:54:32Z.

Capture gap: 2026-10-07T08:15:14Z → 2026-10-07T08:55:04Z (**39.8 min**); 2026-10-07T18:00:01Z → 2026-10-07T18:13:22Z (**13.4 min**); 2026-10-07T20:02:57Z → 2026-10-07T20:13:32Z (**10.6 min**); 2026-10-08T02:18:02Z → 2026-10-08T03:09:14Z (**51.2 min**); 2026-10-08T03:13:30Z → 2026-10-08T04:14:27Z (**60.9 min**), 175.9 min in total. Every other silence between messages was under 278.4 s.
Recorder log cross-check: its largest silence is 2026-10-08T02:07:00Z → 2026-10-08T03:12:00Z (65 min); 315 websocket reconnects; 39 OpenPhish polls, 13 failed.

Coverage = minutes with at least one certificate ÷ minutes in the window (1,356 minutes, 171 of them inside the gaps).

| CT log operator | Coverage | Coverage outside the gaps | Messages |
|---|---|---|---|
| **All operators** | **85.77%** | 98.14% | 247,671 |
| Cloudflare | 78.76% | 90.13% | 13,253 |
| DigiCert | 81.64% | 93.42% | 27,462 |
| Geomys | 39.16% | 44.81% | 9,405 |
| Google | 82.74% | 94.68% | 49,952 |
| IPng Networks | 76.99% | 88.1% | 39,405 |
| Let's Encrypt | 78.02% | 89.28% | 48,360 |
| Sectigo | 81.49% | 93.25% | 26,765 |
| TrustAsia | 82.15% | 94.01% | 32,419 |
| Other | 25.81% | 29.54% | 650 |

The fixture keeps a 1 % background sample, so a low-volume operator can miss a minute without any capture loss; the column outside the gaps separates that from the gaps themselves.

Duplicates: 85,885 messages repeat a certificate already in the capture (64,489 across a restart). Of those, 0 are the same log entry delivered twice (0 across a restart); the rest are the same certificate from another CT log. n = 247,671 messages. Cross-log duplication is expected: browsers require a certificate to carry signed timestamps from more than one CT log, so each certificate is submitted to several logs and the stream delivers every copy. Deduplication is by the leaf certificate's SHA-256 fingerprint, so a raw message count overstates the number of distinct certificates by the duplicate share above.

Triage of the whole capture with the deployed rules at **0.35**: **4,616 candidate certificates**, **4,841 unique candidate names** (8,760 messages; n = 161,786 unique certificates triaged). The fixture holds every certificate that scored >= 0.20 when recorded plus a 1 % sample of the rest; a certificate the deployed rules would now score >= threshold but scored < 0.20 at recording is only present if sampled.

Replay fixture `data/replay/ct_24h.jsonl.gz`: 161,786 messages sorted by `seen`, 85,885 duplicates removed, 17,439 scored (≥ 0.2) + 144,347 background sample (1 %). Replay at 360× takes **3.4 min** (stream.py replay sleeps min(delta / speed, 2.0 s) between messages; the capture gap therefore costs at most 2 s).

Why operators differ: the self-hosted aggregator's own fetch errors, counted from its log (certstream-server-go container log, all runs of the capture): geomys.org 589 (connection closed by the server (EOF) 546, timeout 30, other 10, DNS failure 3); ipng.ch 109 (timeout 99, connection closed by the server (EOF) 5, DNS failure 5); googleapis.com 80 (timeout 74, connection closed by the server (EOF) 3, DNS failure 3); letsencrypt.org 56 (timeout 52, DNS failure 3, connection closed by the server (EOF) 1); godaddy.com 45 (HTTP error status 45); e-szigno.hu 43 (timeout 40, connection closed by the server (EOF) 2, DNS failure 1); trustasia.com 35 (HTTP error status 27, timeout 7, DNS failure 1). Each error costs a 5 s back-off and a worker restart for that log, so the operator with the most errors loses the most minutes. The errors are on the connection to the operator's servers, not in our pipeline.

### Live pipeline counts at threshold 0.35

Window 2026-10-07T06:30:36Z → 2026-10-08T05:05:22Z (the capture window); first candidate 2026-10-07T06:37:03.084306+00:00, last 2026-10-08T02:17:41.978738+00:00. Measured 2026-10-08T17:56:16Z.

| Count at threshold 0.35 | Value | n | Data |
|---|---|---|---|
| Live candidates from CT | 4,920 | — | Supabase domains: source=certstream, shared (origin_org_id null), candidate_at in window |
| org1 confirmed | 0 | 4,920 candidates | domain_verdicts of the pipeline org for those candidates; status as of measured_at |
| org1 dismissed | 219 | 4,920 candidates | domain_verdicts of the pipeline org for those candidates; status as of measured_at |
| org1 unreachable | 814 | 4,920 candidates | domain_verdicts of the pipeline org for those candidates; status as of measured_at |

All org1 statuses: `{"candidate": 444, "no verdict row (candidate)": 3443, "unreachable": 814, "dismissed": 219}`.
The pipeline's own largest gap between candidates: 2026-10-07T08:15:22Z → 2026-10-07T08:55:10Z (39.8 min).
Re-deliveries: 1,516 candidate rows were seen again (`last_seen` > `first_seen`), 11 of them across the gap. certificates.fingerprint is unique and a repeat is absorbed by ON CONFLICT without a counter, so certificate re-deliveries are not measurable. domains.last_seen is touched on every repeat candidate sighting (precertificate + final certificate, other logs, re-delivery); rows first seen before the gap and touched after it bound restart re-deliveries from above.

### Lead time over phishing feeds

Dataset: OpenPhish public feed polled every 30 min x CT first sighting (ct_live.sqlite), complete capture. Match: exact hostname of the OpenPhish URL == a name in ct_first_seen (non-allowlisted names from every certificate in the capture); eTLD+1 matches reported separately, never mixed. Listing time: +/-30 min: the OpenPhish feed is polled every 30 min, so a URL's listing time lies in the 30 min before the poll that first saw it. Measured 2026-10-08T17:56:08Z.

**Exact hostname: not measured: 0 CT-first matches on the exact hostname (fewer than 10); 589 OpenPhish entries, 589 excluded (E1 259, E2 0, E3 322, E4 8), 0 listed before CT showed them, 0 with no CT sighting.**

Exclusions (each OpenPhish entry falls under the first rule that applies):

| Rule | Exact hostname | eTLD+1 (separate) |
|---|---|---|
| E1: present in the first OpenPhish poll: listed before the capture started | 259 | 231 |
| E2: the poll interval in which it was first listed overlaps a capture gap (listing time not known to the 30-min resolution) | 0 | 0 |
| E3: no CT sighting and first listed after a gap began: its certificate may have been issued during the gap | 322 | 264 |
| E4: CT first sighting within W after the capture start or a gap end: an earlier sighting may have been missed | 8 | 15 |
| Retained: seen in CT before listing | 0 | 0 |
| Retained: listed before CT showed it | 0 | 0 |
| Retained: no CT sighting (not in this capture) | 0 | 0 |
| Entries | 589 hosts | 510 eTLD+1s |

eTLD+1 (reported separately, never mixed with the exact match): not measured: 0 CT-first matches on the eTLD+1 (fewer than 10); 510 OpenPhish entries, 510 excluded (E1 231, E2 0, E3 264, E4 15), 0 listed before CT showed them, 0 with no CT sighting.
W = 690 min: p99 of the delay between the first and second sighting of a name in scored certificates (38222 names seen twice) = 661.6 min, rounded up to the 30-min poll resolution: a name first shown during a gap is, with that probability, seen again before W has passed, so first sightings later than W after a gap are not re-sightings of a missed one.
51 of the 589 hosts (before exclusions) are on allowlisted domains, which the first-seen index does not store by design, so they cannot match.
OpenPhish: 735 URLs (589 hosts) over 39 polls; new URLs first appeared in 3 of them.

The earlier check (kept as `lead_time_phishtank_30min`): 11 PhishTank hostnames had their own certificate in a 30-minute capture and 0 were seen in CT first; no lead time was claimed from it.

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

- HTTP-only phishing has no certificate and is invisible to CT monitoring. Browsers increasingly warn on plain HTTP login forms, which limits it, but this system does not see it at all.
- Phishing hosted at a path on a compromised legitimate site (`https://real-bakery.example/wp-content/x/login`) produces no new certificate: the site's existing certificate covers it. It is out of CT scope entirely; only the email module, if a message linking to it is analysed, can surface it.
- Wildcard certificates hide the phishing subdomain; the parent is caught.
- **A kit that relays credentials through its own server is invisible to any browser-side check.** Worked example, `meesho-all.cfd`: a Vue application (RuoYi-Vue admin template) whose login code POSTs to its own origin, `/dev-api/mobileUser`, and the server forwards the data on. The exfiltration happens after the data leaves the browser, so neither the form-action check, S1 (no hardcoded exfiltration endpoint) nor S2 (no foreign POST) can see it, and no client-side heuristic could. Confirming such a page needs evidence from elsewhere: server-side infrastructure correlation, hosting reputation, or kit-fingerprint matching on the bundled JavaScript rather than on its behaviour. The campaign graph is where that evidence belongs, since such a domain sits on the shared infrastructure (hosting IP, nameserver) of the rest of its campaign. As built, though, clustering takes confirmed domains as its input, so an unconfirmed relay-kit domain does not enter a campaign today; admitting candidates that sit on the shared infrastructure of a confirmed campaign is the path to reaching it through its infrastructure rather than its page.
- The email module analyses pasted or uploaded messages only; it never connects to a mailbox.
- QAOA runs on a reduced problem of at most 24 qubits on a simulator.
- Demonstration campaign data is synthetic, labelled `source: seed` everywhere, and uses only reserved `.example` names and documentation IP ranges, so it can never name a real business.
- Takedown requests are generated, never sent. No code in the repository sends email, files abuse forms or calls registrar APIs; the database rejects a report marked sent.

## Future work

**Infrastructure co-location as an entry path into a campaign.** A domain that cannot be confirmed by its page content (a same-origin relay kit, a page behind a host's phishing interstitial, a kit not yet deployed) can still be placed by its infrastructure. Proposed rule: a candidate whose hosting IP or nameserver is already a node of a confirmed campaign joins that campaign as an infrastructure-linked candidate. Its verdict does not change: it stays a candidate, is never shown or reported as confirmed and is never accused on the link alone, but the takedown planner counts it as covered by that node, so the plan that takes down the confirmed campaign also covers it. The link must be attacker infrastructure: shared hosting, CDN anycast addresses and registrars (each serving millions of unrelated domains) are excluded, as they already are as clustering edges. Not built.

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
npm run finalize        # after the 24 h capture: integrity, live counts, lead time, fixture, this report
```

