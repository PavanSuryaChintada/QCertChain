# Explainers (Plan 1 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A viewer understands the console without the presenter: a **?** help panel on every page, a public
**Technical approach** page, and a guided **How it works** tour that walks the real pages with Back / Next step.

**Architecture:** All explainer text lives in data modules (`src/help/content.ts`, `src/explain/technical.ts`,
`src/tour/steps.ts`) so wording is reviewed in one place and tests can scan it. The ? is one component in the top
bar that picks its entry from the route. The tour is a context provider above the sign-in gate (so it survives
signing in) plus an overlay that finds `data-tour="…"` elements, highlights them and shows a step card. Console only:
no API change.

**Tech Stack:** Vite · React 18 · TypeScript · react-router-dom 6 · TanStack Query 5 · Vitest + Testing Library ·
Playwright (Python) for e2e.

**Spec:** `docs/superpowers/specs/2026-10-09-multi-sector-platform-design.md` §8b (approved 2026-10-09). Plans 2–4
(super admin and organisations; sector routing, chain accounts and seeded campaigns; quick-tunnel URL discovery) are
written after this one ships.

## Global Constraints

- **No new dependency** (npm or Python). The tour is built in the console.
- **Design rules enforced by `src/test/design.test.tsx`:** no border radius; no `gradient`, `backdrop-filter`,
  `text-shadow`, `drop-shadow`; **no emoji** (▶ and ◀ count as emoji: buttons say "Back" and "Next step" in words);
  no `outline: none`; `box-shadow` only via the `overlay` class (`var(--overlay-shadow)`); colours only as
  `var(--token)` from `tokens.css`; inline padding / margin / gap only 0, 4, 8, 12, 16, 24, 32 or 48; nav labels in
  sentence case; no "quantum" in a nav label or heading.
- **Content rules (spec §8b):** no measured number typed into explainer text (digits allowed only in `Ed25519`,
  `SHA-256`, `404`; live figures come from the API at run time); a candidate is "suspicious, not verified"; the
  takedown framing is used verbatim: *"Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in
  production; the same formulation runs on QAOA. Quantum is not in the critical path."*; "quantum" never in a heading,
  nav item or step title. Text describes only what exists today (Plan 2 updates the platform wording).
- **Explainers are public:** `/technical` renders without a key. The tour runs on live data, so signed out it asks
  for a key first (the one-click read-only sign-in arrives in Plan 2 with `GET /orgs/public`).
- **The tour only reads:** it issues GET requests only and clicks nothing.
- **Process (owner rules):** tests first (watch the test fail, then pass); commit and push to `main` after each task;
  **no `Co-Authored-By` or any AI attribution** in commits; `docs/AI_USAGE_LOG.md` updated in the last task.
- **The local demo keeps working:** after every task `npx tsc --noEmit` and `npx vitest run` pass in `apps/console`
  and the console on http://localhost:5180 (the owner's `npm run dev`, hot-reloading) still loads.
- Run console commands from `apps/console`; Python commands from the repo root with `PYTHONPATH=.` and
  `.venv/Scripts/python`.

## Review Focus

1. **A step's element appears late** (a cold campaign graph takes seconds on Supabase): the card first says what
   would be there, and the highlight still appears when the element arrives. Test in Task 5.
2. **Esc while a drawer is open** (the help panel or the domain drawer): closes the drawer, not the tour. Test in
   Task 5.
