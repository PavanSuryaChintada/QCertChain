# Build decisions

Every decision taken on the owner's behalf during the build (`Ruling:`), and every review finding deferred (`minor`), copied verbatim from the build ledger before it was deleted. Each ruling states what it costs if it is wrong.

## Owner decisions still open

- Task 19: OWNER DECISION PENDING: email cold-start recall 0/8 (warm 6/8, legit FP 0/5). Gate unchanged at >=2 strong. Options A/B/C/D reported.
- Task 24: OWNER DECISION PENDING: triage threshold 0.45 (TRD) vs 0.35 (recommended; 8/9 vs 0/9 brand phishing caught, 11.5 vs 1.5 candidates/min).
- Task 24: OWNER-VISIBLE: CT-vs-OpenPhish lead time not measurable from a 30-min capture (0 CT-first cases); report must not claim the spec's headline.
- Final: Ruling: I8 lookalike+homoglyph both firing is kept — it is what lifts pure homographs (xn--cicibank-shh.com etc.) over 0.45; pinned by tests; Cyrillic-s sbi.co.in (0.30) pinned as a KNOWN MISS pending owner decision — cost if wrong: one extra weight on homographs that also carry other signals.
- API authentication before any deploy (I11).
- Candidate flare animation colour: DESIGN.md flashes red, CLAUDE.md §2.2 forbids red on candidates.

## Rulings

