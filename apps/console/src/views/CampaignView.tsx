import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { api, isUnavailable, toApiError, type Backend, type Benchmark, type BenchmarkRow, type Campaign, type CampaignGraph, type Formulation,
  type Scaling, type Sweep, type SweepPoint, type Unavailable } from "../lib/api";
import { choose, fmtBig, fmtDateTime, fmtInt, fmtLongDuration, fmtMs, fmtNum, fmtPct, searchSpaceExponent, sentence } from "../lib/format";
import { type ViewState, useDebounced, useLiveQuery, useNow } from "../lib/viewState";
import { useStatus } from "../lib/status";
import { CampaignGraphSvg, GraphLegend, KIND_LABEL } from "./CampaignGraph";
import { LineChart } from "../components/charts";
import { ScalingCaption, ScalingChart, ScalingLegend, kRuleText } from "./ScalingChart";
import { Slider } from "../components/Slider";
import { Button } from "../components/Button";
import { HashDisplay } from "../components/HashDisplay";
import { ErrorState, ViewStateView, errorCopy } from "../components/States";
import { Fact, PageHeader, Section } from "../components/Page";
import { useToast } from "../components/Toast";

export const ROUTE_LABEL: Record<string, string> = { hosting: "Hosting abuse", dns: "DNS abuse", registrar: "Registrar suspension" };

/** Verbatim project framing (CLAUDE.md 2.3). The only place the word appears in the UI. */
export const QUANTUM_FRAMING =
  "Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.";
export const SCALING_NOTE = "CP-SAT is production and QAOA is benchmarked; the claim is about how the formulation scales, not about speed.";

/** /scaling as the page sees it: undefined while loading, null or Unavailable when it has not been generated. */
export type ScalingData = Scaling | Unavailable | null | undefined;

/** The /scaling point the headline quotes: n = 60 when present, otherwise the largest n available. */
export function headlinePoint(s: Scaling) {
  const pts = s.points.filter((p) => p.bruteforce_ms !== null);
  return pts.find((p) => p.n === 60) ?? [...pts].sort((a, b) => b.n - a.n)[0] ?? null;
}

const Pow = ({ e, testId }: { e: string; testId?: string }) => <>2<sup data-testid={testId} style={{ fontSize: 11 }}>{e}</sup></>;

/**
 * The growth headline. A fixed budget k means C(n, k) plans, polynomial in n; the problem is NP-hard because k grows
 * with the campaign, so the comparison quotes /scaling, where k grows with n. Every number comes from the data:
 * n from the sweep, C(n, k) computed from it, 2^n from search_space_log2, the large-n duration from /scaling.
 */
export function GrowthHeadline({ n, k, log2, solveMs, backend, scaling }: {
  n: number; k: number; log2: number; solveMs: number | null; backend: Backend; scaling: ScalingData;
}) {
  const plans = choose(n, k);
  const exp = searchSpaceExponent(log2);
  const s = scaling && !isUnavailable(scaling) ? scaling : null;
  const big = s ? headlinePoint(s) : null;
  const how = backend === "cpsat" ? "solved exactly in" : `solved by ${backend} in`;
  return (
    <p className="t-data" data-testid="search-space" style={{ fontSize: 15, lineHeight: "22px", fontWeight: 500 }}
       aria-label={`${fmtBig(plans)} possible ${k}-target plans here, out of 2 to the power ${exp} takedown sets of any size; ${how} ${fmtMs(solveMs)}`}>
      <span data-testid="plans-here">{fmtBig(plans)}</span> possible {k}-target plans here ({fmtInt(n)} targetable nodes; <Pow e={exp} testId="search-space-exp" /> takedown
      sets of any size): {how} {fmtMs(solveMs)}.
      {s && big ? (
        <span data-testid="growth">
          {" "}When the budget grows with the campaign ({kRuleText(s)}), exhaustive search at n = {big.n}
          {big.plans_log2 !== undefined && <> ({big.k !== undefined ? `k = ${big.k}, ` : ""}<Pow e={fmtNum(big.plans_log2, 0)} /> plans)</>}
          {" "}is {fmtLongDuration(big.bruteforce_ms)}{big.bruteforce_extrapolated ? ", extrapolated from the measured rate" : ""}.
        </span>
      ) : scaling !== undefined ? (
        <span className="ink-2" data-testid="growth-missing" style={{ fontWeight: 400 }}> Scaling benchmark not generated yet.</span>
      ) : null}
    </p>
  );
}