3. **Arrow keys inside a control that uses them** (text fields, the status filter's radio group, table rows): they
   act on the control and do not move the tour. Test in Task 5.
4. **The page scrolls or the window resizes mid-step:** the highlight follows its element. Test in Task 5.
5. **Storage blocked** (private window): the tour still runs, in memory. Test in Task 4.

---

## File structure

| File | Responsibility |
|---|---|
| `src/explain/framing.ts` (create) | The verbatim takedown framing sentence |
| `src/help/content.ts` (create) | Help text per route, `helpKeyFor(pathname)` |
| `src/help/HelpPanel.tsx` (create) | The ? button and its side panel |
| `src/explain/technical.ts` (create) | Technical approach sections |
| `src/views/Technical.tsx` (create) | The Technical approach page |
| `src/tour/steps.ts` (create) | Tour steps, live-value resolution (GET only) |
| `src/tour/TourProvider.tsx` (create) | Tour state, navigation, session persistence, `useTour` |
| `src/tour/TourOverlay.tsx` (create) | Highlight + step card + keys |
| `src/tour/TourStart.tsx` (create) | The `/tour` route: starts the tour |
| `src/test/textRules.ts` (create) | Test helpers: collect strings, detect measured numbers |
| `src/layout/Header.tsx` (modify) | ? in the top bar; breadcrumb labels for the new pages |
| `src/layout/KeyGate.tsx` (modify) | Public `/technical`, links and ? on the sign-in screen, tour note |
| `src/layout/LeftRail.tsx` (modify) | Nav: How it works, Technical approach |
| `src/App.tsx`, `src/main.tsx` (modify) | Routes, overlay, provider |
| `src/components/Page.tsx` (modify) | `Section` takes a `tour` anchor |
| `src/views/{Architecture,LiveQueue,CampaignView,EvidenceViewer,Ledger,Metrics}.tsx`, `src/components/ScoreBreakdown.tsx` (modify) | `data-tour` anchors; Ledger reads `?kit=` |
| `e2e/test_tour.py` (create), `scripts/e2e_stack.py` (modify) | Browser test of the tour and the ? panels |

---

### Task 1: Explainer text: framing, help content, route coverage

**Files:**
- Create: `apps/console/src/explain/framing.ts`
- Create: `apps/console/src/help/content.ts`
- Create: `apps/console/src/test/textRules.ts`
- Test: `apps/console/src/test/explainers.test.tsx` (create)

**Interfaces:**
- Produces: `FRAMING: string`; `HELP: Record<HelpKey, HelpEntry>`; `type HelpKey`; `interface HelpEntry { title: string; what: string; read: { label: string; text: string }[]; data: string; notClaimed: string }`; `helpKeyFor(pathname: string): HelpKey | null`; test helpers `strings(x: unknown): string[]`, `measuredNumber(s: string): boolean`.

- [ ] **Step 1: Write the test helpers**

`apps/console/src/test/textRules.ts`:

```ts
/** Every string inside a value, however deeply nested (help entries, sections, steps). */
export function strings(x: unknown): string[] {
  if (typeof x === "string") return [x];
  if (Array.isArray(x)) return x.flatMap(strings);
  if (x && typeof x === "object") return Object.values(x).flatMap(strings);
  return [];
}

// Names that contain digits but are not measurements.
const NOT_MEASUREMENTS = /Ed25519|SHA-256|404/g;

/** Explainer text never types a measured number (spec §8b): live figures come from the API at run time. */
export function measuredNumber(s: string): boolean {
  return /\d/.test(s.replace(NOT_MEASUREMENTS, ""));
}
```

- [ ] **Step 2: Write the failing tests**

`apps/console/src/test/explainers.test.tsx`:

```tsx
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { FRAMING } from "../explain/framing";
import { HELP, helpKeyFor } from "../help/content";
import { measuredNumber, strings } from "./textRules";

const APP = readFileSync(resolve(__dirname, "../App.tsx"), "utf8");

it("the takedown framing is the verbatim CLAUDE.md sentence", () => {
  expect(FRAMING).toBe(
    "Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.",
  );
});

it("every console route has a help entry", () => {
  const paths = [...APP.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((p) => p !== "*");
  expect(paths.length).toBeGreaterThanOrEqual(11);
  for (const p of paths) expect([p, helpKeyFor(p.replace(":id", "x"))]).not.toEqual([p, null]);
});

it("help keys follow the shape of the route", () => {
  expect(helpKeyFor("/")).toBe("/");
  expect(helpKeyFor("/queue")).toBe("/queue");
  expect(helpKeyFor("/campaigns/0b1c")).toBe("/campaigns/:id");
  expect(helpKeyFor("/evidence/d2eca4fc")).toBe("/evidence/:id");
  expect(helpKeyFor("/nowhere")).toBeNull();
});

it("help text types no measured number", () => {
  for (const s of strings(HELP)) expect([s, measuredNumber(s)]).toEqual([s, false]);
});

it("every entry has its four parts and no title mentions quantum", () => {
  for (const [k, e] of Object.entries(HELP)) {
    expect([k, e.title.toLowerCase().includes("quantum")]).toEqual([k, false]);
    expect([k, !!e.what && e.read.length > 0 && !!e.data && !!e.notClaimed]).toEqual([k, true]);
  }
});
```

- [ ] **Step 3: Run it to see it fail**

Run: `cd apps/console && npx vitest run src/test/explainers.test.tsx`
Expected: FAIL: `Failed to resolve import "../explain/framing"`.

- [ ] **Step 4: Write the framing and the help content**

`apps/console/src/explain/framing.ts`:

```ts
/** CLAUDE.md §2.3: wherever takedown selection and QAOA are mentioned, this sentence is used verbatim. */
export const FRAMING =
  "Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.";
```

`apps/console/src/help/content.ts`:

```ts
import { FRAMING } from "../explain/framing";

/** What the ? panel says about one page. Plain words; no measured numbers (spec §8b). */
export interface HelpEntry {
  title: string;
  what: string;
  read: { label: string; text: string }[];
  data: string;
  notClaimed: string;
}

const HELP_ENTRIES = {
  "/": {
    title: "Architecture",
    what: "The whole pipeline on one diagram, from the certificate stream to the console, with each stage's live status.",
    read: [
      { label: "Boxes", text: "Dashed grey boxes are inputs, white boxes are pipeline stages, and boxes with a thick left edge store records. Click a box to open its page." },
      { label: "Status squares", text: "Filled means ok, half-filled degraded, crossed and grey failed, hollow no report yet. Failed is grey on purpose: a failing system is not a threat." },
      { label: "Figures on the arrows", text: "Certificates per second entering triage, candidates per hour leaving it, and confirmations per hour leaving confirmation." },
      { label: "The three panels", text: "Three positions the database itself enforces: nothing is ever sent, two strong signals are needed to confirm, and only hashes go on chain." },
    ],
    data: "One batched status request every five seconds, answered by the API from the database, Redis and the chain.",
    notClaimed: "A filled square means the stage reported in and is keeping up. It does not mean anything malicious was found.",
  },
  "/queue": {
    title: "Live queue",
    what: "Every domain triage has nominated, newest first, from the certificate stream and from links in analysed emails.",
    read: [
      { label: "Status filter", text: "All, candidates, confirmed or dismissed, with a count on each. A candidate is suspicious, not verified." },
      { label: "Triage score", text: "Hover it for the breakdown: the brand it imitates, keywords, the top-level domain and confusable characters. Above the threshold, a name becomes a candidate." },
      { label: "Rows", text: "Click a row, or press Enter on it, to open the domain: why triage nominated it, what enrichment found, and the confirmation signals." },
      { label: "New rows", text: "While the pointer is over the table, new rows wait behind a bar so the list does not move under you. Click the bar to show them." },
    ],
    data: "Candidates from the certificate stream and from links in analysed emails, refreshed every five seconds.",
    notClaimed: "A candidate is not an accusation. Only a confirmed domain, with two independent strong signals found on its fetched page, is treated as phishing, and candidates are never shown in red.",
  },
  "/campaigns": {
    title: "Campaigns",
    what: "Confirmed domains grouped into campaigns by the infrastructure they share.",
    read: [
      { label: "Each row", text: "One campaign: how many domains and infrastructure nodes it has, its confidence, and when it was first seen. Open it to see the graph and plan the takedowns." },
      { label: "Confidence", text: "How sure the clustering is that these domains belong to one operation." },
    ],
    data: "Your organisation's campaigns only. Other organisations' campaigns do not exist for you.",
    notClaimed: "A campaign groups confirmed domains by shared infrastructure. It does not name the attacker.",
  },
  "/campaigns/:id": {
    title: "Campaign",
    what: "One campaign: the graph of its domains and shared infrastructure, the takedown plan for a budget, and the solvers compared.",
    read: [
      { label: "Graph", text: "Domains around the infrastructure they share. Filled squares are takedown targets (hosting address, nameserver, registrar). Dashed circles are evidence only, such as kit and favicon hashes: nobody can take down a hash." },
      { label: "Takedown budget", text: "Choose how many takedowns you can ask for. Targets light up and the domains they cover go dark. The coverage curve flattens towards the reachable line, because some domains sit only on infrastructure no takedown reaches." },
      { label: "Why this plan", text: "Each target, whom to ask (hosting abuse, DNS abuse or registrar suspension), and the domains it covers." },
      { label: "Solvers", text: "The same problem solved several ways, with domains covered, targets chosen, time taken and the gap to CP-SAT. Run again solves it live." },
      { label: "Solver formulation", text: "The QUBO the problem becomes: its variables, the qubits and circuit depth it needs, and what the reduction removed first." },
    ],
    data: "The campaign graph, the coverage for each budget and the solver benchmark, computed by the API for your organisation's campaign.",
    notClaimed: `${FRAMING} No takedown request is ever submitted.`,
  },
  "/evidence": {
    title: "Evidence",
    what: "Where evidence bundles open. A bundle is built for each confirmed domain.",
    read: [{ label: "Bundle id", text: "Enter a bundle id, or open a bundle from a confirmed domain's detail in the live queue." }],
    data: "Your organisation's bundles only.",
    notClaimed: "Only hashes are anchored on the ledger, never the evidence itself.",
  },
  "/evidence/:id": {
    title: "Evidence bundle",
    what: "Everything kept for one confirmed domain, how it is sealed against tampering, and the abuse report generated from it.",
    read: [
      { label: "Bundle contents", text: "Each artifact (screenshot, page, certificate, DNS and WHOIS records) with its SHA-256 hash and size." },
      { label: "Merkle tree", text: "The artifact hashes combined in pairs up to a single root, which is signed with Ed25519." },
      { label: "Verify", text: "Recomputes the root from the stored bytes, checks the signature and compares the root with the copy anchored on the chain. Tamper flips one byte in memory to show the check failing; the stored evidence is never touched. Restore undoes it." },
      { label: "Attestations", text: "Which organisations confirmed or disputed this evidence on the chain." },
      { label: "Abuse report", text: "The request generated for the hosting provider, DNS provider or registrar, marked not sent." },
    ],
    data: "The bundle from your organisation's evidence store, and its anchor transaction on the chain.",
    notClaimed: "The report is generated for review and never sent. A bundle missing an artifact, such as a screenshot, is marked partial.",
  },
  "/email": {
    title: "Email analyzer",
    what: "Paste the headers of a suspicious email, or the whole message, to see whether it is spoofed and where its links lead.",
    read: [
      { label: "Parsed headers", text: "Sender, return path, the relays it passed through, and the SPF, DKIM and DMARC results with pass or fail." },
      { label: "Signals", text: "What the headers reveal, by strength. The rule is the same as for domains: an email is malicious only with two strong signals." },
      { label: "Extracted link domains", text: "Each link's domain with its triage score. A new one becomes a candidate in the live queue, and when it is confirmed this email is re-scored automatically." },
      { label: "Recent analyses", text: "Your organisation's earlier analyses." },
    ],
    data: "Only what you paste or drop here. Nothing connects to a mailbox; message bodies are read for links and are not stored.",
    notClaimed: "Suspicious is not malicious: with fewer than two strong signals the verdict stays suspicious.",
  },
  "/ledger": {
    title: "Ledger",
    what: "The shared chain: what your organisation anchored and published, and lookups across organisations by kit hash.",
    read: [
      { label: "Kit-hash lookup", text: "Paste the hash of a phishing kit seen on one of your domains. The result lists every organisation that published a campaign built with that kit: domain count, confidence, reporter and time. Corroborate or Dispute records your organisation's answer on the chain, signed with its own key." },
      { label: "Anchored records", text: "Everything your organisation wrote to the chain, with transaction hashes." },
    ],
    data: "The permissioned demo chain, read through the API. Writes wait in a queue while the chain is unreachable.",
    notClaimed: "Only hashes, counts and who reported them are shared. Domain names, addresses and page content never leave the organisation.",
  },
  "/metrics": {
    title: "Metrics",
    what: "How the system measures up: triage precision and recall, the threshold sweep, lead time, response time per stage, and the interdiction, evidence and ledger figures.",
    read: [
      { label: "Triage precision", text: "Precision at a realistic base rate, worked out from the measured false-positive rate and recall, not from a balanced test set." },
      { label: "Threshold sweep", text: "Recall, false positives and candidates per hour at each threshold. A lower threshold costs page fetches, not accusations." },
      { label: "Lead time", text: "How much earlier a domain appears in Certificate Transparency than in a public phishing feed, or why it has not been measured yet." },
      { label: "Per-stage response time", text: "From certificate seen to candidate, confirmed, campaign, plan, bundle and anchor." },
    ],
    data: "Measurement scripts write one metrics file; this page and the written report are both rendered from it.",
    notClaimed: "A figure that could not be measured says so instead of showing an estimate.",
  },
  "/health": {
    title: "System health",
    what: "Whether each component is up, how fast the API answers, and where everything runs.",
    read: [
      { label: "Components", text: "Each stage's status, with the reason when it is degraded or failed." },
      { label: "Endpoint latency", text: "Median and slow-tail response time for each API endpoint over the last few minutes." },
      { label: "Queues and regions", text: "Queue depths, the database round trip, and the regions of the API and the database." },
    ],
    data: "The same status request as the top bar, every five seconds.",
    notClaimed: "Failed is grey: a failing system is not a threat.",
  },
  "/ops": {
    title: "Ops log",
    what: "Every degradation the system hits, written as it happens.",
    read: [
      { label: "Channel", text: "Show entries from one component only." },
      { label: "Entries", text: "Newest first, with severity and context." },
    ],
    data: "An append-only log in the database.",
    notClaimed: "An entry is an operational event, not a security finding.",
  },
  "/technical": {
    title: "Technical approach",
    what: "How QCertChain works and why it is built this way, on one page.",
    read: [
      { label: "Sections", text: "The problem, the five stages, choosing the takedowns, evidence, the shared ledger, organisations, how it is served, and what it does not do." },
      { label: "Diagram", text: "The same pipeline diagram as the Architecture page, without live status." },
    ],
    data: "A written description. Live figures are on the Metrics page.",
    notClaimed: "It describes the design. Measured results are only on the Metrics page and in the report.",
  },
  "/tour": {
    title: "How it works",
    what: "A guided tour of the real console: each step opens a page and highlights the part that matters.",
    read: [
      { label: "Controls", text: "Next step and Back move through the tour. The arrow keys do the same, and Esc ends it." },
      { label: "Live data", text: "Each step uses your organisation's real data. The tour only highlights; it changes nothing." },
    ],
    data: "Your organisation's campaigns, evidence and ledger, read with your key when the tour starts.",
    notClaimed: "Figures in the tour are read live when it starts; they are not fixed claims.",
  },
  signin: {
    title: "Sign in",
    what: "Several organisations share QCertChain. Your key decides which organisation you are and which data exists for you.",
    read: [
      { label: "API key", text: "Paste your organisation's key. The read-only demo key shows everything and changes nothing." },
      { label: "Technical approach", text: "Open without a key: how the system works and why it is built this way." },
      { label: "How it works", text: "A guided tour of the live console. Sign in first; the tour starts on its own." },
    ],
    data: "The API checks each key; only a hash of each key is stored.",
    notClaimed: "Signing in with the demo key never changes any data.",
  },
} satisfies Record<string, HelpEntry>;

export type HelpKey = keyof typeof HELP_ENTRIES;
export const HELP: Record<HelpKey, HelpEntry> = HELP_ENTRIES;

/** The help entry for a pathname: `/`, `/section`, or `/section/:id` for any detail page. */
export function helpKeyFor(pathname: string): HelpKey | null {
  const parts = pathname.split("/").filter(Boolean);
  const key = parts.length === 0 ? "/" : parts.length === 1 ? `/${parts[0]}` : `/${parts[0]}/:id`;
  return key in HELP ? (key as HelpKey) : null;
}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd apps/console && npx vitest run src/test/explainers.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the whole console suite and the typecheck**

Run: `cd apps/console && npx tsc --noEmit && npx vitest run`
Expected: typecheck clean; all tests pass (the 60 existing + 5 new).

- [ ] **Step 7: Commit and push**

```bash
git add apps/console/src/explain/framing.ts apps/console/src/help/content.ts apps/console/src/test/textRules.ts apps/console/src/test/explainers.test.tsx
git commit -m "Console explainers: help text for every page in one module, the verbatim takedown framing, and tests for route coverage and no typed measurements"
git push origin main
```

---

### Task 2: The ? help panel in the top bar

**Files:**
- Create: `apps/console/src/help/HelpPanel.tsx`
- Modify: `apps/console/src/layout/Header.tsx` (imports; the right-hand div ends with the `Key` stat)
- Test: `apps/console/src/test/help.test.tsx` (create)

**Interfaces:**
- Consumes: `HELP`, `helpKeyFor`, `HelpEntry`, `HelpKey` (Task 1); `Button`, `Drawer` (existing).
- Produces: `HelpButton({ entryKey?: HelpKey })`: renders a `?` button (`data-testid="help-button"`, accessible name `Help: <title>`) and a drawer titled `About this page: <title>`; `HelpBody({ entry })`.

- [ ] **Step 1: Write the failing tests**

`apps/console/src/test/help.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { Link } from "react-router-dom";
import { HelpButton } from "../help/HelpPanel";
import { Header } from "../layout/Header";
import { json, renderWith } from "./fixtures";

afterEach(() => vi.restoreAllMocks());

it("the ? opens the current page's explanation with its four parts, and Esc closes it", () => {
  renderWith(<HelpButton />, { route: "/queue" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Live queue" }));
  expect(screen.getByRole("dialog", { name: "About this page: Live queue" })).toBeInTheDocument();
  for (const h of ["What this page is", "How to read it", "Where the data comes from", "What it does not claim"])
    expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("a detail page gets its own entry", () => {
  renderWith(<HelpButton />, { route: "/campaigns/c1" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Campaign" }));
  expect(screen.getByText(/Filled squares are takedown targets/)).toBeInTheDocument();
});

it("the panel closes when the page changes, and the ? then explains the new page", () => {
  renderWith(<><HelpButton /><Link to="/ledger">go</Link></>, { route: "/queue" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Live queue" }));
  fireEvent.click(screen.getByText("go"));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button", { name: "Help: Ledger" })).toBeInTheDocument();
});

it("a page without an entry shows no ?", () => {
  renderWith(<HelpButton />, { route: "/nowhere" });
  expect(screen.queryByTestId("help-button")).toBeNull();
});

it("the top bar carries the ?", () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}, 500));
  renderWith(<Header />, { route: "/metrics" });
  expect(screen.getByRole("button", { name: "Help: Metrics" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/console && npx vitest run src/test/help.test.tsx`
Expected: FAIL: `Failed to resolve import "../help/HelpPanel"`.

- [ ] **Step 3: Write the panel**

`apps/console/src/help/HelpPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "../components/Button";
import { Drawer } from "../components/Drawer";
import { HELP, helpKeyFor, type HelpEntry, type HelpKey } from "./content";

export function HelpBody({ entry }: { entry: HelpEntry }) {
  return (
    <div className="prose">
      <h3 className="t-section">What this page is</h3>
      <p style={{ marginTop: 8 }}>{entry.what}</p>
      <h3 className="t-section" style={{ marginTop: 24 }}>How to read it</h3>
      <dl style={{ marginTop: 8 }}>
        {entry.read.map((r) => (
          <div key={r.label} style={{ marginTop: 12 }}>
            <dt style={{ fontWeight: 500 }}>{r.label}</dt>
            <dd className="ink-2" style={{ marginTop: 4 }}>{r.text}</dd>
          </div>
        ))}
      </dl>
      <h3 className="t-section" style={{ marginTop: 24 }}>Where the data comes from</h3>
      <p style={{ marginTop: 8 }}>{entry.data}</p>
      <h3 className="t-section" style={{ marginTop: 24 }}>What it does not claim</h3>
      <p style={{ marginTop: 8 }}>{entry.notClaimed}</p>
    </div>
  );
}

/** The ? that explains the current page. `entryKey` pins an entry for screens outside the routes (sign-in). */
export function HelpButton({ entryKey }: { entryKey?: HelpKey }) {
  const { pathname } = useLocation();
  const key = entryKey ?? helpKeyFor(pathname);
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [pathname]);
  if (!key) return null;
  const entry = HELP[key];
  return (
    <>
      <Button size="sm" iconLabel={`Help: ${entry.title}`} onClick={() => setOpen(true)} data-testid="help-button">?</Button>
      <Drawer open={open} title={`About this page: ${entry.title}`} onClose={() => setOpen(false)}>
        <HelpBody entry={entry} />
      </Drawer>
    </>
  );
}
```

- [ ] **Step 4: Put the ? in the top bar**

In `apps/console/src/layout/Header.tsx` add the import after the existing imports:

```tsx
import { HelpButton } from "../help/HelpPanel";
```

and replace

```tsx
        <Stat label="Key">{data ? KEY_KIND[data.key_kind] ?? data.key_kind : "–"}</Stat>
      </div>
```

with

```tsx
        <Stat label="Key">{data ? KEY_KIND[data.key_kind] ?? data.key_kind : "–"}</Stat>
        <HelpButton />
      </div>
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd apps/console && npx vitest run src/test/help.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 6: Whole suite, typecheck, and a look at the running console**

Run: `cd apps/console && npx tsc --noEmit && npx vitest run`
Expected: all pass, including `design.test.tsx` (no new colours, spacing or radius).
Then open http://localhost:5180/queue (the dev server hot-reloads): the `?` sits at the right end of the top bar and
opens the Live queue explanation.

- [ ] **Step 7: Commit and push**

```bash
git add apps/console/src/help/HelpPanel.tsx apps/console/src/layout/Header.tsx apps/console/src/test/help.test.tsx
git commit -m "Console: a ? in the top bar opens an explanation of the current page (what it is, how to read it, where the data comes from, what it does not claim)"
git push origin main
```

---

### Task 3: Technical approach page, public, linked from sign-in and the rail

**Files:**
- Create: `apps/console/src/explain/technical.ts`
- Create: `apps/console/src/views/Technical.tsx`
- Modify: `apps/console/src/views/Architecture.tsx:113` (`function Legend` → exported)
- Modify: `apps/console/src/layout/KeyGate.tsx` (whole file below)
- Modify: `apps/console/src/App.tsx` (import + route)
- Modify: `apps/console/src/layout/LeftRail.tsx` (`NAV`)
- Modify: `apps/console/src/layout/Header.tsx` (`SECTION` labels)
- Modify: `apps/console/src/test/auth.test.tsx` (the KeyGate test now needs a router)
- Test: `apps/console/src/test/technical.test.tsx` (create)

**Interfaces:**
- Consumes: `FRAMING` (Task 1), `HelpButton` (Task 2), `ArchitectureDiagram`, `Legend`, `PageHeader`, `Section`.
- Produces: `TECHNICAL: TechSection[]` with `interface TechSection { id: string; title: string; paragraphs: string[] }`; `TechnicalPage()`; `PUBLIC_PATHS: string[]` in KeyGate; the sign-in screen's tour note `data-testid="tour-note"`.

- [ ] **Step 1: Write the failing tests**

`apps/console/src/test/technical.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FRAMING } from "../explain/framing";
import { TECHNICAL } from "../explain/technical";
import { KeyGate } from "../layout/KeyGate";
import { NAV } from "../layout/LeftRail";
import { setKey } from "../lib/auth";
import { TechnicalPage } from "../views/Technical";
import { renderWith } from "./fixtures";
import { measuredNumber, strings } from "./textRules";

afterEach(() => { setKey(null); vi.restoreAllMocks(); });

function gate(route: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[route]}><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
}

it("the Technical approach page opens without a key", () => {
  gate("/technical");
  expect(screen.getByRole("heading", { level: 1, name: "Technical approach" })).toBeInTheDocument();
  expect(screen.queryByLabelText("API key")).toBeNull();
  expect(screen.queryByText("console body")).toBeNull();
});

it("the sign-in screen links to both explainers and carries a ?", () => {
  gate("/");
  expect(screen.getByRole("link", { name: "Technical approach" })).toHaveAttribute("href", "/technical");
  expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/tour");
  expect(screen.getByRole("button", { name: "Help: Sign in" })).toBeInTheDocument();
});

it("opening the tour signed out says it needs a key, and offers the sign-in", () => {
  gate("/tour");
  expect(screen.getByTestId("tour-note")).toHaveTextContent("read-only demo key");
  expect(screen.getByLabelText("API key")).toBeInTheDocument();
});

it("the page states the takedown framing verbatim and no heading says quantum", () => {
  renderWith(<TechnicalPage />, { route: "/technical" });
  expect(screen.getByText(FRAMING)).toBeInTheDocument();
  screen.getAllByRole("heading").forEach((h) => expect(h.textContent!.toLowerCase()).not.toContain("quantum"));
});

it("Technical approach text types no measured number", () => {
  for (const s of strings(TECHNICAL)) expect([s, measuredNumber(s)]).toEqual([s, false]);
});

it("the left rail offers the Technical approach", () => {
  expect(NAV.map((n) => n.label)).toContain("Technical approach");
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/console && npx vitest run src/test/technical.test.tsx`
Expected: FAIL: `Failed to resolve import "../explain/technical"`.

- [ ] **Step 3: Write the Technical approach text**

`apps/console/src/explain/technical.ts`:

```ts
import { FRAMING } from "./framing";

export interface TechSection { id: string; title: string; paragraphs: string[] }

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
    paragraphs: [
      "For a confirmed domain the system keeps the screenshot, the page, the certificate, and the DNS and WHOIS records. Each is hashed with SHA-256, the hashes form a Merkle tree, and the root is signed with Ed25519.",
      "Changing a single byte of any artifact changes the root, so the signature and the anchored copy no longer match. The Verify button on every bundle checks exactly that.",
    ],
  },
  {
    id: "ledger",
    title: "The shared ledger",
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
    paragraphs: [
      "Phishing served over plain HTTP has no certificate and is invisible here. A wildcard certificate hides the phishing subdomain behind the wildcard.",
      "On live data the pipeline currently ends at the confirmation gate: modern phishing kits are JavaScript applications, so the original strong signals rarely fire. The Metrics page shows how many live domains have been confirmed and why. Campaigns, interdiction and evidence are demonstrated on seeded campaigns.",
      "No abuse report is ever sent. Reports are generated for review only.",
    ],
  },
];
```

- [ ] **Step 4: Export the legend, write the page**

In `apps/console/src/views/Architecture.tsx` change `function Legend() {` to `export function Legend() {`.

`apps/console/src/views/Technical.tsx`:

```tsx
import { Link } from "react-router-dom";
import { PageHeader, Section } from "../components/Page";
import { TECHNICAL } from "../explain/technical";
import { ArchitectureDiagram, Legend } from "./Architecture";

/** How the system works and why. Open without a key; measured figures live on the Metrics page, not here. */
export function TechnicalPage() {
  return (
    <div>
      <PageHeader title="Technical approach" meta="How QCertChain works and why it is built this way. Measured results are on the Metrics page." />
      <section className="panel" style={{ padding: 16, marginBottom: 24 }} aria-label="Pipeline diagram">
        <ArchitectureDiagram status={undefined} />
        <Legend />
      </section>
      {TECHNICAL.map((s) => (
        <Section key={s.id} id={`tech-${s.id}`} title={s.title}>
          {s.paragraphs.map((p, i) => <p key={i} className="prose" style={{ marginTop: i === 0 ? 0 : 12 }}>{p}</p>)}
        </Section>
      ))}
      <p className="prose ink-2"><Link className="link" to="/tour">Take the guided tour</Link> to see each stage on live data.</p>
    </div>
  );
}
```

- [ ] **Step 5: Open `/technical` to everyone, link it from the sign-in screen**

Replace `apps/console/src/layout/KeyGate.tsx` with:

```tsx
import { type ReactNode, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { getKey, onKeyChange, setKey } from "../lib/auth";
import { prefetchDemoPath } from "../lib/prefetch";
import { HelpButton } from "../help/HelpPanel";
import { TechnicalPage } from "../views/Technical";

/** Pages anyone may read without a key: they explain the system and hold no organisation data. */
export const PUBLIC_PATHS = ["/technical"];

function PublicShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="topbar" style={{ left: 0 }}>
        <Link to="/" className="link" style={{ textDecoration: "none", fontWeight: 500 }}>QCertChain</Link>
        <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
          <Link to="/" className="link">Sign in</Link>
          <HelpButton />
        </div>
      </header>
      <main className="main" style={{ marginLeft: 0 }}><div className="content">{children}</div></main>
    </>
  );
}

/** Nothing of the console renders without an API key: the key decides which organisation's data exists. */
export function KeyGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const [key, setLocal] = useState(getKey());
  const [draft, setDraft] = useState("");
  useEffect(() => onKeyChange(() => { setLocal(getKey()); qc.clear(); }), [qc]);
  // warm the demo path once per signed-in key, so each page opens from cache (best-effort, never errors)
  useEffect(() => { if (key) void prefetchDemoPath(qc); }, [key, qc]);
  if (key) return <>{children}</>;
  if (PUBLIC_PATHS.includes(pathname)) return <PublicShell><TechnicalPage /></PublicShell>;
  return (
    <main style={{ padding: 48, maxWidth: 640 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <h1 className="t-display">QCertChain console</h1>
        <div style={{ marginLeft: "auto" }}><HelpButton entryKey="signin" /></div>
      </div>
      {pathname === "/tour" && (
        <p className="prose" style={{ marginTop: 16 }} data-testid="tour-note">
          The guided tour runs on live data, so it needs a key. Sign in with any organisation key, including the read-only demo key, and the tour starts.
        </p>
      )}
      <p className="ink-2 prose" style={{ marginTop: 8 }}>
        Enter your organisation's API key. The key decides which organisation you are: its campaigns, evidence and
        analyses are the only ones that exist for you. To switch organisation, sign out and use another key.
      </p>
      <form style={{ marginTop: 24, display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setKey(draft.trim()); }}>
        <label htmlFor="apikey" className="sr-only">API key</label>
        <input id="apikey" className="input mono" style={{ flex: 1 }} type="password" autoComplete="off" placeholder="qcc_org_..."
               value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>Sign in</button>
      </form>
      <p className="prose ink-2" style={{ marginTop: 24 }}>
        New here? Read the <Link className="link" to="/technical">Technical approach</Link>, or sign in and take the guided
        tour: <Link className="link" to="/tour">How it works</Link>.
      </p>
    </main>
  );
}
```

- [ ] **Step 6: Route, nav entry, breadcrumb label**

In `apps/console/src/App.tsx` add `import { TechnicalPage } from "./views/Technical";` with the other view imports,
and add `<Route path="/technical" element={<TechnicalPage />} />` directly after the `"/"` route.

In `apps/console/src/layout/LeftRail.tsx` replace the first `NAV` line

```ts
  { to: "/", label: "Architecture", end: true },
```

with

```ts
  { to: "/", label: "Architecture", end: true },
  { to: "/technical", label: "Technical approach" },
```

In `apps/console/src/layout/Header.tsx` replace `metrics: "Metrics", health: "System health", ops: "Ops log",` with
`metrics: "Metrics", health: "System health", ops: "Ops log", technical: "Technical approach", tour: "How it works",`.

- [ ] **Step 7: The existing KeyGate test now needs a router**

In `apps/console/src/test/auth.test.tsx` add `import { MemoryRouter } from "react-router-dom";` and in the test
`renders nothing of the console without a key, then the console once signed in` replace

```tsx
      <KeyGate><p>console body</p></KeyGate>
```

with

```tsx
      <MemoryRouter><KeyGate><p>console body</p></KeyGate></MemoryRouter>
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd apps/console && npx vitest run src/test/technical.test.tsx src/test/auth.test.tsx src/test/explainers.test.tsx`
Expected: PASS. `explainers.test.tsx` now also covers the new `/technical` route.

- [ ] **Step 9: Whole suite, typecheck, a look signed out**

Run: `cd apps/console && npx tsc --noEmit && npx vitest run`
Expected: all pass (`design.test.tsx` checks the new nav label is sentence case with no "quantum").
Then, in a private browser window, open http://localhost:5180/technical: the page renders without signing in.

- [ ] **Step 10: Commit and push**

```bash
git add apps/console/src/explain/technical.ts apps/console/src/views/Technical.tsx apps/console/src/views/Architecture.tsx apps/console/src/layout/KeyGate.tsx apps/console/src/App.tsx apps/console/src/layout/LeftRail.tsx apps/console/src/layout/Header.tsx apps/console/src/test/auth.test.tsx apps/console/src/test/technical.test.tsx
git commit -m "Console: a public Technical approach page (problem, stages, takedown selection, evidence, ledger, organisations, serving, limits), linked from sign-in and the rail"
git push origin main
```

---

### Task 4: Tour engine: steps, live values, provider

**Files:**
- Create: `apps/console/src/tour/steps.ts`
- Create: `apps/console/src/tour/TourProvider.tsx`
- Test: `apps/console/src/test/tour.test.tsx` (create)

**Interfaces:**
- Consumes: `FRAMING`; `api` and types `Campaign`, `CampaignGraph`, `DomainDetail`, `Page`, `Sweep` from `src/lib/api.ts`; `fmtInt(n)` from `src/lib/format.ts`.
- Produces:
  - `interface TourCtx { campaignId?: string; domainCount?: string; kitHash?: string; bundleId?: string; coverage?: { k: string; killed: string; total: string } }`
  - `interface TourStep { id: string; route: (c: TourCtx) => string; target: string; title: string; body: (c: TourCtx) => string; missing: string }`
  - `STEPS: TourStep[]` (11 steps; targets `architecture, queue, score, status-filter, graph, budget, solvers, report, verify, kit-lookup, metrics`), `TOUR_K = 5`
  - `interface TourReads { campaigns; graph; sweep; domain }` and `resolveCtx(a: TourReads, signal?): Promise<TourCtx>`
  - `TourProvider({ children, reads? })`, `useTour(): Tour` with `Tour { state: { active: boolean; index: number; ctx: TourCtx }; steps: TourStep[]; starting: boolean; start(): Promise<void>; next(): void; back(): void; exit(): void }`

- [ ] **Step 1: Write the failing tests**

`apps/console/src/test/tour.test.tsx`:

```tsx
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { Campaign, DomainDetail, Page } from "../lib/api";
import { STEPS, resolveCtx, type TourCtx, type TourReads } from "../tour/steps";
import { TourProvider, useTour } from "../tour/TourProvider";
import { GRAPH, SWEEP, json } from "./fixtures";
import { measuredNumber } from "./textRules";

const camp = (id: string, n: number, kit: string): Campaign => ({
  id, label: null, kit_hash: kit, domain_count: n, infra_count: 3, confidence: 80, brands: ["ICICI Bank"], status: "active",
  first_seen: "2026-10-07T00:00:00Z", published_tx: null,
});
const CAMPAIGNS: Page<Campaign> = { items: [camp("small", 50, "k-small"), camp("big", 470, "k-big")], limit: 50, next_cursor: null };

export function reads(over: Partial<TourReads> = {}): TourReads {
  return {
    campaigns: vi.fn().mockResolvedValue(CAMPAIGNS),
    graph: vi.fn().mockResolvedValue(GRAPH),
    sweep: vi.fn().mockResolvedValue(SWEEP),
    domain: vi.fn().mockImplementation(async (id: number) => ({ evidence_bundle_id: id === 102 ? "b-102" : null }) as DomainDetail),
    ...over,
  };
}

function wrap(r: TourReads) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={["/tour"]}><TourProvider reads={r}>{children}</TourProvider></MemoryRouter>
  );
}

afterEach(() => { window.sessionStorage.clear(); vi.restoreAllMocks(); });

it("finds the largest campaign, its coverage at the tour budget, a bundle and the kit hash", async () => {
  const r = reads();
  const ctx = await resolveCtx(r);
  // SWEEP has k = 1..3, so the largest k within the tour budget is 3; domain 101 has no bundle, 102 has one
  expect(ctx).toEqual({ campaignId: "big", domainCount: "470", kitHash: "k-big", coverage: { k: "3", killed: "6", total: "6" }, bundleId: "b-102" });
  expect(r.graph).toHaveBeenCalledWith("big", undefined);
});

it("without data the tour still runs, with no live values", async () => {
  expect(await resolveCtx(reads({ campaigns: vi.fn().mockRejectedValue(new Error("offline")) }))).toEqual({});
});

it("every step's text types no measured number and no title says quantum", () => {
  const ph: TourCtx = { campaignId: "C", domainCount: "N", kitHash: "K", bundleId: "B", coverage: { k: "K", killed: "X", total: "T" } };
  for (const s of STEPS) {
    for (const text of [s.title, s.body(ph), s.body({}), s.missing]) expect([s.id, measuredNumber(text)]).toEqual([s.id, false]);
    expect(s.title.toLowerCase()).not.toContain("quantum");
  }
});

it("a step without its item falls back to the list page", () => {
  const by = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  expect(by.graph.route({})).toBe("/campaigns");
  expect(by.evidence.route({})).toBe("/evidence");
  expect(by.ledger.route({})).toBe("/ledger");
  expect(by.ledger.route({ kitHash: "abc" })).toBe("/ledger?kit=abc");
});

it("start opens step one; Next and Back move between pages; the last step ends the tour", async () => {
  const { result } = renderHook(() => ({ tour: useTour(), loc: useLocation() }), { wrapper: wrap(reads()) });
  await act(async () => { await result.current.tour.start(); });
  expect(result.current.tour.state).toMatchObject({ active: true, index: 0 });
  expect(result.current.loc.pathname).toBe("/");
  for (let i = 1; i <= 4; i++) act(() => result.current.tour.next());
  expect(result.current.loc.pathname).toBe("/campaigns/big");
  act(() => result.current.tour.back());
  expect(result.current.loc.pathname + result.current.loc.search).toBe("/queue?status=confirmed");
  for (let i = 0; i < STEPS.length && result.current.tour.state.active; i++) act(() => result.current.tour.next());
  expect(result.current.tour.state.active).toBe(false);
  expect(window.sessionStorage.getItem("qcertchain.tour")).toBeNull();
});

it("the tour survives a reload in the same tab", async () => {
  const first = renderHook(() => useTour(), { wrapper: wrap(reads()) });
  await act(async () => { await first.result.current.start(); });
  act(() => first.result.current.next());
  first.unmount();
  const again = renderHook(() => useTour(), { wrapper: wrap(reads()) });
  expect(again.result.current.state).toMatchObject({ active: true, index: 1 });
});

it("with storage blocked the tour still runs, in memory", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  const { result } = renderHook(() => useTour(), { wrapper: wrap(reads()) });
  await act(async () => { await result.current.start(); });
  act(() => result.current.next());
  expect(result.current.state).toMatchObject({ active: true, index: 1 });
});

it("starting the tour only reads (every request is a GET)", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ items: [], limit: 50, next_cursor: null }));
  const { result } = renderHook(() => useTour(), {
    wrapper: ({ children }: { children: ReactNode }) => <MemoryRouter><TourProvider>{children}</TourProvider></MemoryRouter>,
  });
  await act(async () => { await result.current.start(); });
  expect(f).toHaveBeenCalled();
  for (const [, init] of f.mock.calls) expect(((init as RequestInit | undefined)?.method ?? "GET").toUpperCase()).toBe("GET");
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/console && npx vitest run src/test/tour.test.tsx`
Expected: FAIL: `Failed to resolve import "../tour/steps"`.

- [ ] **Step 3: Write the steps and the live-value resolution**

`apps/console/src/tour/steps.ts`:

```ts
import { FRAMING } from "../explain/framing";
import type { Campaign, CampaignGraph, DomainDetail, Page, Sweep } from "../lib/api";
import { fmtInt } from "../lib/format";

/** Live values a step can quote. Read once when the tour starts and stored formatted, so steps type no numbers. */
export interface TourCtx {
  campaignId?: string;
  domainCount?: string;
  kitHash?: string;
  bundleId?: string;
  coverage?: { k: string; killed: string; total: string };
}

export interface TourStep {
  id: string;
  /** where the step happens; a step whose item is missing falls back to the list page */
  route: (c: TourCtx) => string;
  /** the element to highlight: the page marks it data-tour="<target>" */
  target: string;
  title: string;
  body: (c: TourCtx) => string;
  /** what the card says while the element is not on the page (no data yet) */
  missing: string;
}

/** The largest takedown budget the tour quotes (the demo's slider value). */
export const TOUR_K = 5;

const campaign = (c: TourCtx) => (c.campaignId ? `/campaigns/${encodeURIComponent(c.campaignId)}` : "/campaigns");
const bundle = (c: TourCtx) => (c.bundleId ? `/evidence/${encodeURIComponent(c.bundleId)}` : "/evidence");

export const STEPS: TourStep[] = [
  {
    id: "pipeline", route: () => "/", target: "architecture", title: "The pipeline",
    body: () => "Every HTTPS certificate is published to public Certificate Transparency logs before browsers trust it. QCertChain listens to those logs and moves each lookalike domain through triage, confirmation, campaign clustering, interdiction, evidence and the ledger. Each square is that stage's live status.",
    missing: "The pipeline diagram appears here once the page has loaded.",
  },
  {
    id: "queue", route: () => "/queue", target: "queue", title: "Certificates arriving",
    body: () => "Domains that triage nominates appear here as their certificates are logged. Triage is cheap and errs towards catching too many: it nominates, it never decides.",
    missing: "The queue fills as certificates arrive; it is empty right now.",
  },
  {
    id: "score", route: () => "/queue", target: "score", title: "Why a domain was nominated",
    body: () => "Hover a score to see its parts: the brand it imitates, keywords, the top-level domain and confusable characters. A candidate is suspicious, not verified, and is never shown in red.",
    missing: "Scores appear on each row once the queue has candidates.",
  },
  {
    id: "confirmed", route: () => "/queue?status=confirmed", target: "status-filter", title: "Confirmation needs evidence",
    body: () => "A domain is confirmed only after its page is fetched and two independent strong signals are found, such as a cloned login form and credentials posted to a foreign site. The database rejects a confirmation with fewer.",
    missing: "The status filter is at the top of the queue.",
  },
  {
    id: "graph", route: campaign, target: "graph", title: "One operator, many domains",
    body: (c) => `${c.domainCount ? `This campaign's ${c.domainCount} domains are` : "A campaign's domains are"} linked by the hosting, nameservers, registrars and phishing kit they share. Blocking one domain leaves the rest running.`,
    missing: "Your organisation has no campaign yet. Campaigns appear once confirmed domains share infrastructure.",
  },
  {
    id: "budget", route: campaign, target: "budget", title: "The fewest takedowns",
    body: (c) => `${c.coverage ? `With a budget of ${c.coverage.k} takedowns, the best plan covers ${c.coverage.killed} of ${c.coverage.total} domains. ` : ""}Choosing which few targets cover the most domains is maximum coverage, an NP-hard problem, solved here with CP-SAT. Drag the budget to see the plan change.`,
    missing: "The takedown planner appears on a campaign's page.",
  },
  {
    id: "solvers", route: campaign, target: "solvers", title: "Solvers compared",
    body: () => `${FRAMING} Every solver's result is shown, losses included.`,
    missing: "The solver comparison appears on a campaign's page.",
  },
  {
    id: "report", route: bundle, target: "report", title: "Generated, never sent",
    body: () => "For each target the system writes an evidence-backed abuse request to the hosting provider, DNS provider or registrar. It is never submitted: one false positive would take a legitimate business offline.",
    missing: "Abuse reports belong to evidence bundles, which exist only for confirmed domains.",
  },
  {
    id: "evidence", route: bundle, target: "verify", title: "Tamper-evident evidence",
    body: () => "The screenshot, page, certificate, DNS and WHOIS records are hashed into one Merkle root and signed with Ed25519. Verify recomputes the root and compares it with the copy anchored on the chain. Only the hash is on the chain, never the content.",
    missing: "Verification appears on an evidence bundle's page.",
  },
  {
    id: "ledger", route: (c) => (c.kitHash ? `/ledger?kit=${encodeURIComponent(c.kitHash)}` : "/ledger"), target: "kit-lookup",
    title: "One organisation protects the next",
    body: () => "Looking up a phishing kit's hash shows every organisation that published a campaign built with it: counts, confidence, reporter and time. Domain names, addresses and page content are never shared.",
    missing: "The kit-hash lookup is at the top of the ledger page.",
  },
  {
    id: "metrics", route: () => "/metrics", target: "metrics", title: "Measured, not asserted",
    body: () => "Every figure on this page comes from a measurement script, and what could not be measured says so. That is the end of the tour.",
    missing: "The metrics appear once the report has loaded.",
  },
];

/** The GET-only reads the tour needs; injected so tests can stub them. */
export interface TourReads {
  campaigns: (p: { limit?: number }, signal?: AbortSignal) => Promise<Page<Campaign>>;
  graph: (id: string, signal?: AbortSignal) => Promise<CampaignGraph>;
  sweep: (id: string, signal?: AbortSignal) => Promise<Sweep>;
  domain: (id: number, signal?: AbortSignal) => Promise<DomainDetail>;
}

/** The organisation's largest campaign, its coverage within the tour budget, one evidence bundle and its kit hash. */
export async function resolveCtx(a: TourReads, signal?: AbortSignal): Promise<TourCtx> {
  const ctx: TourCtx = {};
  try {
    const page = await a.campaigns({ limit: 50 }, signal);
    const best = [...page.items].sort((x, y) => y.domain_count - x.domain_count)[0];
    if (!best) return ctx;
    ctx.campaignId = best.id;
    ctx.domainCount = fmtInt(best.domain_count);
    if (best.kit_hash) ctx.kitHash = best.kit_hash;
    const [graph, sweep] = await Promise.all([
      a.graph(best.id, signal).catch(() => null),
      a.sweep(best.id, signal).catch(() => null),
    ]);
    const point = sweep?.points.filter((p) => p.k <= TOUR_K).sort((x, y) => y.k - x.k)[0];
    if (point) ctx.coverage = { k: String(point.k), killed: fmtInt(point.domains_killed), total: fmtInt(point.domains_total) };
    for (const d of (graph?.domains ?? []).filter((x) => x[2] === "confirmed").slice(0, 5)) {
      const detail = await a.domain(d[0], signal).catch(() => null);
      if (detail?.evidence_bundle_id) { ctx.bundleId = detail.evidence_bundle_id; break; }
    }
  } catch {
    /* the tour still runs; steps without live values say so */
  }
  return ctx;
}
```

- [ ] **Step 4: Write the provider**

`apps/console/src/tour/TourProvider.tsx`:

```tsx
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { STEPS, resolveCtx, type TourCtx, type TourReads, type TourStep } from "./steps";

const STORAGE = "qcertchain.tour";

export interface TourState { active: boolean; index: number; ctx: TourCtx }
const IDLE: TourState = { active: false, index: 0, ctx: {} };

// Per tab: a reload (or signing in) resumes the tour where it was. Blocked storage means memory only.
function load(): TourState {
  try {
    const raw = window.sessionStorage.getItem(STORAGE);
    if (raw) return { ...IDLE, ...(JSON.parse(raw) as Partial<TourState>) };
  } catch {
    /* blocked or corrupt: start idle */
  }
  return IDLE;
}

function save(s: TourState): void {
  try {
    if (s.active) window.sessionStorage.setItem(STORAGE, JSON.stringify(s));
    else window.sessionStorage.removeItem(STORAGE);
  } catch {
    /* blocked: memory only */
  }
}

export interface Tour {
  state: TourState;
  steps: TourStep[];
  starting: boolean;
  start: () => Promise<void>;
  next: () => void;
  back: () => void;
  exit: () => void;
}

const TourContext = createContext<Tour | null>(null);

/** Sits above the sign-in gate so the tour survives signing in. Navigation happens in the actions, never in effects. */
export function TourProvider({ children, reads = api }: { children: ReactNode; reads?: TourReads }) {
  const nav = useNavigate();
  const [state, setState] = useState<TourState>(load);
  const [starting, setStarting] = useState(false);
  // Refs keep every action's identity stable across navigation (useNavigate's function changes with the location).
  const cur = useRef(state);
  cur.current = state;
  const navRef = useRef(nav);
  navRef.current = nav;
  const readsRef = useRef(reads);
  readsRef.current = reads;
  const busy = useRef(false);

  const go = useCallback((s: TourState) => {
    setState(s);
    save(s);
    if (s.active) navRef.current(STEPS[s.index].route(s.ctx));
  }, []);

  const start = useCallback(async () => {
    if (busy.current) return; // StrictMode runs effects twice; one tour at a time
    busy.current = true;
    setStarting(true);
    try {
      go({ active: true, index: 0, ctx: await resolveCtx(readsRef.current) });
    } finally {
      busy.current = false;
      setStarting(false);
    }
  }, [go]);

  const exit = useCallback(() => go(IDLE), [go]);
  const next = useCallback(() => {
    const s = cur.current;
    if (!s.active) return;
    if (s.index >= STEPS.length - 1) exit();
    else go({ ...s, index: s.index + 1 });
  }, [go, exit]);
  const back = useCallback(() => {
    const s = cur.current;
    if (s.active && s.index > 0) go({ ...s, index: s.index - 1 });
  }, [go]);

  const value = useMemo<Tour>(() => ({ state, steps: STEPS, starting, start, next, back, exit }),
    [state, starting, start, next, back, exit]);
  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

export function useTour(): Tour {
  const t = useContext(TourContext);
  if (!t) throw new Error("useTour must be used inside TourProvider");
  return t;
}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd apps/console && npx vitest run src/test/tour.test.tsx`
Expected: PASS (8 tests).

- [ ] **Step 6: Whole suite and typecheck**

Run: `cd apps/console && npx tsc --noEmit && npx vitest run`
Expected: all pass. (Nothing is wired into the app yet; the running console is unchanged.)

- [ ] **Step 7: Commit and push**

```bash
git add apps/console/src/tour/steps.ts apps/console/src/tour/TourProvider.tsx apps/console/src/test/tour.test.tsx
git commit -m "Console tour engine: eleven steps over the real pages, live values read once with GET only, state per tab that survives sign-in and blocked storage"
git push origin main
```

---

### Task 5: Tour overlay, page anchors, wiring

**Files:**
- Create: `apps/console/src/tour/TourOverlay.tsx`
- Create: `apps/console/src/tour/TourStart.tsx`
- Modify: `apps/console/src/components/Page.tsx` (`Section` takes `tour`)
- Modify: `apps/console/src/views/Architecture.tsx` (diagram section), `src/views/LiveQueue.tsx` (filter + table), `src/components/ScoreBreakdown.tsx` (root span), `src/views/CampaignView.tsx` (three sections), `src/views/EvidenceViewer.tsx` (two sections), `src/views/Ledger.tsx` (section + `?kit=`), `src/views/Metrics.tsx` (page root)
- Modify: `apps/console/src/main.tsx`, `apps/console/src/App.tsx`, `apps/console/src/layout/LeftRail.tsx`
- Test: `apps/console/src/test/tourOverlay.test.tsx` (create), `apps/console/src/test/anchors.test.ts` (create)

**Interfaces:**
- Consumes: `useTour`, `TourProvider`, `STEPS`, `TourReads` (Task 4); `reads()` test helper exported from `src/test/tour.test.tsx` is NOT imported (importing a test file re-runs it): the overlay test defines its own stub.
- Produces: `TourOverlay({ waitMs?: number })` with `data-testid="tour-highlight"`, `data-testid="tour-missing"`, buttons `Exit`, `Back`, `Next step` / `Finish`; `TARGET_WAIT_MS = 8000`; `TourStartPage()`; `Section` prop `tour?: string` rendered as `data-tour`; `LedgerPage` honours `?kit=<hash>`.

- [ ] **Step 1: Write the failing tests**

`apps/console/src/test/anchors.test.ts`:

```ts
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { STEPS } from "../tour/steps";

const SRC = resolve(__dirname, "..");
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" ? [] : files(p);
    return /\.tsx?$/.test(f) ? [p] : [];
  });
}
const SOURCE = files(SRC).map((p) => readFileSync(p, "utf8")).join("\n");

it("every tour step points at an element some page marks", () => {
  for (const s of STEPS) {
    const marked = SOURCE.includes(`data-tour="${s.target}"`) || SOURCE.includes(`tour="${s.target}"`);
    expect([s.id, marked]).toEqual([s.id, true]);
  }
});
```

`apps/console/src/test/tourOverlay.test.tsx`:

```tsx
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Drawer } from "../components/Drawer";
import type { Campaign, DomainDetail, Page } from "../lib/api";
import { STEPS, type TourReads } from "../tour/steps";
import { TourOverlay } from "../tour/TourOverlay";
import { TourProvider, useTour } from "../tour/TourProvider";
import { LedgerPage } from "../views/Ledger";
import { GRAPH, SWEEP, json, renderWith } from "./fixtures";

const N = STEPS.length;
const stub = (): TourReads => ({
  campaigns: vi.fn().mockResolvedValue({ items: [] as Campaign[], limit: 50, next_cursor: null } as Page<Campaign>),
  graph: vi.fn().mockResolvedValue(GRAPH),
  sweep: vi.fn().mockResolvedValue(SWEEP),
  domain: vi.fn().mockResolvedValue({ evidence_bundle_id: null } as DomainDetail),
});

function Start() {
  const t = useTour();
  return <button onClick={() => void t.start()}>start</button>;
}

function Pages() {
  return (
    <Routes>
      <Route path="/" element={<div data-tour="architecture">diagram</div>} />
      <Route path="/queue" element={
        <div>
          <div data-tour="status-filter" role="radiogroup" aria-label="Filter"><button role="radio" aria-checked="true">All</button></div>
          <div data-tour="queue"><input aria-label="search" /></div>
        </div>
      } />
      <Route path="*" element={<p>other</p>} />
    </Routes>
  );
}

function setup(waitMs = 50, extra: ReactNode = null) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <TourProvider reads={stub()}><Pages />{extra}<Start /><TourOverlay waitMs={waitMs} /></TourProvider>
    </MemoryRouter>,
  );
}

afterEach(() => { window.sessionStorage.clear(); vi.restoreAllMocks(); });

it("shows the step card, highlights the step's element and moves focus to the card", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  expect(await screen.findByText(`Step 1 of ${N}`)).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "The pipeline" })).toBeInTheDocument();
  expect(await screen.findByTestId("tour-highlight")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "The pipeline" })).toHaveFocus();
});

