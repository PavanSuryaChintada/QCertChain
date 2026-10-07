import { act, fireEvent, render, screen } from "@testing-library/react";
import { CoverageCurve, GrowthHeadline, InterdictionWorkbench, ScalingPanel, SolversTable, kneeK, reachability } from "../views/CampaignView";
import { ScalingChart } from "../views/ScalingChart";
import { logScale } from "../components/charts";
import { choose, fmtLongDuration } from "../lib/format";
import type { BenchmarkRow, Scaling, ScalingPoint, Sweep, SweepPoint, SweepTarget } from "../lib/api";
import { GRAPH, renderWith } from "./fixtures";

afterEach(() => { vi.useRealTimers(); });

const YEAR_MS = 365 * 86_400_000;
const NS = 40; // ns per plan
const pt = (n: number, measured: boolean, extra: Partial<ScalingPoint> = {}): ScalingPoint => {
  const k = Math.round(n / 4);
  const plans = Number(choose(n, k));
  return {
    n, k, subsets_log2: n, plans_log2: Math.log2(plans), bruteforce_ms: (plans * NS) / 1e6, bruteforce_extrapolated: !measured,
    cpsat_ms: 5 + n * 2, cpsat_status: "OPTIMAL", greedy_ms: 0.2 + n / 100, qaoa_ms: n <= 20 ? 900 * n : null,
    qaoa_note: n <= 20 ? null : "above the 24-qubit simulator cap", coverage: { cpsat: 1, greedy: 0.97, qaoa: n <= 20 ? 0.9 : null, bruteforce: 1 }, ...extra,
  };
};
export const SCALING: Scaling = {
  generated_at: "2026-10-07T00:00:00Z", k: null, k_rule: "n/4", method: "median of 3 runs per size", machine: "Ryzen 7 5800H, 16 GB",
  fit: { ns_per_subset: NS }, thresholds: { one_second: { n: 30 }, one_hour: { n: 40 }, one_year: { n: 60 } },
  points: [pt(10, true), pt(15, true), pt(20, true), pt(25, false), pt(30, false), pt(40, false), pt(60, false, { bruteforce_ms: 36_412 * YEAR_MS }), pt(80, false)],
};

it("the log scale maps 1 s, 1 h and 1 yr to positions proportional to their logarithms", () => {
  const s = logScale(1, 1e12, 400, 0);
  expect(s(1)).toBe(400);
  expect(s(1e12)).toBe(0);
  expect(s(1e6)).toBeCloseTo(200);

  render(<ScalingChart scaling={SCALING} campaignN={19} />);
  const y = (id: string) => Number(screen.getByTestId(`ref-${id}`).getAttribute("data-y"));
  const [s1, h1, y1] = [y("1s"), y("1h"), y("1yr")];
  expect(s1).toBeGreaterThan(h1);
  expect(h1).toBeGreaterThan(y1);
  // equal ratios in time are equal distances on screen
  expect((s1 - h1) / (h1 - y1)).toBeCloseTo(Math.log10(3600) / Math.log10(365 * 24), 6);
  expect(screen.getByText("1 second")).toBeInTheDocument();
  expect(screen.getByText("1 hour")).toBeInTheDocument();
  expect(screen.getByText("1 year")).toBeInTheDocument();
  // crossings from thresholds, and this campaign's n on the axis
  expect(screen.getByTestId("cross-1yr").textContent).toContain("n = 60");
  expect(screen.getByTestId("this-campaign").textContent).toBe("this campaign: n = 19");
});

it("exhaustive search is solid where measured and dashed and labelled where extrapolated", () => {
  render(<ScalingPanel state={{ kind: "data", data: SCALING, staleSince: null, error: null }} campaignN={19} />);
  const measured = screen.getByTestId("bf-measured");
  const extra = screen.getByTestId("bf-extrapolated");
  expect(measured.getAttribute("stroke-dasharray")).toBeNull();
  expect(extra.getAttribute("stroke-dasharray")).toBeTruthy();
  // the dashed run starts at the last measured point (n = 20) and covers the five extrapolated sizes
  expect(extra.getAttribute("points")!.split(" ")).toHaveLength(6);
  expect(screen.getByTestId("bf-extrapolated-label").textContent).toBe("extrapolated");
  expect(screen.getByText("Exhaustive search, extrapolated from the fit")).toBeInTheDocument();
  expect(screen.getByTestId("scaling-caption").textContent).toContain("k = n/4");
  expect(screen.getByTestId("scaling-caption").textContent).toContain("40.0 ns per plan");
  expect(screen.getByText("QAOA (stops at n = 20)")).toBeInTheDocument();
});