- Setup: Ruling: work on branch feat/qcertchain-build in place, not a separate worktree — repo is new (docs only on main), .env/docker volumes live at repo root — cost if wrong: none, branch is isolated from main.
- Task 1: Ruling: web3 7.6.0 (plan pin) requires websockets<14, conflicts with TRD pin websockets==14.1 — pinned web3==7.10.0 (websockets<16) — cost if wrong: web3 API differences in Task 18, caught by its tests.
- Task 1: Ruling: CT capture (Task 3 config + capture.py) pulled ahead of Task 1 finish — owner's Phase 0 priority order (capture → schema → rename) — cost if wrong: none; Task 3 still adds tests for stream/parse.
- Task 1: Ruling: AI-usage log kept at docs/AI_USAGE_LOG.md, appended every task — owner instruction mid-run — cost if wrong: none.
- Task 3: Ruling: full-stream capture is ~250MB/min (as_der + chain); let the 30-min capture finish (137GB free), then compact to data/capture.jsonl without as_der/chain (replay needs names/issuer/dates only) and use the lite stream URL '/' for live ingest — cost if wrong: evidence cert.pem comes from the TLS fetch anyway, not CT DER.
- Task 4: Ruling: parse+serialise perf unit test uses best-of-5 with bar 6000/s (2x the 3000/s target) instead of my single-shot 9000/s — single runs swing 5.4k-9k/s while the capture shares the CPU — cost if wrong: a regression between 6k and 9k/s goes unflagged; end-to-end ingest rate is measured separately.
- Task 5: Ruling: allowlist size test >=99,000 not >=100,000 — 100k Tranco rows normalise to 99,627 registrable domains — cost if wrong: none.
- Task 5: Ruling: added data/shared_hosting.txt as extra PSL suffixes — 11 Tranco-ranked hosting platforms are absent from the PSL, so their phishing subdomains would be allowlisted — cost if wrong: a legit site on those platforms can become a candidate (never a verdict).
- Task 5: Ruling: bank.in allowlisted as a zone; tokens 'netbanking','axis','kite' not used — registry-restricted / too generic — cost if wrong: misses for brand tokens that only appear as 'axis'.
- Task 6: Ruling: lookalike skips segments that already contain an exact token; a segment shorter than the token gets max 1 edit — real FPs (growww.today, idfcbank.com, 1xbet-onlines.top) — cost if wrong: misses typosquats that delete 2 chars from a long token.
- Task 6: Ruling: segments split on [.-_] only, edge digits stripped for short-token match — hex 'vi0svszw' produced token 'vi' — cost if wrong: 'vi9kyc' style names miss the short token.
- Task 6: Ruling: brand-owned TLDs (.sbi/.jio/.amazon/.aws, IANA-verified) allowlisted; AWS service domains added to Amazon legit (NS awsdns) — cost if wrong: phishing hosted on a brand's own registry (not possible without the brand).
- Task 6: Ruling: ASCII-only homoglyph never matches a <=3-char token — 'vl'->'vi' noise — cost if wrong: misses 'sb1'-style digit swaps on 3-letter tokens (exact segment match on 'sbi1' still works).
- Task 6: Ruling: triage model loading deferred to Task 23 (rules-only now; no artifact exists) — YAGNI — cost if wrong: none.
- Task 6: Ruling: p99 latency reported as measured (4.8-5.3 ms on this laptop); release gate is the plan's mean < 5 ms — cost if wrong: report must not claim p99 < 5 ms.
- Task 7: Ruling: CP-SAT <1s gate measured on a campaign-shaped instance (must be OPTIMAL); the plan's random 400x30 instance needs 3-4s to prove optimality on 4 cores, so it runs with a 0.9s limit and must report FEASIBLE+gap and match greedy — cost if wrong: report must state FEASIBLE plans as not proven optimal.
- Task 8: Ruling: NPHARD §6 QUBO replaced by x-only 2nd-order inclusion-exclusion — spec penalty rewards over-coverage and its ground state can be the wrong plan (counter-example in tests) — cost if wrong: owner may prefer the spec form for presentation; qubit count drops 26 -> <=12 (contract example shows 24).
- Task 8: Ruling: reduce caps candidate NODES at min(C, max_vars) (x-only QUBO has one variable per node) instead of nodes+groups — follows from the formulation — cost if wrong: none.
- Task 10: Ruling: Merkle leaf = sha256(0x00||name||0x00||sha256(content)), nodes 0x01-prefixed — domain separation + name binding (rename/swap detected) — cost if wrong: none; roots are only compared with our own.
- Task 12: Ruling: ASN via Team Cymru DNS (DATA.md-listed) — pyasn needs MSVC on Windows — cost if wrong: one DNS round trip per IP instead of an offline lookup.
- Task 12: Ruling: TLS issuer from a verified stdlib handshake, PEM from an unverified one; no `cryptography` dependency — cost if wrong: issuer None for invalid chains (CT record still has it).
- Task 12: Ruling: >=1 strong but <2 strong -> stays candidate (not dismissed); weak-only -> dismissed — TRD defines only confirmed/dismissed/unreachable; dismissing on partial strong evidence would hide real phish — cost if wrong: more candidates kept in queue.
- Task 15: Ruling: seed uses .example (RFC 2606) names, RFC 5737 IPs, RFC 5398 ASNs, "(seed)" registrars — realistic .top names could belong to real registrants and the seed labels them confirmed phishing — cost if wrong: seed names look less realistic on screen.
- Task 15: Ruling: bulk writes via jsonb_to_recordset for seed and bundles (19 statements for 400 domains) — Supabase RTT 109 ms made per-row writes ~19 min — cost if wrong: none; single-domain live path uses the same code with a list of one.
- Task 16: Ruling: plan `kills` is marginal in rank order (sums to domains_killed), matching the contract example rather than schema comment "domains this target alone removes" — contract updated — cost if wrong: one column semantics.
- Task 16: Ruling: killed_domain_ids + notes stored as interdiction_plans columns (schema add column if not exists) — not in contract's schema — cost if wrong: none.
- Task 16: Ruling: SSE token bucket drops excess non-candidate events but makes candidates wait — DESIGN: candidates must surface — cost if wrong: a burst of candidates delays the feed slightly.
- Task 16: Ruling: stale heartbeat (>15 s) => connection 'down', rate 0 — DESIGN 'every degradation visible' — cost if wrong: none.
- Task 18: Ruling: ABIs exported to committed contracts/abi/ and deployments/localhost.json committed — a fresh Hardhat node deploys to deterministic addresses, and the API image must not need a Node build — cost if wrong: redeploy on a non-fresh chain needs the json regenerated.
- Task 18: Ruling: anchor_queue.next_attempt_at added for backoff (schema add column if not exists) — not in baseline schema — cost if wrong: none.
- Task 19: Ruling: return_path_mismatch / message_id_mismatch suppressed when DMARC passes — aligned DMARC explains third-party ESPs (legit sample l05) — cost if wrong: misses a weak signal on DMARC-passing attacker domains (they pass for their own domain anyway).
- Task 19: Ruling: Received anomaly = hop timestamps going backwards only (no per-hop ASN lookups) — keeps analysis offline and instant — cost if wrong: misses origin-ASN mismatch (weak signal).
- Task 20: Ruling: console dev port 5180 (5173 is used by another local project); API CORS default updated — cost if wrong: none.
- Task 21: Ruling: EvidenceViewer built in Task 21 (DomainDetail embeds it) instead of Task 22 — cost if wrong: none.
- Task 21: Ruling: campaign graph uses a deterministic radial preset layout instead of cose-bilkent — cose-bilkent 17-18 s / cose 21-23 s on the real 400-domain graph froze the tab 46 s — cost if wrong: DESIGN.md names cose-bilkent; the visual intent (single settle, static) is kept.
- Task 22: Ruling: QAOA runs in a dedicated worker process when hosted by the API (router.ISOLATE_QAOA, default False in the package) with a hard kill at timeout+2 s; worker start-up excluded from the solve budget and from solve_ms — measured 34 s in-process under API load vs 6.6-12 s isolated — cost if wrong: one extra process (~200 MB with Aer).
- Task 23: Ruling: trained LR not adopted — fails MODELS §7 hard checks (Tranco top-1k aws.dev/amazon.dev flagged, onlinesbi.sbi >= 0.1) and the triage release gate; triage stays on rules (provenance 'rules'); the model-scoring path in triage is NOT wired since no model passes — cost if wrong: none now; wiring needed if a future model passes.
- Task 23: Ruling: adoption gate adds the triage release-gate LEGIT/PHISH lists to MODELS §7's four checks — a model must not regress the release gate — cost if wrong: none.
- Task 24: Ruling: fetch() no longer retries httpx after Playwright returned Unreachable (only when Playwright itself fails) — measured p95 candidate->verdict 44.7 s from double timeouts — cost if wrong: a site that blocks headless Chromium but serves plain HTTP is not re-tried (it stays a candidate, never mis-judged).
- Task 24: Ruling: queue_depth.certs_raw = triage consumer lag + pending (was stream length) — cost if wrong: none.
- Task 25: Ruling: Task 25 and Task 26 started overlapping (deploy configs written while the live window ran); commits interleave in d...HEAD — cost if wrong: none.
- Final: Ruling: Docker base pinned to python:3.11-slim-bookworm — python:3.11-slim moved to Debian trixie, unsupported by Playwright 1.49 (build failed on ttf-unifont) — cost if wrong: none.
- Final: Ruling: I4 weak-only dismissed domains are not re-checked — dismissal needs a fetched page; re-checking every dismissal multiplies fetches — cost if wrong: a kit deployed later on a dismissed domain is missed until a new cert appears.
- Final: Ruling: I6 shared-infra IPs are dropped as takedown targets too, not only as clustering edges — a CDN anycast IP is not the attacker's host — cost if wrong: Cloudflare/AWS abuse desks are not offered as hosting targets.
- Final: Ruling: kit-hash floor 20 tags / 8 distinct (reviewer suggested ~30) — trivial pages measured at <=5 tags, the seed kit at 22/16 — cost if wrong: a 20-29 tag generic template could still link unrelated sites.
- Final: Ruling: I8 lookalike+homoglyph both firing is kept — it is what lifts pure homographs (xn--cicibank-shh.com etc.) over 0.45; pinned by tests; Cyrillic-s sbi.co.in (0.30) pinned as a KNOWN MISS pending owner decision — cost if wrong: one extra weight on homographs that also carry other signals.
- Final: Ruling: I11 API authentication deferred to the deploy decision — local demo only; DEPLOY.md says so — cost if wrong: an exposed deployment is open to anyone.
- Final: fixed candidate_at/verdict_at used transaction-start now() — test_candidate_stores_our_receipt_time RED→GREEN with clock_timestamp(); Ruling: test allows 1 s host/DB clock skew — cost if wrong: none (latencies are seconds).
- Task 26: Ruling: STREAM_MAXLEN 1,000,000 -> 500,000 — §7 smoke found XADD rejected (Redis 512 MB noeviction, 587 B/entry measured); pinned by test_stream_cap_fits_in_redis_memory; live stream trimmed after confirming lag 0 / pending 0 — cost if wrong: 4.5 min of backlog at 1,840 certs/s instead of 9.

