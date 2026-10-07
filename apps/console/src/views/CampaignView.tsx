import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, toApiError, type Backend, type Benchmark, type BenchmarkRow, type Campaign, type CampaignGraph, type Formulation,
  type Sweep, type SweepPoint } from "../lib/api";
import { fmtDateTime, fmtInt, fmtMs, fmtNum, fmtPct, searchSpaceExponent, sentence } from "../lib/format";
import { useDebounced, useLiveQuery, useNow } from "../lib/viewState";
import { useStatus } from "../lib/status";
import { CampaignGraphSvg, GraphLegend, KIND_LABEL } from "./CampaignGraph";
import { LineChart } from "../components/charts";
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

/** "2^n candidate subsets": n is the API's search_space_log2, never hard-coded and never recomputed here. */
export function SearchSpace({ log2, solveMs }: { log2: number; solveMs: number | null }) {
  const exp = searchSpaceExponent(log2);
  return (
    <p className="t-data" data-testid="search-space" aria-label={`2 to the power ${exp} candidate subsets, solved in ${fmtMs(solveMs)}`}
       style={{ fontSize: 15, lineHeight: "20px", fontWeight: 500 }}>
      2<sup data-testid="search-space-exp" style={{ fontSize: 11 }}>{exp}</sup> candidate subsets, solved in {fmtMs(solveMs)}
    </p>
  );
}

function headline(p: SweepPoint) {
  return `${p.k} takedown${p.k === 1 ? "" : "s"} cover${p.k === 1 ? "s" : ""} ${fmtInt(p.domains_killed)}/${fmtInt(p.domains_total)} domains in ~${fmtInt(p.solve_ms)} ms`;
}

/** Sections (a) graph and (b) interdiction. The slider reads the precomputed sweep: no request per move. */
export function InterdictionWorkbench({ graph, sweep, initialK = 5, onKChange }: {
  graph: CampaignGraph; sweep: Sweep; initialK?: number; onKChange?: (k: number) => void;
}) {
  const points = useMemo(() => [...sweep.points].sort((a, b) => a.k - b.k), [sweep]);
  const minK = points.length ? Math.max(1, points[0].k) : 1;
  const maxK = points.length ? Math.min(10, points[points.length - 1].k) : 1;
  const [sliderK, setSliderK] = useState(Math.min(Math.max(initialK, minK), maxK));
  const k = useDebounced(sliderK, 150);
  const point = points.find((p) => p.k === k) ?? null;
  useEffect(() => { onKChange?.(k); }, [k]); // eslint-disable-line react-hooks/exhaustive-deps
  const selected = useMemo(() => new Map((point?.targets ?? []).map((t, i) => [t.node_id, i + 1])), [point]);
  const killed = useMemo(() => new Set(point?.killed_ids ?? []), [point]);

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
      <Section id="sec-graph" title="Graph" aside={<span className="t-meta">Built <span className="mono">{fmtDateTime(graph.built_at)}</span></span>}>
        <CampaignGraphSvg graph={graph} selected={selected} killed={killed} />
        <GraphLegend />
      </Section>
      <Section id="sec-interdiction" title="Interdiction" aside={renderMs !== null && <span className="t-meta mono" data-testid="render-ms">re-rendered in {fmtNum(renderMs, 1)} ms</span>}>
        {points.length === 0 ? (
          <p className="ink-2">No precomputed sweep for this campaign yet. It is computed when the campaign graph is built.</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 520px)", gap: 24 }}>
            <div>
              <Slider label="Takedown budget k" min={minK} max={maxK} value={sliderK} onChange={setSliderK}
                      valueText={`${sliderK} takedowns`} />
              {point ? (
                <div style={{ marginTop: 16 }}>
                  <p className="t-display" data-testid="headline">{headline(point)}</p>
                  <div style={{ marginTop: 8 }}><SearchSpace log2={sweep.search_space_log2} solveMs={point.solve_ms} /></div>
                  <p className="t-meta" style={{ marginTop: 4 }}>
                    Coverage <span className="mono">{fmtPct(point.coverage_pct)}</span>; solver <span className="mono">{point.backend}</span>;
                    {" "}{fmtInt(sweep.n_targetable)} target-eligible nodes{sweep.cached ? "; precomputed" : ""}.
                  </p>
                  {!point.valid && <p className="ink-2" style={{ marginTop: 8 }}>This plan failed validation: {point.notes.join("; ") || "no detail given"}.</p>}
                </div>
              ) : <p className="ink-2" style={{ marginTop: 16 }}>No precomputed plan for k = {k}.</p>}
            </div>
            <div>
              <p className="t-label">Coverage vs k (diminishing returns)</p>
              <LineChart
                label="Coverage by takedown budget"
                width={520} height={200} xLabel="Takedowns (k)" yLabel="Coverage %" yMin={0} yMax={100}
                yFmt={(v) => `${v}`}
                series={[{ name: "Coverage", points: points.map((p) => ({ x: p.k, y: p.coverage_pct })), stroke: "var(--ink-2)" }]}
                extra={(sx, sy) => point && (
                  <rect x={sx(point.k) - 4} y={sy(point.coverage_pct) - 4} width={8} height={8} fill="var(--action)" data-testid="curve-selected" />
                )}
              />
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
];

function outcome(r: BenchmarkRow | undefined): string {
  if (!r) return "Not returned by the API";
  if (!r.valid || r.error) return `Failed: ${r.error ?? "invalid plan"}`;
  if (r.backend === "cpsat") return r.is_best ? "Reference; best" : "Reference";
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
              <td className="num mono">{r && r.solve_ms !== null ? fmtNum(r.solve_ms, r.solve_ms < 10 ? 2 : 0) : dash}</td>
              <td className="num mono">{id === "cpsat" ? "0.0% (reference)" : ok && r.gap_vs_cpsat_pct !== null ? fmtPct(r.gap_vs_cpsat_pct) : dash}</td>
              <td title={r?.notes.join("; ")}>{outcome(r)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function SolversSection({ campaignId, k }: { campaignId: string; k: number }) {
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
    <Section id="sec-solvers" title="Solvers" aside={
      <>
        {run && <Button size="sm" onClick={() => run.ctrl.abort()}>Cancel</Button>}
        <Button variant="primary" size="sm" onClick={start} disabled={!!run}>Run again at k = {k}</Button>
      </>
    }>
      {run && (
        <p className="t-meta" role="status" style={{ marginBottom: 12 }}>
          Running greedy, CP-SAT, simulated annealing and QAOA at k = {run.k}: <span className="mono">{Math.floor((now - run.started) / 1000)} s</span> elapsed.
          QAOA alone can take up to about 20 s; the table updates when all four finish.
        </p>
      )}
      <ViewStateView state={q.state} what="the solver benchmark" onRetry={() => q.query.refetch()} empty={null}
                     skeleton={<div style={{ height: 192, background: "var(--sunken)" }} aria-busy="true" />}>
        {(b) => (
          <>
            <p className="t-meta" style={{ marginBottom: 8 }}>
              k = <span className="mono">{b.k}</span>; {b.cached ? "cached result" : "fresh run"} computed <span className="mono">{fmtDateTime(b.computed_at)}</span>.
            </p>
            <SolversTable rows={b.rows} />
          </>
        )}
      </ViewStateView>
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
  return (
    <>
      <InterdictionWorkbench graph={graph} sweep={sweep} initialK={initialK} onKChange={setK} />
      <SolversSection campaignId={id} k={k} />
    </>
  );
}
