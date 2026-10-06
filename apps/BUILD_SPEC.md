# BUILD SPEC — apps/console

Analyst console. Read `../CLAUDE.md` and `../docs/DESIGN.md` first — the design tokens are locked and the ban list is enforced.

---

## Build order

```
1. Shell + header + mode indicator      ← liveness proof, build first
2. Certificate stream rail (SSE)
3. Candidate list + detail panel
4. Campaign list + Cytoscape graph
5. Interdiction plan panel + benchmark
6. Evidence viewer + tamper demo
7. Second-org view + ledger provenance
8. Ops log
```

Items 1–2 are the credibility layer. A judge decides whether this is real in the first four seconds, and a live certificate ticker is what convinces them.

---

## Layout

```
apps/console/src/
├── App.tsx
├── layout/
│   ├── Header.tsx            mode indicator, counters
│   ├── LeftRail.tsx          campaigns + candidates
│   ├── Main.tsx              graph / detail
│   └── StreamRail.tsx        THE certificate ticker — never collapses
├── views/
│   ├── CampaignGraph.tsx     cytoscape
│   ├── DomainDetail.tsx      verdict + reasons + screenshot
│   ├── PlanPanel.tsx         targets, coverage, benchmark
│   ├── EvidenceViewer.tsx    artifacts, hashes, verify
│   ├── SecondOrg.tsx         inherited campaigns + provenance
│   └── OpsLog.tsx
├── components/
│   ├── VerdictChip.tsx       square + word. NEVER colour alone.
│   ├── ModeIndicator.tsx     live | replay | reconnecting
│   ├── StreamLine.tsx
│   ├── BenchmarkTable.tsx
│   └── Mono.tsx              wrapper: all domains and numerals
├── lib/
│   ├── api.ts                TanStack Query client
│   ├── sse.ts                EventSource + throttle
│   └── cyto.ts               graph styling
└── styles/tokens.css         from docs/DESIGN.md — do not edit values
```

---

## 1. Header and mode indicator

Always visible. Three states, visually distinct:

```
● LIVE · 3,204/s              --state-live
● REPLAY · capture.jsonl      --state-replay
● RECONNECTING                --state-down
```

**Replay must never look like live.** Different colour, different label, no ambiguity. Presenting replayed data as live — even accidentally — is the kind of thing that ends a run.

Counters: campaigns, confirmed domains, candidates, certs/sec.

---

## 2. Stream rail — the signature

Live monospace ticker. **Never collapsible.**

```
03:02:11  shop-example.io              0.02
03:02:11  cdn-assets.net               0.00
03:02:12  icici-verify-kyc.top         0.87   ← flares
03:02:12  blog.example.de              0.01
```

**Implementation**
- `EventSource` on `/certs/live`
- **Throttle rendering to ~20 lines/sec** regardless of arrival rate. Cap the DOM at 200 lines and drop from the tail.
- New lines: 80ms opacity fade. No slide.
- A triage hit flares to `--v-confirmed` briefly, then settles.
- Click a line → opens that domain's detail.

**Trap:** rendering every event at 3,000/sec will freeze the browser during your demo. Throttle server-side *and* client-side.

---

## 3. Verdict chip — the most important component

```tsx
<VerdictChip status="candidate" />   // grey square + "CANDIDATE"
<VerdictChip status="confirmed" />   // red square + "CONFIRMED"
```

**Rules, enforced:**
- Square + word, always. Never colour alone.
- **Candidate is grey.** Not orange, not yellow. If you want to make candidates colourful so the demo looks livelier, that is exactly the instinct `DESIGN.md` exists to stop.
- No pills, no radius above 2px.

---

## 4. Domain detail

Screenshot thumbnail, and the verdict with **every reason that produced it**:

```
■ CONFIRMED                         confidence 0.91

  ✓ strong   credential POST → 185.243.115.22 (not icicibank.com)
  ✓ strong   DOM structure matches known kit a4f2c9…
  ✓ moderate favicon matches ICICI brand asset
  ✓ weak     registered 3 days ago
```

