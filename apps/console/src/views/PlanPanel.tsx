import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type Backend, type Benchmark, type Plan } from "../lib/api";
import { BenchmarkTable } from "../components/BenchmarkTable";
import { Num } from "../components/Mono";

const KIND = { ip: "IP", nameserver: "NS", registrar: "REG" } as Record<string, string>;
const ROUTE = { hosting: "hosting provider", dns: "DNS provider", registrar: "registrar" } as Record<string, string>;

function fallbackText(plan: Plan) {
  if (!plan.fell_back || !plan.fallback_from) return null;
  const reason = plan.notes.find((n) => n.startsWith(plan.fallback_from + ":")) ?? "";
  const why = /Timeout/i.test(reason) ? "timed out" : /Import/i.test(reason) ? "is not installed" : "failed";
  return `${plan.fallback_from} ${why} → ${plan.backend}`;
}

export function PlanSummary({ plan, onHover }: { plan: Plan; onHover?: (nodeId: number | null) => void }) {
  const fb = fallbackText(plan);
  const feasible = plan.notes.find((n) => n.startsWith("cp-sat feasible"));
  return (
    <div>
      <p className="secondary">
        backend <span className="mono">{plan.backend}</span> · <Num v={plan.solve_ms} /> ms ·{" "}
        <Num v={plan.n_variables} /> variables{plan.qubit_count != null && <> · <Num v={plan.qubit_count} /> qubits</>}
        {fb && <> · <span className="mono">{fb}</span></>}
      </p>
      {feasible && <p className="secondary">Time limit reached: a valid plan, not proven optimal ({feasible.replace(/^cp-sat feasible /, "")}).</p>}
      <table className="w-full mt-2" style={{ borderCollapse: "collapse", fontSize: 13 }}>
        <tbody>
          {plan.targets.map((t) => (
            <tr key={t.node_id} className="row rule-b" onMouseEnter={() => onHover?.(t.node_id)} onMouseLeave={() => onHover?.(null)}
                onFocus={() => onHover?.(t.node_id)} onBlur={() => onHover?.(null)} tabIndex={0}>
              <td className="num py-1 pl-1 w-6">{t.rank}</td>
              <td className="mono py-1">{t.value}</td>
              <td className="mono py-1 secondary">{KIND[t.kind] ?? t.kind}</td>
              <td className="py-1 secondary">report to {ROUTE[t.takedown_route] ?? t.takedown_route}</td>
              <td className="py-1 pr-1 text-right">takes down <Num v={t.kills} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 flex justify-between" style={{ color: "var(--ink-000)" }}>
        <span>Take down {plan.targets.length} targets → {plan.domains_killed} of {plan.domains_total} domains</span>
        <span><Num v={plan.coverage_pct} digits={1} suffix="% coverage" /></span>
      </p>
      <p className="secondary">Reports are generated for each target and never sent.</p>
    </div>
  );
}

export function PlanPanel({ campaignId, onPlan, onHover }: {
  campaignId: string; onPlan?: (p: Plan) => void; onHover?: (nodeId: number | null) => void;
}) {
  const [k, setK] = useState(4);
  const [maxK, setMaxK] = useState<number | null>(null);
  const [backend, setBackend] = useState<Backend>("cpsat");
  const [bench, setBench] = useState<Benchmark | null>(null);
  const solve = useMutation({
    mutationFn: () => api.interdict(campaignId, k, backend),
    onSuccess: (p) => { setBench(null); onPlan?.(p); },
    onError: (e) => {
      const m = e instanceof ApiError && e.problem.status === 422 ? /max (\d+)/.exec(e.problem.detail ?? "") : null;
      if (m) { setMaxK(Number(m[1])); setK(Number(m[1])); }
    },
  });
  const runBench = useMutation({ mutationFn: (planId: string) => api.benchmark(planId), onSuccess: setBench });
  const plan = solve.data;
  const err = solve.error instanceof ApiError ? solve.error.problem : null;
  return (
    <section className="p-4">
      <div className="flex items-center justify-between">
        <p className="panel-title">Takedown plan</p>
        <div className="flex items-center gap-2">
          <label className="secondary" htmlFor="k">targets</label>
          <input id="k" type="number" min={1} max={maxK ?? 50} value={k} style={{ width: 72 }}
                 onChange={(e) => setK(Math.max(1, Math.min(Number(e.target.value) || 1, maxK ?? 50)))} />
          <label className="secondary" htmlFor="backend">solver</label>
          <select id="backend" value={backend} onChange={(e) => setBackend(e.target.value as Backend)}>
            <option value="cpsat">cpsat</option><option value="qaoa">qaoa</option>
            <option value="annealing">annealing</option><option value="greedy">greedy</option>
          </select>
          <button onClick={() => solve.mutate()} disabled={solve.isPending}>Plan takedowns</button>
        </div>
      </div>
      {solve.isPending && <div className="solving mt-2" />}
      {err && err.status === 409 && <p className="mt-2">No shared infrastructure — nothing to interdict.</p>}
      {err && err.status === 422 && <p className="mt-2 secondary">{err.detail}. The control is now capped.</p>}
      {err && ![409, 422].includes(err.status) && <p className="mt-2">Planning failed: {err.detail}</p>}
      {plan && (
        <div className="mt-3">
          <PlanSummary plan={plan} onHover={onHover} />
          <div className="mt-4 flex items-center justify-between">
            <p className="panel-title" style={{ fontSize: 15 }}>Solver comparison</p>
            <button onClick={() => runBench.mutate(plan.plan_id)} disabled={runBench.isPending}>Compare all solvers</button>
          </div>
          {runBench.isPending && <><div className="solving mt-2" /><p className="secondary mt-1">Running four solvers; qaoa takes up to 15 s.</p></>}
          {bench && <div className="mt-2"><BenchmarkTable rows={bench.rows} /></div>}
        </div>
      )}
    </section>
  );
}
