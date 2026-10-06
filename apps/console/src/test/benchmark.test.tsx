import { render, screen } from "@testing-library/react";
import { BenchmarkTable, QUANTUM_FRAMING } from "../components/BenchmarkTable";
import { PlanSummary } from "../views/PlanPanel";
import type { BenchmarkRow, Plan } from "../lib/api";

const row = (backend: BenchmarkRow["backend"], killed: number, ms: number, extra: Partial<BenchmarkRow> = {}): BenchmarkRow => ({
  backend, objective: killed, domains_killed: killed, coverage_pct: killed / 4, solve_ms: ms, valid: true,
  qubit_count: backend === "qaoa" ? 12 : null, n_variables: 12, is_best: false, error: null, notes: [], ...extra,
});

function border(backend: string) {
  return screen.getByTestId(`bench-${backend}`).getAttribute("style") ?? "";
}

it("the winning row gets the ink border when cpsat wins", () => {
  render(<BenchmarkTable rows={[row("cpsat", 387, 41, { is_best: true }), row("qaoa", 371, 8420), row("annealing", 379, 1120), row("greedy", 364, 3)]} />);
  expect(border("cpsat")).toContain("var(--ink-000)");
  expect(border("qaoa")).not.toContain("var(--ink-000)");
});

it("…and the same treatment when qaoa wins — no backend is styled as the hero", () => {
  render(<BenchmarkTable rows={[row("cpsat", 371, 41), row("qaoa", 387, 8420, { is_best: true }), row("annealing", 379, 1120), row("greedy", 364, 3)]} />);
  expect(border("qaoa")).toContain("var(--ink-000)");
  expect(border("cpsat")).not.toContain("var(--ink-000)");
});

it("a failed backend is a row with its error, not a missing row", () => {
  render(<BenchmarkTable rows={[row("cpsat", 387, 41, { is_best: true }), row("qaoa", 0, 0, { valid: false, error: "TimeoutError: qaoa exceeded 15s", qubit_count: null })]} />);
  expect(screen.getByTestId("bench-qaoa").textContent).toContain("TimeoutError");
});

it("qubits appear only for the quantum backend and the framing is verbatim", () => {
  const { container } = render(<BenchmarkTable rows={[row("cpsat", 387, 41, { is_best: true }), row("qaoa", 371, 8420)]} />);
  expect(screen.getByTestId("bench-qaoa").textContent).toContain("12");
  expect(container.textContent).toContain(QUANTUM_FRAMING);
  expect(QUANTUM_FRAMING).toBe("Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.");
  container.querySelectorAll("h1,h2,h3,h4").forEach((h) => expect(h.textContent!.toLowerCase()).not.toContain("quantum"));
});

const PLAN: Plan = {
  plan_id: "p", campaign_id: "c", budget_k: 4, backend: "cpsat", fell_back: true, fallback_from: "qaoa", objective: 387,
  domains_killed: 387, domains_total: 400, coverage_pct: 96.75, n_variables: 12, qubit_count: null, solve_ms: 41, valid: true,
  targets: [{ rank: 1, node_id: 1, kind: "ip", value: "203.0.113.10", kills: 302, takedown_route: "hosting" }],
  killed_domain_ids: [], notes: ["qaoa: TimeoutError: qaoa exceeded 15s", "cp-sat feasible (time limit; gap 2.2%)"],
};

it("plan summary states the fallback and a non-proven optimum in words", () => {
  render(<PlanSummary plan={PLAN} />);
  expect(screen.getByText(/qaoa timed out → cpsat/)).toBeInTheDocument();
  expect(screen.getByText(/not proven optimal/)).toBeInTheDocument();
  expect(screen.getByText(/387 of 400 domains/)).toBeInTheDocument();
  expect(screen.queryByText(/qubits/)).toBeNull();
});