**A verdict without visible reasons is a bug.** This is the entire difference between us and a classifier that outputs "94%".

Also show: triage score and its reasons, full enrichment, cert chain, raw CT record.

---

## 5. Campaign graph

Cytoscape with `cose-bilkent`.

- Domain nodes: 6px squares, verdict colour
- Infrastructure nodes: 12px squares, `--ink-200`, labelled by kind
- Edge opacity ∝ weight
- **Takedown targets: 2px `--ink-000` ring** — the only decorative stroke in the product, and it marks the answer

**Traps**
- **One 400ms settle on load, then `layout.stop()`.** Continuous physics makes the graph unreadable and burns CPU through the whole demo.
- Cap at 1,000 nodes. Above that, collapse domain nodes into a count badge per infrastructure node.
- Disable node dragging. An analyst dragging the layout apart mid-demo is a bad minute.

---

## 6. Plan panel

```
TAKEDOWN PLAN                     backend: cpsat · 41 ms

  1  185.243.115.22      IP        kills 302
  2  ns1.cheapdns.top    NS        kills  61
  3  a4f2c9…  (kit)      HOST      kills  19
  4  AS20473             ASN       kills   5
  ─────────────────────────────────────────────
     387 of 400 domains           96.7% coverage
```

- Mono throughout, kill counts right-aligned
- Budget `k` is a control — changing it re-solves
- Backend selector: `cpsat` default, `qaoa`, `annealing`, `greedy`
- Fallbacks shown as text: `qaoa timed out → cpsat`
- Hovering a target highlights the domains it kills in the graph

**Benchmark table** — one row per backend, winning row gets a `--ink-000` left border **whichever backend wins**. Do not style QAOA as the hero.

---

## 7. Evidence viewer — and the tamper demo

Artifact list with hashes:

```
  screenshot.png     3f2a91…    847 KB    ✓
  dom.html           a4f2c9…     31 KB    ✓
  headers.json       91bc4e…      2 KB    ✓
  cert.pem           7d1f02…      4 KB    ✓
  ──────────────────────────────────────────
  root               c8e1a4…              ✓ signature valid
```

On verify failure, the failing row turns `--v-confirmed` and shows **both** hashes:

```
  dom.html           a4f2c9…  expected
                     5e88b1…  found       ✗ TAMPERED
  ──────────────────────────────────────────
  root               MISMATCH             ✗
```

**Make this unmissable.** It is the beat that proves the cryptography is real rather than decorative.

---

## 8. Second-org view

A separate route (`/org2`) rendering as a different organisation.

- Starts empty
- Queries `/ledger/by-kit/{hash}`
- Campaign appears with **reporter address, timestamp, and corroboration count**
- Shows plainly: *"Inherited from ledger. No raw telemetry received."*

That last line is the point of the whole blockchain layer. Put it on screen.

---

## 9. Design enforcement

From `docs/DESIGN.md`, no exceptions:

- No gradients, no glassmorphism, no purple, no glow
- No `border-radius` above 2px, no emoji
- **All domain names in monospace** — `rn` vs `m` and `1` vs `l` are the attack
- All numerals monospace, tabular
- Verdict never colour alone
- Mode never ambiguous

Run a dedicated pass in Phase 6. Violations creep in under time pressure.

---

## 10. Copy

| Write | Not |
|---|---|
| Candidate — not yet verified | Suspicious! |
| Confirmed: cloned login, credentials POST to 185.243.115.22 | Malicious (94%) |
| Could not reach — still a candidate | Error |
| Take down 4 targets → 387 of 400 domains | Optimized solution found |
| qaoa timed out → cpsat | Fallback triggered |
| Report generated — not sent | Takedown initiated |

**Never write "malicious" without the evidence beside it.**

---

## 11. Tests

```
test_verdict_chip.tsx    candidate never renders a verdict colour
test_mode.tsx            replay and live are visually distinct
test_sse.ts              throttle holds at 20/sec under 3000/sec input
test_graph.ts            layout stops after settle; 1000-node cap enforced
```

`test_verdict_chip` is the important one. It guards the rule that matters most.
