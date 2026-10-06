# DESIGN — QCertChain

Visual and interaction spec. These tokens are locked. Do not invent values.

---

## 1. Direction

**Reference world:** a security operations console at 3am. Dense, fast-moving, read by someone who has been awake too long and must not misread a status.

**The one decision everything follows from:**

> **Colour means verdict. Nothing else gets colour.**

A candidate is grey. A confirmed phishing domain is red. Every other element — panels, rules, labels, buttons, type — is greyscale on a cool dark ground.

This is not aesthetic preference. **The most dangerous failure in this product is a judge, or a real analyst, reading a candidate as an accusation.** Colour discipline is what prevents it.

**Signature element:** the **certificate stream** — a live monospace ticker down the right rail, always visible, never collapsible. Raw certificates arriving in real time, most scrolling past in grey, the occasional one flaring. It is the proof that this is live and not a mockup.

---

## 2. Banned

Hard bans. If any appear, the design has failed.

- **Gradients.** No `linear-gradient`, no `radial-gradient`, no `bg-gradient-to-*`
- Glassmorphism, `backdrop-filter`, frosted panels
- Purple, violet, indigo, magenta
- Glow effects, coloured `box-shadow`
- `border-radius` above `2px`
- Emoji in the UI
- Drop shadows for elevation — use a hairline rule
- Animated backgrounds, particles, mesh, aurora
- shadcn defaults, Material, Bootstrap, DaisyUI
- Pill badges
- **Colour on a candidate**
- Any colour not in §3

---

## 3. Colour tokens

```css
:root {
  /* Ground — cool console slate, lifted off pure black so the
     verdict colours don't crush at the low end */
  --ground-000: #0E1417;   /* page */
  --ground-100: #151F24;   /* panel */
  --ground-200: #1C2A30;   /* raised: table header, active row */
  --ground-300: #263840;   /* hairline rules */
  --ground-400: #35525C;   /* disabled, inactive stroke */

  /* Ink — warm bone on cool ground */
  --ink-000:    #EFEAE0;   /* primary */
  --ink-100:    #C6C0B5;   /* body */
  --ink-200:    #97928A;   /* secondary */
  --ink-300:    #67645E;   /* tertiary, stream noise */

  /* VERDICT — the only chromatic vocabulary in the product */
  --v-candidate: #67645E;  /* grey. NOT a colour. This is the point. */
  --v-confirmed: #C0392B;  /* red — evidence-backed */
  --v-dismissed: #4A5D52;  /* muted green — cleared */
  --v-unreach:   #9A760C;  /* amber — could not determine */

  /* Campaign severity, used ONLY on the graph and campaign list */
  --sev-1: #C9A227;        /* < 10 domains */
  --sev-2: #D97B1F;        /* 10–99 */
  --sev-3: #C0392B;        /* 100–499 */
  --sev-4: #7A1E14;        /* 500+ */

  /* System state — never for emphasis */
  --state-live:  #4A7C59;
  --state-replay:#9A760C;  /* replay mode must be visually distinct */
  --state-down:  #C0392B;
}
```

**The candidate colour is grey on purpose.** If you find yourself wanting to make candidates orange so the demo looks more exciting, that is the exact instinct this rule exists to stop.

---

## 4. Type

```css
--font-display: "IBM Plex Sans Condensed", sans-serif;   /* 600 */
--font-body:    "IBM Plex Sans", sans-serif;             /* 400, 500 */
--font-data:    "IBM Plex Mono", monospace;              /* 400, 500 */
```

| Role | Face | Size / spacing |
|---|---|---|
| Section eyebrow | Condensed 600, uppercase | 11px / `0.12em` |
| Panel title | Condensed 600 | 15px / `0.02em` |
| Body | Plex Sans 400 | 14px / `1.5` |
| Secondary | Plex Sans 400 | 13px, `--ink-200` |
| **Domain names** | **Plex Mono 400** | **13px — always mono** |
| **All numerals** | **Plex Mono 500** | tabular, always |
| Hashes, IPs, ASNs | Plex Mono 400 | 12px |
| Stream lines | Plex Mono 400 | 11px / `1.4` |

**Domain names are always monospace.** This is a lookalike-detection product. `rn` versus `m`, `1` versus `l`, `0` versus `O` — in a proportional face those are genuinely hard to tell apart, which is the attack. Monospace makes them legible.

Scale: `11 · 12 · 13 · 14 · 15 · 18 · 22 · 28`. Nothing else.

---