## Platform (2026-10-09 / 10)

Owner-approved changes to earlier decisions are listed in spec `2026-10-09-multi-sector-platform-design.md` §9:
sealed, retrievable keys with every read-only key published on the home page; live candidates routed by sector; a
super admin password login; the public site served from the laptop through a quick tunnel; the Supabase publishable
key used by the console. Rulings made while building it:

- Ruling: response time counts each live domain once, with the verdict of whichever organisation checked it — with
  sector routing only one organisation checks a live domain, so per-organisation counting would split or double it —
  cost if wrong: figures are not comparable with the earlier Bank-One-only method.
- Ruling: the Supabase project URL and publishable key are committed in `apps/console/src/lib/publicConfig.ts`, not
  set as Vercel build variables — the hosted site failed to find the API without them, and both are public by design
  (row-level security: one readable row, no writes) — cost if wrong: anyone can read the current tunnel URL, which
  the public site exposes anyway.
- Ruling: https://q-cert-chain.vercel.app is in the API's default `CONSOLE_ORIGINS` — the line vanished from the local
  `.env` once and the public site broke — cost if wrong: one extra allowed origin; every call still needs a key.
- Ruling: a lost provisioning failure is logged on the existing 'system' channel rather than adding 'platform' to
  the `ops_log` check — no schema migration for a log label — cost if wrong: platform lines mix with system lines.