it("Next step, the arrow keys and Esc drive it", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  fireEvent.click(screen.getByRole("button", { name: "Next step" }));
  expect(await screen.findByText(`Step 2 of ${N}`)).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "ArrowRight" });
  expect(await screen.findByText(`Step 3 of ${N}`)).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "ArrowLeft" });
  expect(await screen.findByText(`Step 2 of ${N}`)).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("arrow keys inside a field or a radio group act on the control, not the tour", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  fireEvent.click(screen.getByRole("button", { name: "Next step" }));
  await screen.findByText(`Step 2 of ${N}`);
  fireEvent.keyDown(screen.getByLabelText("search"), { key: "ArrowRight" });
  fireEvent.keyDown(screen.getByRole("radio", { name: "All" }), { key: "ArrowRight" });
  expect(screen.getByText(`Step 2 of ${N}`)).toBeInTheDocument();
});

it("Esc with a drawer open closes the drawer, not the tour", async () => {
  function OpenDrawer() {
    const [open, setOpen] = useState(true);
    return <Drawer open={open} title="Help" onClose={() => setOpen(false)}><p>help text</p></Drawer>;
  }
  setup(50, <OpenDrawer />);
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  fireEvent.keyDown(document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByText("help text")).toBeNull());
  expect(screen.getByText(`Step 1 of ${N}`)).toBeInTheDocument();
});