## 5. Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ QCertChain      ● LIVE · 3,204/s      12 campaigns · 47 confirmed    [◼]  │  48px
├────────────┬──────────────────────────────────┬──────────────────────┤
│            │                                  │  CERTIFICATE STREAM  │
│  CAMPAIGNS │         GRAPH / DETAIL           │                      │
│            │                                  │ 03:02:11 shop.io     │
│  ■ CAMP-42 │      [ cytoscape canvas ]        │ 03:02:11 cdn-x.net   │
│    400 dom │                                  │ 03:02:12 icici-ver…  │ ← flare
│  ■ CAMP-38 │                                  │ 03:02:12 blog.de     │
│     87 dom │                                  │ 03:02:13 api.foo.io  │
│            │                                  │                      │
│  ────────  ├──────────────────────────────────┤                      │
│            │                                  │                      │
│  CANDIDATES│     PLAN / EVIDENCE PANEL        │                      │
│            │                                  │                      │
│   220px    │             fluid                │        300px         │
└────────────┴──────────────────────────────────┴──────────────────────┘
```

- 8px base grid. Every dimension a multiple.
- Panels separated by a 1px `--ground-300` rule. **No cards, no shadows, no gaps.** One continuous surface divided by rules.
- **The stream rail never collapses.** It is the signature and the liveness proof.
- Below 1100px: stream moves to a 120px bottom strip, still always visible.

---

## 6. Components

**Verdict chip** — 12px square, no radius, filled with the verdict colour, adjacent to the status word in mono. **Never colour alone.** A colour-blind analyst must read the word.

```
■ CANDIDATE     grey square + grey word
■ CONFIRMED     red square + red word
```

**Stream line**
```
03:02:12  icici-verify-kyc.top                    0.87
└─ mono    └─ mono, flares to --v-confirmed       └─ mono score
   --ink-300  on triage hit
```
New lines enter with an 80ms opacity fade. No slide, no bounce. Throttle rendering to ~20 lines/sec regardless of arrival rate — the browser will not survive 3,000/sec and the human cannot read it either.

**Confirmation panel** — screenshot thumbnail, the matched signals as a checklist with each signal's strength, and the verdict. **Every verdict shows its reasons.** A verdict with no visible reasoning is a bug.

**Campaign graph** — Cytoscape, cose-bilkent layout. Domain nodes 6px squares in verdict colour. Infrastructure nodes 12px squares in `--ink-200`. Edge opacity proportional to weight. **Takedown targets get a 2px `--ink-000` ring** — the only decorative stroke in the product, and it marks the answer.

**Plan panel**
```
TAKEDOWN PLAN                    backend: cpsat · 41 ms

  1  185.243.115.22      IP        kills 302
  2  ns1.cheapdns.top    NS        kills  61
  3  a4f2c9…  (kit)      HOST      kills  19
  4  AS20473             ASN       kills   5
  ────────────────────────────────────────────
     387 of 400 domains          96.7% coverage
```
Targets in rank order, mono throughout, kill counts right-aligned.

**Benchmark table** — one row per backend. The winning row gets a `--ink-000` left border, **whichever backend wins.** Do not style QAOA as the hero. The table's credibility is the point.

**Evidence viewer** — artifact list with hashes. On verify failure, the failing artifact row turns `--v-confirmed` and shows both hashes. This is the tamper demo; make it unmissable.

**Mode indicator** — header, always visible:
```
● LIVE · 3,204/s        --state-live
● REPLAY · capture.jsonl --state-replay
● RECONNECTING           --state-down
```
**Replay must be visually distinct from live.** Presenting replayed data as live, even accidentally, is the kind of thing that ends a hackathon run.

---

## 7. Motion

Almost none.

- Transitions: 120ms `ease-out`, opacity and background only. Never transform, never scale.
- Stream lines: 80ms opacity fade in.
- Graph layout: one 400ms settle on load, then static. **No continuous physics** — it makes the graph unreadable and burns CPU during the demo.
- Solving: 2px `--ink-200` indeterminate bar at the top of the plan panel, 1200ms cycle. No spinner.
- `prefers-reduced-motion`: everything instant.

**Banned:** page-load sequences, scroll reveals, hover lift, parallax, count-up numerals, skeleton shimmer.

---

## 8. Copy

Sentence case. Active voice. Plain verbs.

| Write | Not |
|---|---|
| Candidate — not yet verified | Suspicious! |
| Confirmed: cloned login, credentials POST to 185.243.115.22 | Malicious (94%) |
| Could not reach — still a candidate | Error |
| Take down 4 targets → 387 of 400 domains | Optimized solution found |
| qaoa timed out → cpsat | Fallback triggered |
| Report generated — not sent | Takedown initiated |

**Never write "malicious" without the evidence beside it.** Never write a confidence percentage as the whole verdict — a number without reasons is exactly the classifier output we exist to improve on.

Never write: leverage, seamless, powerful, cutting-edge, revolutionise, harness, unlock, empower.

---

## 9. Quantum in the UI

- The backend appears as a plain mono label: `cpsat` · `qaoa` · `annealing` · `greedy`. Lowercase, no badge, no icon.
- Default selection is `cpsat`.
- Fallbacks are stated, not hidden: `qaoa timed out → cpsat`.
- Benchmark shows real numbers including losses.
- Qubit count is a fact in the plan metadata: `24 variables · 24 qubits`.

**Nowhere does the word "quantum" appear next to a claim of speed or superiority.** No heading, no nav item, no purple, no lightning icon. Treated as an implementation detail shown honestly, it becomes more credible than any badge.

---

## 10. Quality floor

- Responsive to 1024px (analyst console — desktop-first is correct here)
- Visible keyboard focus: 2px `--ink-000` outline, 2px offset. Never `outline: none`.
- Contrast: `--ink-100` on `--ground-100` ≥ 7:1
- **Verdict never encoded by colour alone** — always paired with the status word
- **Mode never ambiguous** — live and replay are visually distinct at a glance
- All interactive elements ≥ 32px tall
- No layout shift when stream state changes — reserve the space