it("the scaling panel says when the benchmark has not been generated", () => {
  render(<ScalingPanel state={{ kind: "data", data: { unavailable: "run scripts/scaling.py" }, staleSince: null, error: null }} campaignN={19} />);
  expect(screen.getByTestId("scaling-missing").textContent).toBe("Scaling benchmark not generated yet: run scripts/scaling.py.");
});

it("the headline computes plans from n and k, and quotes /scaling at n = 60", () => {
  const { unmount } = render(<GrowthHeadline n={19} k={5} log2={19} solveMs={166} backend="cpsat" scaling={SCALING} />);
  const a = screen.getByTestId("search-space").textContent!;
  expect(screen.getByTestId("plans-here").textContent).toBe("11,628");
  expect(a).toContain("solved exactly in 166 ms");
  expect(screen.getByTestId("growth").textContent).toContain("(k = n/4), exhaustive search at n = 60");
  expect(screen.getByTestId("growth").textContent).toContain("is 36,000 years, extrapolated");
  unmount();
  render(<GrowthHeadline n={25} k={6} log2={25} solveMs={210} backend="cpsat" scaling={SCALING} />);
  expect(screen.getByTestId("plans-here").textContent).toBe("177,100");
  expect(screen.getByTestId("search-space-exp").textContent).toBe("25");
  expect(screen.getByTestId("search-space").textContent).not.toBe(a);
});

it("the headline uses the largest n when 60 is absent, and falls back when /scaling is unavailable", () => {
  const no60 = { ...SCALING, points: SCALING.points.filter((p) => p.n !== 60) };
  const { unmount } = render(<GrowthHeadline n={19} k={5} log2={19} solveMs={166} backend="cpsat" scaling={no60} />);
  expect(screen.getByTestId("growth").textContent).toContain("at n = 80");
  expect(screen.getByTestId("growth").textContent).toContain(fmtLongDuration(no60.points.find((p) => p.n === 80)!.bruteforce_ms));
  unmount();
  for (const s of [null, { unavailable: "not generated" }]) {
    const r = render(<GrowthHeadline n={19} k={5} log2={19} solveMs={166} backend="cpsat" scaling={s} />);
    expect(screen.getByTestId("search-space").textContent).toContain("11,628 possible 5-target plans here");
    expect(screen.getByTestId("growth-missing").textContent).toContain("Scaling benchmark not generated yet");
    expect(screen.queryByTestId("growth")).toBeNull();
    r.unmount();
  }
});

// The reseeded campaign: 470 domains, 30 with only shared DNS, 440 reachable; k = 5 covers 387, k = 14 covers all 440.
const KILLS = [150, 250, 320, 360, 387, 400, 410, 418, 425, 430, 434, 437, 439, 440, 440];
const tgt = (id: number, kind: SweepTarget["kind"], kills: number): SweepTarget =>
  ({ node_id: id, kind, value: `${kind}-${id}`, kills, route: kind === "ip" ? "hosting" : kind === "nameserver" ? "dns" : "registrar" });
const targetsFor = (k: number): SweepTarget[] =>
  k === 5 ? [tgt(1, "ip", 150), tgt(2, "ip", 100), tgt(3, "ip", 70), tgt(4, "nameserver", 40), tgt(5, "registrar", 27)]
  : k === 6 ? [tgt(1, "ip", 150), tgt(11, "nameserver", 110), tgt(12, "nameserver", 60), tgt(3, "ip", 40), tgt(13, "registrar", 25), tgt(14, "ip", 15)]
  : Array.from({ length: k }, (_, i) => tgt(100 + i, "ip", 10));
const P = (k: number): SweepPoint => ({
  k, backend: "cpsat", domains_killed: KILLS[k - 1], domains_total: 470, coverage_pct: (KILLS[k - 1] / 470) * 100, solve_ms: 100 + k,
  valid: true, notes: [], targets: targetsFor(k), killed_ids: [],
});
const UNCOVERABLE = Array.from({ length: 30 }, (_, i) => 1000 + i);
export const REACH_SWEEP: Sweep = {
  campaign_id: "c1", n_targetable: 19, search_space_log2: 19, cached: true, points: KILLS.map((_, i) => P(i + 1)),
  uncoverable_domain_ids: UNCOVERABLE, coverable_total: 440, domains_total: 470,
};