/** The page's headline number: "k = 5 covers 342 of 460 domains (400 reachable)". */
export function coverageHeadline(p: SweepPoint, reachable: number | null) {
  return `k = ${p.k} covers ${fmtInt(p.domains_killed)} of ${fmtInt(p.domains_total)} domains${reachable !== null ? ` (${fmtInt(reachable)} reachable)` : ""}`;
}

/** The knee: the first k whose marginal gain drops below half of k = 1's gain. */
export function kneeK(points: SweepPoint[]): number | null {
  const ps = [...points].sort((a, b) => a.k - b.k);
  if (ps.length < 2 || ps[0].k !== 1) return null;
  const g1 = ps[0].domains_killed;
  for (let i = 1; i < ps.length; i++) {
    if (ps[i].k !== ps[i - 1].k + 1) return null;
    if (ps[i].domains_killed - ps[i - 1].domains_killed < g1 / 2) return ps[i].k;
  }
  return null;
}

export interface Reach { total: number; reachable: number; unreachable: number }

/** The ceiling any plan can reach, and the domains beyond it, from the sweep (older APIs omit both: then null). */
export function reachability(sweep: Sweep): Reach | null {
  const total = sweep.domains_total ?? sweep.points[0]?.domains_total;
  if (total === undefined) return null;
  if (sweep.coverable_total !== undefined) return { total, reachable: sweep.coverable_total, unreachable: total - sweep.coverable_total };
  if (sweep.uncoverable_domain_ids !== undefined) {
    const u = sweep.uncoverable_domain_ids.length;
    return { total, reachable: total - u, unreachable: u };
  }
  return null;
}

/** Domains covered against k, with the reachable ceiling, the unreachable band above it, and the knee. */
export function CoverageCurve({ points, point, reach, knee }: { points: SweepPoint[]; point: SweepPoint | null; reach: Reach | null; knee: number | null }) {
  const total = reach?.total ?? points[0]?.domains_total ?? 1;
  const kneePt = knee !== null ? points.find((p) => p.k === knee) ?? null : null;
  return (
    <>
      <LineChart
        label="Domains covered by takedown budget"
        width={520} height={280} xLabel="Takedowns (k)" yLabel="Domains covered" yMin={0} yMax={total * 1.08}
        yFmt={(v) => fmtInt(v)}
        series={[{ name: "Domains covered", points: points.map((p) => ({ x: p.k, y: p.domains_killed })), stroke: "var(--ink-2)" }]}
        extra={(sx, sy) => {
          const xl = sx(points[0]?.k ?? 1), xr = sx(points[points.length - 1]?.k ?? 1);
          return (
            <>
              {reach && reach.unreachable > 0 && (
                <g data-testid="uncoverable-band">
                  <defs>
                    <pattern id="qcc-unreach" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                      <rect width="6" height="6" fill="var(--sunken)" />
                      <line x1="0" y1="0" x2="0" y2="6" stroke="var(--hairline-firm)" strokeWidth="1" />
                    </pattern>
                  </defs>
                  <rect x={xl} y={sy(reach.total)} width={xr - xl} height={sy(reach.reachable) - sy(reach.total)} fill="url(#qcc-unreach)" />
                  <text x={xl + 4} y={sy(reach.total) - 4} className="svg-text" style={{ fill: "var(--ink)" }}>
                    {fmtInt(reach.unreachable)} unreachable at any k
                  </text>
                </g>
              )}
              {reach && (
                <g data-testid="ceiling">
                  <line x1={xl} x2={xr} y1={sy(reach.reachable)} y2={sy(reach.reachable)} stroke="var(--ink)" strokeWidth={1} strokeDasharray="4 3" />
                  <text x={xl + 4} y={sy(reach.reachable) + 14} className="svg-text" style={{ fill: "var(--ink)" }}>
                    Reachable by any takedown: {fmtInt(reach.reachable)} of {fmtInt(reach.total)}
                  </text>
                </g>
              )}
              {kneePt && (
                <g data-testid="knee">
                  <line x1={sx(kneePt.k)} x2={sx(kneePt.k)} y1={sy(kneePt.domains_killed) + 6} y2={sy(kneePt.domains_killed) + 18} stroke="var(--ink-2)" strokeWidth={1} />
                  <text x={sx(kneePt.k) + 4} y={sy(kneePt.domains_killed) + 28} className="svg-mono">knee: k = {kneePt.k}</text>
                </g>
              )}
              {point && (
                <rect x={sx(point.k) - 4} y={sy(point.domains_killed) - 4} width={8} height={8} fill="var(--action)" data-testid="curve-selected" />
              )}
            </>
          );
        }}
      />
      {reach && reach.unreachable > 0 && (
        <p className="t-meta" data-testid="uncoverable-note" style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "flex-start" }}>
          <svg width="16" height="12" aria-hidden="true" style={{ flex: "none", transform: "translateY(2px)" }}>
            <rect width="16" height="12" fill="var(--sunken)" stroke="var(--hairline-firm)" strokeWidth="1" />
          </svg>
          <span><span className="mono">{fmtInt(reach.unreachable)}</span> domains have no takedownable infrastructure (only shared DNS); no budget reaches them.</span>
        </p>
      )}
    </>
  );
}