it("a step whose element is not there yet says what would be there, then highlights it when it arrives", async () => {
  function Late() {
    const [on, setOn] = useState(false);
    useEffect(() => { const t = setTimeout(() => setOn(true), 300); return () => clearTimeout(t); }, []);
    return on ? <div data-tour="architecture">late diagram</div> : null;
  }
  render(
    <MemoryRouter><TourProvider reads={stub()}><Late /><Start /><TourOverlay waitMs={50} /></TourProvider></MemoryRouter>,
  );
  fireEvent.click(screen.getByText("start"));
  expect(await screen.findByTestId("tour-missing")).toHaveTextContent("pipeline diagram");
  expect(await screen.findByTestId("tour-highlight", {}, { timeout: 2000 })).toBeInTheDocument();
  expect(screen.queryByTestId("tour-missing")).toBeNull();
});

it("the highlight follows its element when the page scrolls", async () => {
  setup();
  const el = document.querySelector('[data-tour="architecture"]')!;
  let top = 100;
  vi.spyOn(el, "getBoundingClientRect").mockImplementation(() =>
    ({ top, left: 10, width: 200, height: 50, right: 210, bottom: top + 50, x: 10, y: top, toJSON: () => ({}) }) as DOMRect);
  fireEvent.click(screen.getByText("start"));
  const box = await screen.findByTestId("tour-highlight");
  expect(box.style.top).toBe("96px");
  top = 40;
  act(() => { window.dispatchEvent(new Event("scroll")); });
  expect(box.style.top).toBe("36px");
});