- Ruling: each sector's seeded campaigns get their own kit (a sector-specific block of tags in the seed page; the kit
  hash is the tag structure), and banking keeps the original kit — an e-commerce organisation's demo campaign turned
  up in a bank's kit-hash lookup; banking unchanged keeps the reports already on the ledger findable — cost if wrong:
  a demo needing a cross-sector kit match has none (real kits are not sector-bound).
- Ruling: CI pulls the official postgres and redis images from the AWS public mirror — Docker Hub's anonymous pull
  limit stopped the python and e2e jobs before any test ran — cost if wrong: the mirror can trail Docker Hub by hours.

## Live confirmation findings (2026-10-07, measured on the live CT feed)

- **Safety hole, fixed: one artifact could confirm a domain on its own.** While wiring the new S1 (exfiltration
  endpoint) and S2 (credential POST in the page's code) signals, one Telegram bot URL produced TWO strong signals
  (S1 saw the endpoint, S2 saw the cross-origin POST to it), so a page could reach "confirmed" on a single
  observation while the spec promises two independent signals. The same flaw existed one level up for every
  detector pair (a static form and the page's code POSTing to the same host). Impact had it shipped: confirmations
  resting on one piece of evidence, the exact failure the two-strong rule exists to prevent. Fix (S3b), one shared
  rule: every strong signal declares the artifacts it rests on (destination site, DOM hash, favicon hash); two count
  together only if they come from different detectors and share no artifact. Enforced in code
  (`confirm.independent_strong`) AND in the database (`has_two_independent_strong`, the `dv_confirmed_needs_two_strong`
  check). Pinned by test_one_exfil_endpoint_is_one_strong_signal_not_two, test_rule_is_shared_by_the_static_form_check_too,
  test_db_rejects_two_strong_signals_on_one_artifact, test_db_rejects_two_instances_of_one_detector.
- **Mislabel, fixed: 134 DNS failures reported as SSRF blocks.** The SSRF guard returned "resolves to a non-public
  address" for a name that does not resolve at all. The guard still fails closed; the reason is now `dns: ...`.
  Impact: the unreachable breakdown overstated SSRF rejections 34x (4 real, 134 NXDOMAIN) and hid that most of
  those candidates simply did not exist yet. Pinned by test_dns_failure_is_reported_as_dns_not_as_ssrf_block.
- **Backwards verdict, fixed: 9 pages behind Cloudflare's "Suspected Phishing" interstitial were DISMISSED.** Another
  system had already flagged them, which is corroboration, and the content was hidden from us, so it could not be
  judged at all. Now: not assessable (unreachable), still a candidate, rechecked; never a dismissal and never our
  evidence for a confirmation. Pinned by test_host_phishing_interstitial_is_not_assessable_never_dismissed.
- Ruling: S2 refinement (owner-approved) dropped requests fired during page load (5 of 6 gate false positives were
  analytics/telemetry) and requires a real hostname (the 6th was the string "https://www."). Re-gated once on the
  same set: 0 FP. Because that refinement was designed against the same pages, I added a held-out set (45 legitimate
  login pages never used in development) and ran it ONCE. Result: S1 0 FP; **S2 1 FP** (twitch.tv's own feature-flag
  bundle POSTs to eppo.cloud). Owner rule: any FP -> S2 ships MODERATE; S2 is not tuned again against the held-out
  set (that would make it a training set). Consequence, accepted by the owner: with S1 the only live-capable strong
  signal, live confirmations stay at or near zero, reported with the diagnosis. Cost if wrong: none for precision;
  recall on JS-era kits stays low until an independent second strong signal exists.
- Ruling: the kill switch can only LOWER a configured strength, never raise it — a runtime knob must not promote a
  signal past the false-positive gate — cost if wrong: raising a signal needs a config change and a commit.
- Ruling: one vote per detector (several S1 hits on different endpoints still count once) — the detectors share
  failure modes, so two hits from one heuristic are not independent evidence — cost if wrong: a page with two
  different exfil endpoints and nothing else stays a candidate.
- **Two overclaims in the draft report, caught against the measured data and corrected before publication.**
  (1) "The triage and campaign layers are demonstrably working at scale": clustering, takedown planning, evidence
  bundles and anchoring take CONFIRMED domains as their input (services/graph/build.py, pipeline.persist_result), and no
  live domain has been confirmed, so nothing live has reached the campaign layer; every campaign in the database is
  seeded (470 + 50 domains, `source: seed`). The draft's S3e sentence ("an unconfirmed domain can still be reached
  through its infrastructure") had the same flaw. Corrected: triage works on live traffic at scale; clustering and
  planning are demonstrated on seeded data; the live pipeline ends at the confirmation gate (not "at triage": live
  candidates are also fetched and assessed); reaching unconfirmed domains through a confirmed neighbour's
  infrastructure is named as future work, not claimed. (2) "Interdiction solved in 166 ms": no such figure is in the
  measured metrics; the report carries the measured CP-SAT values (131 ms median through the API; 58–228 ms median
  across k = 2..5 in the benchmark). Both claims came from the conversation, not from a measurement script.
- **Five local test failures under load (2026-10-08 night run), all explained and re-run; none is a code defect.**
  The full suite ran beside the S4 re-check on one laptop (database round trip p95 490 ms):
  (1) `test_latency_budgets_and_one_data_query_per_endpoint` failed the query-count rule: `org2 GET /candidates`
  ran 2 statements where 1 is allowed. Statements, captured: `select k.id, k.kind, k.org_id, o.slug from api_keys k
  left join organisations o on o.id = k.org_id where k.key_hash = :h and k.revoked_at is null` (the auth
  dependency's API-key lookup) and the single `org_domains` candidates query. Not a tenancy fallback (the org-2 path
  issues one statement) and not a serialization lazy load. Mechanism: the key lookup is cached for 30 s
  (`auth.CACHE_TTL_S`); under load a request took 2-60 s, so the cache expired inside a measured run. Proved by
  forcing the TTL to 0: every endpoint of both orgs rose by exactly one statement (lists 2, interdiction 3). Re-run
  alone on the idle machine: passed, every list/graph endpoint 1 data statement, interdiction 2 (its maximum).
  (2-5) `test_cpsat_hard_random_respects_time_limit_and_reports_gap` (1.8 s vs 1.5 s), `test_busy_host_process_does_
  not_slow_the_solve` (56 s vs 15 s), `test_hard_timeout_is_enforced_even_if_the_child_overruns` and
  `test_router_uses_isolated_process_when_enabled` (QAOA child timed out, router fell back to cpsat as designed):
  wall-clock assertions; packages/interdict unchanged since e9c2fa4; re-run alone on the idle machine: 6/6 passed.
  CI passed all five on 5baf70b. Latency BUDGETS were not enforced in any local run (round trip 130-660 ms, not
  co-located); they are enforced in CI. Proposed, not done: make the query-count rule ignore the auth lookup (or
  refresh the key cache before each measured run) so a slow machine cannot produce a false query-count failure.

## Deferred minor findings (whole-branch review)

- candidates flash red (flare keyframe) — spec conflict DESIGN.md vs CLAUDE.md §2.2, owner to rule
- CampaignRegistry.corroborate allows duplicate corroboration by one org
- AlreadyAnchored/AlreadyPublished path never records anchored_tx/ledger_events
- re-seeding with same label 500s; different labels merge into one campaign
- dismissed domains keep campaign_id; emptied campaigns keep stale counts
- ingest exits on non-dict JSON / non-string SAN (restart policy recovers)
- evidence artifacts lack nosniff + CSP sandbox headers
- /evidence/{id}/verify trusts stored collector_pk, does not check on-chain anchor
- concurrent QAOA calls share one worker; a queued call's timeout kills the running one
- IDN names shown only as U-label (show xn-- too)
- favicon_brand_match not suppressed when the final page is the brand's real site
- purge_raw_certs() never scheduled
- SSE heartbeat certs_per_sec not stale-checked
- Dockerfile fetches Tranco "latest", not the evaluated list 56WKN
- stray qcertchain.zip (spec copy) committed at repo root
- no API-level test for k=0 → 422