/** Sections (a) graph and (b) interdiction. The slider reads the precomputed sweep: no request per move. */
export function InterdictionWorkbench({ graph, sweep, initialK = 5, onKChange, scaling }: {
  graph: CampaignGraph; sweep: Sweep; initialK?: number; onKChange?: (k: number) => void; scaling?: ScalingData;
}) {
  const points = useMemo(() => [...sweep.points].sort((a, b) => a.k - b.k), [sweep]);
  const minK = points.length ? Math.max(1, points[0].k) : 1;
  const maxK = points.length ? points[points.length - 1].k : 1;
  const [sliderK, setSliderK] = useState(Math.min(Math.max(initialK, minK), maxK));
  const k = useDebounced(sliderK, 150);
  const point = points.find((p) => p.k === k) ?? null;
  useEffect(() => { onKChange?.(k); }, [k]); // eslint-disable-line react-hooks/exhaustive-deps
  const selected = useMemo(() => new Map((point?.targets ?? []).map((t, i) => [t.node_id, i + 1])), [point]);
  const killed = useMemo(() => new Set(point?.killed_ids ?? []), [point]);
  const uncoverable = useMemo(() => new Set(graph.uncoverable_domain_ids ?? sweep.uncoverable_domain_ids ?? []), [graph, sweep]);
  const reach = useMemo(() => reachability(sweep), [sweep]);
  const knee = useMemo(() => kneeK(points), [points]);

  // Measure the re-render after the debounce, for the deliverable check (target: under 100 ms).
  const t0 = useRef<number | null>(null);
  const lastK = useRef(k);
  if (lastK.current !== k) { lastK.current = k; t0.current = performance.now(); }
  const [renderMs, setRenderMs] = useState<number | null>(null);
  useLayoutEffect(() => {
    if (t0.current !== null) { setRenderMs(performance.now() - t0.current); t0.current = null; }
  }, [k]);

  return (
    <>
      <Section id="sec-graph" tour="graph" title="Graph" aside={<span className="t-meta">Built <span className="mono">{fmtDateTime(graph.built_at)}</span></span>}>
        <CampaignGraphSvg graph={graph} selected={selected} killed={killed} uncoverable={uncoverable} />
        <GraphLegend uncoverable={uncoverable.size} />
      </Section>
      <Section id="sec-interdiction" tour="budget" title="Interdiction" aside={renderMs !== null && <span className="t-meta mono" data-testid="render-ms">re-rendered in {fmtNum(renderMs, 1)} ms</span>}>
        {points.length === 0 ? (
          <p className="ink-2">No precomputed sweep for this campaign yet. It is computed when the campaign graph is built.</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 520px)", gap: 24 }}>
            <div>
              <Slider label="Takedown budget k" min={minK} max={maxK} value={sliderK} onChange={setSliderK}
                      valueText={`${sliderK} takedowns`} />
              {point ? (
                <div style={{ marginTop: 16 }}>
                  <p className="t-display mono" data-testid="headline" style={{ fontSize: 26, lineHeight: "32px" }}>{coverageHeadline(point, reach?.reachable ?? null)}</p>
                  <div style={{ marginTop: 12 }}>
                    <GrowthHeadline n={sweep.n_targetable} k={point.k} log2={sweep.search_space_log2} solveMs={point.solve_ms} backend={point.backend} scaling={scaling} />
                  </div>
                  <p className="t-meta" style={{ marginTop: 4 }}>
                    Coverage <span className="mono">{fmtPct(point.coverage_pct)}</span>; solver <span className="mono">{point.backend}</span>;
                    {" "}{fmtInt(sweep.n_targetable)} target-eligible nodes{sweep.cached ? "; precomputed" : ""}.
                  </p>
                  {!point.valid && <p className="ink-2" style={{ marginTop: 8 }}>This plan failed validation: {point.notes.join("; ") || "no detail given"}.</p>}
                </div>
              ) : <p className="ink-2" style={{ marginTop: 16 }}>No precomputed plan for k = {k}.</p>}
            </div>
            <div>
              <p className="t-label">Domains covered by budget k (diminishing returns)</p>
              <CoverageCurve points={points} point={point} reach={reach} knee={knee} />
            </div>
          </div>
        )}
        {point && (
          <div style={{ marginTop: 24 }}>
            <h3 className="t-section">Why this plan</h3>
            <p className="t-meta" style={{ marginBottom: 8 }}>Each takedown request is generated with its evidence and never sent.</p>
            <table className="tbl" aria-label="Selected takedown targets">
              <colgroup><col style={{ width: 56 }} /><col style={{ width: 144 }} /><col /><col style={{ width: 200 }} /><col style={{ width: 144 }} /></colgroup>
              <thead><tr><th>Rank</th><th>Kind</th><th>Target</th><th>Takedown route</th><th className="num">Domains covered</th></tr></thead>
              <tbody data-testid="why-rows">
                {point.targets.map((t, i) => (
                  <tr key={t.node_id} data-node={t.node_id}>
                    <td className="mono">{i + 1}</td>
                    <td>{KIND_LABEL[t.kind] ?? t.kind}</td>
                    <td className="mono" title={t.value}>{t.value}</td>
                    <td>{ROUTE_LABEL[t.route] ?? sentence(t.route)}</td>
                    <td className="num mono">{fmtInt(t.kills)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}

const BACKENDS: { id: Backend; label: string }[] = [
  { id: "greedy", label: "Greedy" },
  { id: "cpsat", label: "CP-SAT" },
  { id: "annealing", label: "Simulated annealing" },
  { id: "qaoa", label: "QAOA" },
  { id: "bruteforce", label: "Exhaustive search" },
];

/** The exhaustive row proves CP-SAT optimal when it ran and found nothing better. */
export function exhaustiveVerifies(rows: BenchmarkRow[]): BenchmarkRow | null {
  const bf = rows.find((r) => r.backend === "bruteforce");
  const cp = rows.find((r) => r.backend === "cpsat");
  if (!bf || !cp || !bf.valid || bf.error || !cp.valid || cp.error) return null;
  return bf.gap_vs_cpsat_pct === 0 || (bf.domains_covered !== null && bf.domains_covered === cp.domains_covered) ? bf : null;
}

function outcome(r: BenchmarkRow | undefined, rows: BenchmarkRow[]): ReactNode {
  if (!r) return "Not returned by the API";
  if (r.backend === "bruteforce" && r.error && /^skipped/i.test(r.error)) {
    return `Skipped: ${r.error.replace(/^skipped:?\s*/i, "")} is beyond exhaustive search here`;
  }
  if (!r.valid || r.error) return `Failed: ${r.error ?? "invalid plan"}`;
  if (r.backend === "cpsat") {
    const bf = exhaustiveVerifies(rows);
    const base = r.is_best ? "Reference; best" : "Reference";
    return bf ? <>{base}; <span data-testid="verified">optimality verified exhaustively ({bf.subsets_checked != null ? <span className="mono">{fmtInt(bf.subsets_checked)}</span> : "all"} plans)</span></> : base;
  }
  if (r.backend === "bruteforce" && r.gap_vs_cpsat_pct === 0) {
    return <>Checked {r.subsets_checked != null ? <span className="mono">{fmtInt(r.subsets_checked)}</span> : "every"} plans; matches CP-SAT</>;
  }
  if (r.gap_vs_cpsat_pct === null) return "No comparison: CP-SAT failed";
  if (r.gap_vs_cpsat_pct > 0) return `Loses to CP-SAT by ${fmtNum(r.gap_vs_cpsat_pct, 1)}%`;
  if (r.gap_vs_cpsat_pct < 0) return `Beats CP-SAT by ${fmtNum(-r.gap_vs_cpsat_pct, 1)}%`;
  return r.is_best ? "Matches CP-SAT; best" : "Matches CP-SAT";
}

/** Every backend gets a row and every column stays, including losses and failures. */
export function SolversTable({ rows }: { rows: BenchmarkRow[] }) {
  const by = new Map(rows.map((r) => [r.backend, r]));
  const dash = <span className="ink-3">{"–"}</span>;
  return (
    <table className="tbl" aria-label="Solver benchmark">
      <colgroup><col style={{ width: 176 }} /><col style={{ width: 144 }} /><col style={{ width: 112 }} /><col style={{ width: 128 }} /><col style={{ width: 168 }} /><col /></colgroup>
      <thead>
        <tr><th>Backend</th><th className="num">Domains covered</th><th className="num">Targets used</th><th className="num">Solve time ms</th><th className="num">Optimality gap vs CP-SAT</th><th>Result</th></tr>
      </thead>
      <tbody>
        {BACKENDS.map(({ id, label }) => {
          const r = by.get(id);
          const ok = r && r.valid && !r.error;
          return (
            <tr key={id} data-testid={`bench-${id}`} style={r?.is_best ? { fontWeight: 500 } : undefined}>
              <td>{label}</td>
              <td className="num mono">{ok && r.domains_covered !== null ? `${fmtInt(r.domains_covered)}/${fmtInt(r.domains_total)}` : dash}</td>
              <td className="num mono">{ok && r.targets_used !== null ? fmtInt(r.targets_used) : dash}</td>
              <td className="num mono">{r && r.solve_ms !== null && (ok || r.solve_ms > 0) ? fmtNum(r.solve_ms, r.solve_ms < 10 ? 2 : 0) : dash}</td>
              <td className="num mono">{id === "cpsat" ? "0.0% (reference)" : ok && r.gap_vs_cpsat_pct !== null ? fmtPct(r.gap_vs_cpsat_pct) : dash}</td>
              <td title={r?.notes.join("; ")}>{outcome(r, rows)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** A1(c): the scaling chart. /scaling is platform data; a 404 or {unavailable} means it has not been generated. */
export function ScalingPanel({ state, campaignN }: { state: ViewState<Scaling | Unavailable>; campaignN: number | null }) {
  const missing = (why: string | null) => (
    <p className="ink-2" data-testid="scaling-missing">Scaling benchmark not generated yet{why ? `: ${why}` : ""}.</p>
  );
  return (
    <div style={{ marginTop: 32 }} data-testid="scaling">
      <h3 className="t-section">How solve time grows with campaign size</h3>
      <p className="t-meta" style={{ marginTop: 4, marginBottom: 12 }}>
        When the budget grows with the campaign, exhaustive search grows exponentially in n; that growth, not this campaign's size, is what makes the selection NP-hard.
      </p>
      {state.kind === "loading" ? <div style={{ height: 400, background: "var(--sunken)" }} aria-busy="true" />
        : state.kind === "error" ? (state.error.status === 404 ? missing(null) : <ErrorState error={state.error} what="the scaling benchmark" />)
        : state.kind === "empty" ? missing(null)
        : isUnavailable(state.data) ? missing(state.data.unavailable)
        : (
          <>
            <ScalingChart scaling={state.data} campaignN={campaignN} />
            <ScalingLegend />
            <ScalingCaption scaling={state.data} />
          </>
        )}
    </div>
  );
}

function SolversSection({ campaignId, k, scaling, campaignN }: { campaignId: string; k: number; scaling: ViewState<Scaling | Unavailable>; campaignN: number | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [benchK, setBenchK] = useState(5);
  const q = useLiveQuery<Benchmark>({ queryKey: ["benchmark", campaignId, benchK], queryFn: (s) => api.benchmark(campaignId, benchK, false, s), isEmpty: () => false, staleTime: 60_000 });
  const [run, setRun] = useState<{ started: number; ctrl: AbortController; k: number } | null>(null);
  const now = useNow(run ? 250 : 60_000);
  useEffect(() => () => run?.ctrl.abort(), [run]);

  const start = async () => {
    const ctrl = new AbortController();
    const runK = k;
    setRun({ started: Date.now(), ctrl, k: runK });
    try {
      const b = await api.benchmark(campaignId, runK, true, ctrl.signal);
      qc.setQueryData(["benchmark", campaignId, runK], b);
      setBenchK(runK);
      toast(`Benchmark finished at k = ${runK}.`);
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") toast(errorCopy(toApiError(e), "the benchmark run"));
    } finally {
      setRun(null);
    }
  };

  return (
    <Section id="sec-solvers" tour="solvers" title="Solvers" aside={
      <>
        {run && <Button size="sm" onClick={() => run.ctrl.abort()}>Cancel</Button>}
        <Button variant="primary" size="sm" onClick={start} disabled={!!run}>Run again at k = {k}</Button>
      </>
    }>
      {run && (
        <p className="t-meta" role="status" style={{ marginBottom: 12 }}>
          Running greedy, CP-SAT, simulated annealing, QAOA and exhaustive search at k = {run.k}: <span className="mono">{Math.floor((now - run.started) / 1000)} s</span> elapsed.
          QAOA alone can take up to about 20 s; the table updates when all five finish.
        </p>
      )}
      <ViewStateView state={q.state} what="the solver benchmark" onRetry={() => q.query.refetch()} empty={null}
                     skeleton={<div style={{ height: 192, background: "var(--sunken)" }} aria-busy="true" />}>
        {(b) => (
          <>
            <p className="t-meta" style={{ marginBottom: 8 }}>
              k = <span className="mono">{b.k}</span>
              {b.plans_at_k !== undefined && <>; <span className="mono">{fmtInt(b.plans_at_k)}</span> possible {b.k}-target plans over <span className="mono">{fmtInt(b.n_targetable ?? campaignN)}</span> targetable nodes</>}
              ; {b.cached ? "cached result" : "fresh run"} computed <span className="mono">{fmtDateTime(b.computed_at)}</span>.
            </p>
            <SolversTable rows={b.rows} />
          </>
        )}
      </ViewStateView>
      <ScalingPanel state={scaling} campaignN={campaignN} />
    </Section>
  );
}

export function FormulationPanel({ f }: { f: Formulation }) {
  const r = f.reduction;
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(144px, 1fr))", gap: 16 }}>
        <Fact label="QUBO variables">{fmtInt(f.qubo_variables)}</Fact>
        <Fact label="Qubit count">{fmtInt(f.qubit_count)}</Fact>
        <Fact label="Circuit depth">{f.circuit_depth === null ? "Unavailable" : fmtInt(f.circuit_depth)}</Fact>
        <Fact label="QAOA layers (p)">{fmtInt(f.p_layers)}</Fact>
        <Fact label="Shots">{fmtInt(f.shots)}</Fact>
        <Fact label="Warm start">{f.warm_start}</Fact>
      </div>
      <h3 className="t-section" style={{ marginTop: 24 }}>Reduction applied</h3>
      <p className="prose" style={{ marginTop: 8 }}>
        From <span className="mono">{fmtInt(r.original_nodes)}</span> infrastructure nodes over <span className="mono">{fmtInt(r.original_domains)}</span> domains,
        {" "}<span className="mono">{fmtInt(r.collapsed_groups)}</span> groups of equivalent nodes were collapsed and <span className="mono">{fmtInt(r.pruned_nodes)}</span> dominated
        nodes pruned, keeping <span className="mono">{fmtInt(r.kept_nodes)}</span>. Discarded: <span className="mono">{fmtNum(r.unreachable_weight, 1)}</span> units of
        domain weight that no kept node can reach.
      </p>
      {r.notes.length > 0 && <ul className="t-meta" style={{ marginTop: 8 }}>{r.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
      <p className="prose" style={{ marginTop: 16 }} data-testid="framing">{QUANTUM_FRAMING} {SCALING_NOTE}</p>
    </>
  );
}

function FormulationSection({ campaignId }: { campaignId: string }) {
  const q = useLiveQuery<Benchmark>({ queryKey: ["benchmark", campaignId, 5], queryFn: (s) => api.benchmark(campaignId, 5, false, s), isEmpty: () => false, staleTime: 60_000 });
  return (
    <Section id="sec-formulation" title="Solver formulation">
      <ViewStateView state={q.state} what="the solver formulation" empty={null} onRetry={() => q.query.refetch()}
                     skeleton={<div style={{ height: 128, background: "var(--sunken)" }} aria-busy="true" />}>
        {(b) => <FormulationPanel f={b.formulation} />}
      </ViewStateView>
    </Section>
  );
}

function CampaignHeader({ c }: { c: Campaign }) {
  const toast = useToast();
  const { data: status } = useStatus();
  const demo = status?.key_kind === "demo";
  const publish = useMutation({
    mutationFn: () => api.publish(c.id),
    onSuccess: () => toast("Queued for the ledger. Only the IOC root and kit hash are published."),
    onError: (e) => toast(errorCopy(toApiError(e), "the ledger publish")),
  });
  return (
    <>
      <PageHeader
        title={<span className="mono">{c.label ?? c.id}</span>}
        meta={<>Campaign <span className="mono">{c.id}</span>; brands {c.brands.join(", ") || "none"}; status {sentence(c.status).toLowerCase()}</>}
        actions={c.published_tx || c.anchored ? (
          <span className="t-meta">On the ledger: <HashDisplay value={c.published_tx} label="transaction hash" /></span>
        ) : (
          <Button onClick={() => publish.mutate()} disabled={publish.isPending || publish.isSuccess || !c.kit_hash || demo}
                  disabledReason={demo ? "The demo key is read-only." : !c.kit_hash ? "No kit hash to publish yet." : undefined}>
            {publish.isSuccess ? "Queued for the ledger" : "Publish hashes to ledger"}
          </Button>
        )}
      />
      <div className="panel panel-body" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(144px, 1fr))", gap: 16, marginBottom: 24 }}>
        <Fact label="Domains">{fmtInt(c.domain_count)}</Fact>
        <Fact label="Infra nodes">{fmtInt(c.infra_count)}</Fact>
        <Fact label="Confidence">{fmtNum(c.confidence, 2)}</Fact>
        <Fact label="Kit hash"><HashDisplay value={c.kit_hash} label="kit hash" /></Fact>
        <Fact label="First seen">{fmtDateTime(c.first_seen)}</Fact>
        <Fact label="Last seen">{fmtDateTime(c.last_seen ?? null)}</Fact>
      </div>
    </>
  );
}

export function CampaignDetailPage() {
  const { id = "" } = useParams();
  // All four requests start together: no waterfall.
  const c = useLiveQuery<Campaign>({ queryKey: ["campaign", id], queryFn: (s) => api.campaign(id, s), isEmpty: () => false, staleTime: 30_000 });
  const g = useLiveQuery<CampaignGraph>({ queryKey: ["graph", id], queryFn: (s) => api.graph(id, s), isEmpty: () => false, staleTime: 5 * 60_000 });
  const sw = useLiveQuery<Sweep>({ queryKey: ["sweep", id], queryFn: (s) => api.sweep(id, s), isEmpty: () => false, staleTime: 5 * 60_000 });
  const [k] = useState(5);
  if (c.state.kind === "error") return <ErrorState error={c.state.error} what="this campaign" onRetry={() => c.query.refetch()} />;
  const blocking = g.state.kind === "error" ? g.state : sw.state.kind === "error" ? sw.state : null;
  return (
    <div>
      {c.data ? <CampaignHeader c={c.data} /> : <div style={{ height: 128 }} aria-busy="true" />}
      {blocking ? (
        <div style={{ marginBottom: 24 }}><ErrorState error={blocking.error} what="the campaign graph and plan sweep" onRetry={() => { g.query.refetch(); sw.query.refetch(); }} /></div>
      ) : g.data && sw.data ? (
        <WorkbenchWithSolvers id={id} graph={g.data} sweep={sw.data} initialK={k} />
      ) : (
        <div className="panel" style={{ height: 480, marginBottom: 24, background: "var(--sunken)" }} aria-busy="true" aria-label="Loading the campaign graph" />
      )}
      <FormulationSection campaignId={id} />
    </div>
  );
}

function WorkbenchWithSolvers({ id, graph, sweep, initialK }: { id: string; graph: CampaignGraph; sweep: Sweep; initialK: number }) {
  // "Run again" benchmarks at the k currently applied on the slider.
  const [k, setK] = useState(initialK);
  const sc = useLiveQuery<Scaling | Unavailable>({ queryKey: ["scaling"], queryFn: (s) => api.scaling(s), isEmpty: () => false, staleTime: 10 * 60_000 });
  // For the headline: loading stays undefined; a 404, an error or {unavailable} all mean "not generated yet".
  const headlineScaling: ScalingData = sc.state.kind === "loading" ? undefined : sc.state.kind === "data" ? sc.state.data : null;
  return (
    <>
      <InterdictionWorkbench graph={graph} sweep={sweep} initialK={initialK} onKChange={setK} scaling={headlineScaling} />
      <SolversSection campaignId={id} k={k} scaling={sc.state} campaignN={sweep.n_targetable} />
    </>
  );
}
