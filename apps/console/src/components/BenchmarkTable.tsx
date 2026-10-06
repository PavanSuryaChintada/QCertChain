import type { BenchmarkRow } from "../lib/api";
import { Num } from "./Mono";

// Verbatim wherever it appears (CLAUDE.md §2.3). Never in a heading, never next to a speed claim.
export const QUANTUM_FRAMING =
  "Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.";

/** One row per backend, every row shown — losses and failures included. The winning row gets an ink border,
 *  whichever backend wins: the table's credibility is the point (DESIGN.md §6). */
export function BenchmarkTable({ rows }: { rows: BenchmarkRow[] }) {
  return (
    <div>
      <table className="w-full" style={{ borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr className="rule-b secondary text-left">
            <th className="py-1 pl-3 font-normal">backend</th>
            <th className="py-1 font-normal text-right">domains taken down</th>
            <th className="py-1 font-normal text-right">coverage</th>
            <th className="py-1 font-normal text-right">time</th>
            <th className="py-1 pr-2 font-normal text-right">variables · qubits</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.backend} data-testid={`bench-${r.backend}`} className="rule-b"
                style={{ borderLeft: r.is_best ? "2px solid var(--ink-000)" : "2px solid transparent",
                         color: r.valid ? "var(--ink-100)" : "var(--ink-300)" }}>
              <td className="mono py-1 pl-3">{r.backend}</td>
              {r.valid ? (
                <>
                  <td className="py-1 text-right"><Num v={r.domains_killed} /></td>
                  <td className="py-1 text-right"><Num v={r.coverage_pct} digits={1} suffix="%" /></td>
                  <td className="py-1 text-right"><Num v={r.solve_ms} /> ms</td>
                  <td className="py-1 pr-2 text-right mono">{r.n_variables}{r.qubit_count != null ? ` · ${r.qubit_count}` : ""}</td>
                </>
              ) : (
                <td className="py-1 pr-2 mono" colSpan={4} style={{ fontSize: 12 }}>failed: {r.error}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="secondary mt-2">{QUANTUM_FRAMING} Greedy is guaranteed at least 63% of optimal (1 − 1/e).</p>
    </div>
  );
}