it("the last step offers Finish, which ends the tour", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  for (let i = 2; i <= N; i++) {
    fireEvent.click(screen.getByRole("button", { name: "Next step" }));
    await screen.findByText(`Step ${i} of ${N}`);
  }
  fireEvent.click(screen.getByRole("button", { name: "Finish" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("the ledger runs a kit-hash lookup passed in the address", async () => {
  const kit = "ab".repeat(32);
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/ledger/by-kit/")) return json({ kit_hash: kit, campaigns: [], local_telemetry_received: false });
    if (u.includes("/ledger/status")) return json({ available: true, queue_depth: 0, orgs: {}, you: "org1", reason: null });
    if (u.includes("/ledger/events")) return json({ items: [], limit: 50, next_cursor: null });
    return json({}, 404);
  });
  renderWith(<LedgerPage />, { route: `/ledger?kit=${kit}` });
  await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes(`/ledger/by-kit/${kit}`))).toBe(true));
  expect(screen.getByPlaceholderText("Kit hash (64 hex characters)")).toHaveValue(kit);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/console && npx vitest run src/test/anchors.test.ts src/test/tourOverlay.test.tsx`
Expected: FAIL: `Failed to resolve import "../tour/TourOverlay"`, and `anchors.test.ts` fails for every step.

- [ ] **Step 3: Write the overlay**

`apps/console/src/tour/TourOverlay.tsx`:

```tsx
import { useEffect, useId, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "../components/Button";
import { useTour } from "./TourProvider";

/** How long a step waits before saying its element is missing. It keeps looking after that: a cold campaign graph
 *  can take seconds, and the highlight appears whenever the element does. */
export const TARGET_WAIT_MS = 8000;
const PAD = 4;
// Above the rail and top bar (z 20), below drawers (z 30): an opened ? panel covers the card, closing it shows the card.
const Z_HIGHLIGHT = 24;
const Z_CARD = 25;
// Controls that use the arrow keys themselves: the tour leaves them alone.
const ARROW_OWNERS = 'input, textarea, select, [contenteditable="true"], [role="radiogroup"], [role="slider"], [role="grid"], table';

export function TourOverlay({ waitMs = TARGET_WAIT_MS }: { waitMs?: number }) {
  const t = useTour();
  const { pathname, search } = useLocation();
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [missing, setMissing] = useState(false);
  const { active, index } = t.state;
  const step = t.steps[index];

  // Find the step's element, waiting for the page's data; then follow it through scrolling, resizing and layout shifts.
  useEffect(() => {
    if (!active) return;
    setRect(null);
    setMissing(false);
    let el: Element | null = null;
    let timer = 0;
    const deadline = Date.now() + waitMs;
    const measure = () => { if (el) setRect(el.getBoundingClientRect()); };
    const find = () => {
      el = document.querySelector(`[data-tour="${step.target}"]`);
      if (el) {
        setMissing(false);
        el.scrollIntoView?.({ block: "center" });
        measure();
        return;
      }
      const late = Date.now() >= deadline;
      if (late) setMissing(true);
      timer = window.setTimeout(find, late ? 250 : 100);
    };
    find();
    const follow = window.setInterval(measure, 500);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(timer);
      window.clearInterval(follow);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [active, index, step.target, pathname, search, waitMs]);

  useEffect(() => { if (active) heading.current?.focus(); }, [active, index]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (document.querySelector(".drawer")) return; // Esc closes the open drawer first
        e.preventDefault();
        t.exit();
        return;
      }
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      if ((e.target as Element | null)?.closest?.(ARROW_OWNERS)) return;
      e.preventDefault();
      if (e.key === "ArrowRight") t.next();
      else t.back();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [active, t]);

  if (!active) return null;
  const last = index === t.steps.length - 1;
  const counter = `Step ${index + 1} of ${t.steps.length}`;
  return (
    <>
      {rect && (
        <div data-testid="tour-highlight" aria-hidden="true"
             style={{ position: "fixed", top: rect.top - PAD, left: rect.left - PAD, width: rect.width + 2 * PAD,
                      height: rect.height + 2 * PAD, outline: "2px solid var(--focus)", pointerEvents: "none", zIndex: Z_HIGHLIGHT }} />
      )}
      <section className="overlay panel" role="dialog" aria-modal="false" aria-labelledby={`${id}-title`}
               style={{ position: "fixed", right: 24, bottom: 24, width: 380, zIndex: Z_CARD }}>
        <div className="panel-body">
          <p className="sr-only" aria-live="polite">{`${counter}: ${step.title}`}</p>
          <p className="t-label">{counter}</p>
          <h2 id={`${id}-title`} ref={heading} tabIndex={-1} className="t-section" style={{ marginTop: 4 }}>{step.title}</h2>
          <p className="prose" style={{ marginTop: 8 }}>{step.body(t.state.ctx)}</p>
          {missing && <p className="prose ink-2" style={{ marginTop: 8 }} data-testid="tour-missing">{step.missing}</p>}
          <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
            <Button size="sm" variant="ghost" onClick={t.exit}>Exit</Button>
            <Button size="sm" onClick={t.back} disabled={index === 0} disabledReason="This is the first step">Back</Button>
            <Button size="sm" variant="primary" onClick={t.next}>{last ? "Finish" : "Next step"}</Button>
          </div>
        </div>
      </section>
    </>
  );
}
```

`apps/console/src/tour/TourStart.tsx`:

```tsx
import { useEffect } from "react";
import { PageHeader } from "../components/Page";
import { useTour } from "./TourProvider";

/** /tour: starts the guided tour on this organisation's data, then the tour navigates to its first step. */
export function TourStartPage() {
  const { start } = useTour();
  useEffect(() => { void start(); }, [start]);
  return <PageHeader title="How it works" meta="Preparing the tour from your organisation's data." />;
}
```

- [ ] **Step 4: Let `Section` carry an anchor**

In `apps/console/src/components/Page.tsx` replace

```tsx
export function Section({ title, aside, children, id }: { title: ReactNode; aside?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="panel" aria-labelledby={id} style={{ marginBottom: 24 }}>
```

with

```tsx
export function Section({ title, aside, children, id, tour }: { title: ReactNode; aside?: ReactNode; children: ReactNode; id?: string; tour?: string }) {
  return (
    <section className="panel" aria-labelledby={id} data-tour={tour} style={{ marginBottom: 24 }}>
```

- [ ] **Step 5: Mark the elements the steps point at**

- `src/views/Architecture.tsx`: `<section className="panel" style={{ padding: 16 }} aria-label="Architecture diagram">`
  → `<section className="panel" style={{ padding: 16 }} aria-label="Architecture diagram" data-tour="architecture">`
- `src/views/LiveQueue.tsx`: `actions={` followed by `<SegmentedControl<Filter>` … `/>` → wrap that control:
  replace `        actions={\n          <SegmentedControl<Filter>` with `        actions={<div data-tour="status-filter">\n          <SegmentedControl<Filter>`,
  and the control's closing `          />\n        }\n      />` with `          /></div>\n        }\n      />`.
  Wrap the table: replace `            <Table<CandidateItem>\n              label="Live queue"` with
  `            <div data-tour="queue"><Table<CandidateItem>\n              label="Live queue"`, and
  `              onPointerInside={setPointerIn}\n            />` with `              onPointerInside={setPointerIn}\n            /></div>`.
- `src/components/ScoreBreakdown.tsx`: `<span style={{ position: "relative", display: "inline-block" }}` →
  `<span data-tour="score" style={{ position: "relative", display: "inline-block" }}`
- `src/views/CampaignView.tsx`: `<Section id="sec-graph" title="Graph"` → `<Section id="sec-graph" tour="graph" title="Graph"`;
  `<Section id="sec-interdiction" title="Interdiction"` → `<Section id="sec-interdiction" tour="budget" title="Interdiction"`;
  `<Section id="sec-solvers" title="Solvers"` → `<Section id="sec-solvers" tour="solvers" title="Solvers"`.
- `src/views/EvidenceViewer.tsx`: `<Section id="sec-verify" title="Verify"` → `<Section id="sec-verify" tour="verify" title="Verify"`;
  `<Section id="sec-report" title="Abuse report"` → `<Section id="sec-report" tour="report" title="Abuse report"`.
- `src/views/Metrics.tsx`, in `MetricsPage`: the first `<div>` after `return (` → `<div data-tour="metrics">`.
- `src/views/Ledger.tsx`: `<Section id="sec-kit" title="Kit-hash lookup">` → `<Section id="sec-kit" tour="kit-lookup" title="Kit-hash lookup">`;
  change the import `import { Link } from "react-router-dom";` to `import { Link, useSearchParams } from "react-router-dom";`;
  and in `LedgerPage` replace

  ```tsx
    const [kit, setKit] = useState("");
    const [lookup, setLookup] = useState<string | null>(null);
  ```

  with

  ```tsx
    const [params] = useSearchParams();
    const fromUrl = params.get("kit")?.trim() || null; // the tour (or any link) can open a lookup directly
    const [kit, setKit] = useState(fromUrl ?? "");
    const [lookup, setLookup] = useState<string | null>(fromUrl);
  ```

- [ ] **Step 6: Wire the provider, the overlay, the route and the nav entry**

`apps/console/src/main.tsx`: add `import { TourProvider } from "./tour/TourProvider";` and replace

```tsx
          <KeyGate>
            <App />
          </KeyGate>
```

with

```tsx
          <TourProvider>
            <KeyGate>
              <App />
            </KeyGate>
          </TourProvider>
```

`apps/console/src/App.tsx`: add `import { TourOverlay } from "./tour/TourOverlay";` and
`import { TourStartPage } from "./tour/TourStart";`; add `<Route path="/tour" element={<TourStartPage />} />` after the
`/technical` route; and replace `      <DomainDrawer />` with

```tsx
      <DomainDrawer />
      <TourOverlay />
```

`apps/console/src/layout/LeftRail.tsx`: replace

```ts
  { to: "/", label: "Architecture", end: true },
  { to: "/technical", label: "Technical approach" },
```

with

```ts
  { to: "/", label: "Architecture", end: true },
  { to: "/tour", label: "How it works" },
  { to: "/technical", label: "Technical approach" },
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd apps/console && npx vitest run src/test/anchors.test.ts src/test/tourOverlay.test.tsx src/test/explainers.test.tsx`
Expected: PASS. (`explainers.test.tsx` now also sees `/tour` in `App.tsx`, which has a help entry.)

- [ ] **Step 8: Whole suite, typecheck, and the real tour on the running console**

Run: `cd apps/console && npx tsc --noEmit && npx vitest run`
Expected: all pass, including `design.test.tsx` (overlay uses only tokens, scale spacing and the `overlay` class).
Then on http://localhost:5180 signed in as Bank One: click **How it works** in the rail and step through all 11 steps
with Next step; each step lands on its page and highlights its element; Exit and Esc end it.

- [ ] **Step 9: Commit and push**

```bash
git add apps/console/src/tour/TourOverlay.tsx apps/console/src/tour/TourStart.tsx apps/console/src/components/Page.tsx apps/console/src/views/Architecture.tsx apps/console/src/views/LiveQueue.tsx apps/console/src/components/ScoreBreakdown.tsx apps/console/src/views/CampaignView.tsx apps/console/src/views/EvidenceViewer.tsx apps/console/src/views/Metrics.tsx apps/console/src/views/Ledger.tsx apps/console/src/main.tsx apps/console/src/App.tsx apps/console/src/layout/LeftRail.tsx apps/console/src/test/anchors.test.ts apps/console/src/test/tourOverlay.test.tsx
git commit -m "Console: the How it works tour walks the real pages, highlighting each step's element with Back / Next step / Exit and arrow keys; the ledger opens a kit lookup from ?kit="
git push origin main
```

---

### Task 6: Browser test, docs, full verification

**Files:**
- Create: `e2e/test_tour.py`
- Modify: `scripts/e2e_stack.py:120` (run both e2e files)
- Modify: `docs/DEMO.md` (a short "Explaining it" section), `docs/AI_USAGE_LOG.md` (entry)

**Interfaces:**
- Consumes: everything above; the e2e harness env `E2E_CONSOLE_URL`, `E2E_API_URL`, `E2E_KEY_DEMO`.

- [ ] **Step 1: Write the browser test**

`e2e/test_tour.py`:

```python
"""End-to-end: a signed-out visitor reads the Technical approach, starts the guided tour, signs in with the read-only
demo key and walks every step to the end, opening the ? panel on each page. Every step must find its element on the
seeded demo, and the tour must change nothing (no request other than GET/HEAD/OPTIONS).

Run through the harness, like test_demo_path.py:  python -m scripts.e2e_stack
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.e2e

CONSOLE = os.environ.get("E2E_CONSOLE_URL", "")
API = os.environ.get("E2E_API_URL", "")
DEMO_KEY = os.environ.get("E2E_KEY_DEMO", "")
LOCAL = {"localhost", "127.0.0.1"}
STEPS = 11

if not (CONSOLE and API and DEMO_KEY):
    pytest.skip("run through scripts/e2e_stack.py (needs E2E_* env)", allow_module_level=True)

from playwright.sync_api import expect, sync_playwright  # noqa: E402


def test_tour_signed_out_to_the_end_with_help_on_every_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        blocked: list[str] = []

        def offline(route):
            if (urlsplit(route.request.url).hostname or "") in LOCAL:
                route.continue_()
            else:  # the demo must not need the internet
                blocked.append(route.request.url)
                route.abort()

        ctx.route("**/*", offline)
        page = ctx.new_page()
        errors: list[str] = []
        writes: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method not in ("GET", "HEAD", "OPTIONS") else None)

        # no key yet: the Technical approach is open; the tour asks for a key first
        page.goto(CONSOLE + "/technical")
        expect(page.get_by_role("heading", name="Technical approach", level=1)).to_be_visible(timeout=30_000)
        page.goto(CONSOLE + "/tour")
        expect(page.get_by_test_id("tour-note")).to_be_visible()
        page.get_by_label("API key").fill(DEMO_KEY)
        page.get_by_role("button", name="Sign in").click()

        for n in range(1, STEPS + 1):
            expect(page.get_by_text(f"Step {n} of {STEPS}", exact=True)).to_be_visible(timeout=60_000)
            # every step finds its element on the seeded demo (the card's fallback text must not be what we see)
            expect(page.get_by_test_id("tour-highlight")).to_be_visible(timeout=60_000)
            # the ? explains whichever page this step is on
            page.get_by_test_id("help-button").click()
            help_panel = page.get_by_role("dialog", name=re.compile("^About this page"))
            expect(help_panel.get_by_role("heading", name="What this page is")).to_be_visible()
            help_panel.get_by_role("button", name="Close").click()
            expect(help_panel).to_have_count(0)
            page.get_by_role("button", name="Finish" if n == STEPS else "Next step").click()

        expect(page.get_by_text(f"Step {STEPS} of {STEPS}", exact=True)).to_have_count(0)
        assert not writes, writes
        assert not blocked, blocked
        assert not errors, errors
        browser.close()
```

- [ ] **Step 2: Run both browser tests in the harness**

In `scripts/e2e_stack.py` replace

```python
        r = subprocess.run([PY, "-m", "pytest", "e2e/test_demo_path.py", "-q", "-s", "-p", "no:cacheprovider",
```

with

```python
        r = subprocess.run([PY, "-m", "pytest", "e2e/test_demo_path.py", "e2e/test_tour.py", "-q", "-s", "-p", "no:cacheprovider",
```

- [ ] **Step 3: Run the offline e2e and see it pass**

The harness uses its own ports (API 8100, console 4173) and the :8546 test chain, so the running demo is untouched.
Run (repo root): `CHAIN_RPC=http://127.0.0.1:8546 PYTHONPATH=. .venv/Scripts/python -m scripts.e2e_stack`
Expected: `2 passed`; exit 0. If a tour step times out on its highlight, the step's element is not on the seeded page:
fix the anchor (Task 5), not the test.

- [ ] **Step 4: Document it for the presenter**

In `docs/DEMO.md`, directly before `## 0:00–2:00 Ingest and triage (profile A)`, add:

```markdown
## Explaining it (optional, any time)

- **?** at the right of the top bar explains the current page: what it is, how to read it, where the data comes
  from, and what it does not claim. Open it whenever a viewer asks "what am I looking at?".
- **How it works** (left rail, or the sign-in screen) is a guided tour of the real pages: eleven steps, each opening
  its page and highlighting the part that matters. Back / Next step / Exit, or the arrow keys and Esc. It only reads.
- **Technical approach** (left rail, or the sign-in screen, no key needed) is the design on one page.
```

- [ ] **Step 5: Log the work**

Append to `docs/AI_USAGE_LOG.md`:

```markdown

## Explainers: ? on every page, Technical approach, guided tour (2026-10-09)

- **Owner asked:** a Technical approach section, a step-by-step How it works section to click through during the
  demo, and a ? on every page explaining it (spec 2026-10-09 §8b; Plan 1 of 4).
- **AI did:** all explainer text in data modules (`help/content.ts`, `explain/technical.ts`, `tour/steps.ts`); a ?
  in the top bar opening a side panel per route; a public Technical approach page linked from sign-in and the rail;
  a guided tour (provider above the sign-in gate, overlay that finds `data-tour` anchors, live values read once with
  GET only); the ledger opens a kit lookup from `?kit=`.
- **Verified by:** tests first for each piece (route coverage, no typed measurements, framing verbatim, tour
  navigation, storage blocked, late elements, Esc with a drawer open, arrow keys in controls, highlight following
  scroll, anchors present); console typecheck and full suite; `e2e/test_tour.py` in the offline harness (signed out →
  Technical approach → tour with the demo key → all steps found → ? on each page → no write request).
```

- [ ] **Step 6: Full verification before claiming done**

Run, in order:
- `cd apps/console && npx tsc --noEmit && npx vitest run` → all pass (60 existing + the new tests).
- `CHAIN_RPC=http://127.0.0.1:8546 PYTHONPATH=. .venv/Scripts/python -m scripts.e2e_stack` → `2 passed`.
- `PYTHONPATH=. .venv/Scripts/python -m scripts.demo check` → `READY` (the local demo still works).
- Open http://localhost:5180 signed out: the sign-in screen shows the ?, Technical approach and How it works links.

- [ ] **Step 7: Commit and push**

```bash
git add e2e/test_tour.py scripts/e2e_stack.py docs/DEMO.md docs/AI_USAGE_LOG.md
git commit -m "Tour browser test in the offline e2e (signed out to the last step, ? on every page, no writes); DEMO.md and the AI usage log describe the explainers"
git push origin main
```