it("the coverage curve draws the reachable ceiling, the uncoverable band and the knee from the sweep", () => {
  const reach = reachability(REACH_SWEEP)!;
  expect(reach).toEqual({ total: 470, reachable: 440, unreachable: 30 });
  expect(kneeK(REACH_SWEEP.points)).toBe(3); // gains 150, 100, 70: 70 < 75
  render(<CoverageCurve points={REACH_SWEEP.points} point={REACH_SWEEP.points[4]} reach={reach} knee={3} />);
  expect(screen.getByTestId("ceiling").textContent).toBe("Reachable by any takedown: 440 of 470");
  expect(screen.getByTestId("uncoverable-band").textContent).toContain("30 unreachable at any k");
  expect(screen.getByTestId("uncoverable-note").textContent).toBe("30 domains have no takedownable infrastructure (only shared DNS); no budget reaches them.");
  expect(screen.getByTestId("knee").textContent).toBe("knee: k = 3");
  // older sweeps without the fields: no ceiling, no band
  expect(reachability({ ...REACH_SWEEP, coverable_total: undefined, uncoverable_domain_ids: undefined, domains_total: undefined })).toBeNull();
});

it("the page headline reads k covers X of Y (Z reachable); the slider runs to the sweep's largest k; uncoverable domains are hollow squares", () => {
  const graph = { ...GRAPH, uncoverable_domain_ids: [105, 106] };
  renderWith(<InterdictionWorkbench graph={graph} sweep={REACH_SWEEP} initialK={5} />);
  expect(screen.getByTestId("headline").textContent).toBe("k = 5 covers 387 of 470 domains (440 reachable)");
  expect(screen.getByRole("slider").getAttribute("max")).toBe("15");
  const hollow = document.querySelectorAll('rect[data-uncoverable="true"]');
  expect(hollow).toHaveLength(2);
  expect(hollow[0].getAttribute("fill")).toBe("var(--paper)");
  expect(hollow[0].getAttribute("stroke")).toBe("var(--ink-3)");
  expect(screen.getByText(/No takedownable infrastructure, only shared DNS: no plan reaches these 2/)).toBeInTheDocument();
});

it("why this plan follows the sweep's targets per k, including a different mix at k = 6", () => {
  vi.useFakeTimers();
  renderWith(<InterdictionWorkbench graph={GRAPH} sweep={REACH_SWEEP} initialK={5} />);
  const rows = () => [...screen.getByTestId("why-rows").querySelectorAll("tr")].map((r) => r.getAttribute("data-node"));
  const kinds = () => [...screen.getByTestId("why-rows").querySelectorAll("tr")].map((r) => r.children[1].textContent);
  expect(rows()).toEqual(["1", "2", "3", "4", "5"]);
  expect(kinds()).toEqual(["Hosting IP", "Hosting IP", "Hosting IP", "Nameserver", "Registrar"]);
  fireEvent.change(screen.getByRole("slider"), { target: { value: "6" } });
  act(() => { vi.advanceTimersByTime(160); });
  expect(rows()).toEqual(["1", "11", "12", "3", "13", "14"]);
  expect(kinds()).toEqual(["Hosting IP", "Nameserver", "Nameserver", "Hosting IP", "Registrar", "Hosting IP"]);
  expect(rows()).not.toContain("2"); // k = 6 drops a k = 5 target: targets change, they do not only grow
  expect(screen.getByTestId("headline").textContent).toBe("k = 6 covers 400 of 470 domains (440 reachable)");
});

const row = (backend: BenchmarkRow["backend"], extra: Partial<BenchmarkRow> = {}): BenchmarkRow => ({
  backend, domains_covered: 387, domains_total: 470, targets_used: 5, solve_ms: 166, gap_vs_cpsat_pct: 0, valid: true,
  is_best: false, error: null, notes: [], ...extra,
});

it("the exhaustive row verifies CP-SAT when it matches, and says skipped above 22 nodes", () => {
  const { unmount } = render(<SolversTable rows={[row("cpsat", { is_best: true }), row("bruteforce", { subsets_checked: 11628, solve_ms: 640 })]} />);
  expect(screen.getByTestId("bench-cpsat").textContent).toContain("optimality verified exhaustively (11,628 plans)");
  expect(screen.getByTestId("bench-bruteforce").textContent).toContain("Exhaustive search");
  expect(screen.getByTestId("bench-bruteforce").textContent).toContain("Checked 11,628 plans; matches CP-SAT");
  expect(screen.getAllByRole("row")).toHaveLength(6); // header + five backends, losses included
  unmount();
  render(<SolversTable rows={[row("cpsat"), row("bruteforce", { valid: false, error: "skipped: 2^40 subsets", domains_covered: null, gap_vs_cpsat_pct: null, solve_ms: null })]} />);
  expect(screen.getByTestId("bench-bruteforce").textContent).toContain("Skipped: 2^40 subsets");
  expect(screen.getByTestId("bench-bruteforce").textContent).not.toContain("Failed");
  expect(screen.getByTestId("bench-cpsat").textContent).not.toContain("verified");
});
