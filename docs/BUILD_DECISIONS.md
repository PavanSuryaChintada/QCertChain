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
