import { act, fireEvent, render, screen } from "@testing-library/react";
import { InterdictionWorkbench, GrowthHeadline, SolversTable, FormulationPanel, QUANTUM_FRAMING } from "../views/CampaignView";
import { searchSpaceExponent } from "../lib/format";
import type { BenchmarkRow } from "../lib/api";
import { GRAPH, SWEEP, renderWith } from "./fixtures";

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

const whyNodes = () => [...screen.getByTestId("why-rows").querySelectorAll("tr")].map((r) => r.getAttribute("data-node"));
const selectedInGraph = () => [...document.querySelectorAll('g[data-selected="true"]')].map((g) => g.getAttribute("data-node"));

it("moving the k slider re-renders targets from the precomputed sweep, after a 150ms debounce, without fetching", () => {
  vi.useFakeTimers();
  const f = vi.spyOn(globalThis, "fetch");
  renderWith(<InterdictionWorkbench graph={GRAPH} sweep={SWEEP} initialK={1} />);
  expect(whyNodes()).toEqual(["3"]);
  expect(selectedInGraph()).toEqual(["3"]);
  expect(document.querySelectorAll("circle[data-dark]")).toHaveLength(4);

  fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });
  expect(whyNodes()).toEqual(["3"]); // debounced: not yet
  act(() => { vi.advanceTimersByTime(160); });
  expect(whyNodes()).toEqual(["1", "2"]);
  expect(selectedInGraph().sort()).toEqual(["1", "2"]);
  expect(document.querySelectorAll("circle[data-dark]")).toHaveLength(6);
  expect(screen.getByTestId("headline").textContent).toBe("k = 2 covers 6 of 6 domains");
  expect(screen.getAllByText("Hosting abuse", { selector: "td" })).toHaveLength(2);
  expect(f).not.toHaveBeenCalled();
});

it("only the last of several quick moves is applied", () => {
  vi.useFakeTimers();
  renderWith(<InterdictionWorkbench graph={GRAPH} sweep={SWEEP} initialK={1} />);
  const s = screen.getByRole("slider");
  fireEvent.change(s, { target: { value: "2" } });
  act(() => { vi.advanceTimersByTime(100); });
  fireEvent.change(s, { target: { value: "3" } });
  act(() => { vi.advanceTimersByTime(160); });
  expect(whyNodes()).toEqual(["1", "2", "3"]);
  expect(screen.getByTestId("search-space").textContent).toContain("solved exactly in 405 ms");
});

it("2^n comes from search_space_log2, not from n_targetable; plans at k are C(n, k)", () => {
  render(<GrowthHeadline n={19} k={5} log2={23} solveMs={405} backend="cpsat" scaling={undefined} />);
  expect(screen.getByTestId("search-space-exp").textContent).toBe("23");
  expect(screen.getByTestId("plans-here").textContent).toBe("11,628");
  expect(screen.getByTestId("search-space").getAttribute("aria-label")).toContain("2 to the power 23");
  renderWith(<InterdictionWorkbench graph={GRAPH} sweep={{ ...SWEEP, n_targetable: 3, search_space_log2: 41 }} initialK={1} />);
  expect(screen.getAllByTestId("search-space-exp").map((e) => e.textContent)).toContain("41");
  expect(searchSpaceExponent(37.5)).toBe("37.5");
});

it("graph draws targetable nodes as filled squares and evidence-only nodes as dashed hollow circles", () => {
  renderWith(<InterdictionWorkbench graph={GRAPH} sweep={SWEEP} initialK={1} />);
  const asn = document.querySelector('g[data-node="4"]')!;
  expect(asn.querySelector("circle")!.getAttribute("stroke-dasharray")).toBe("2 2");
  expect(asn.querySelector("circle")!.getAttribute("fill")).toBe("var(--paper)");
  expect(document.querySelector('g[data-node="1"] rect')).not.toBeNull();
  expect(screen.getByText(/Evidence only: ASN/)).toBeInTheDocument();
});

const row = (backend: BenchmarkRow["backend"], extra: Partial<BenchmarkRow> = {}): BenchmarkRow => ({
  backend, domains_covered: 400, domains_total: 400, targets_used: 5, solve_ms: 405, gap_vs_cpsat_pct: 0, valid: true,
  is_best: false, error: null, notes: [], ...extra,
});

it("solvers table keeps every row and column, shows QAOA losing and failures as rows", () => {
  render(<SolversTable rows={[row("cpsat", { is_best: true }), row("qaoa", { domains_covered: 371, gap_vs_cpsat_pct: 7.3, solve_ms: 8420 }),
                              row("greedy", { valid: false, error: "TimeoutError" })]} />);
  expect(screen.getAllByRole("columnheader")).toHaveLength(6);
  expect(screen.getByTestId("bench-qaoa").textContent).toContain("Loses to CP-SAT by 7.3%");
  expect(screen.getByTestId("bench-greedy").textContent).toContain("Failed: TimeoutError");
  expect(screen.getByTestId("bench-annealing").textContent).toContain("Not returned by the API");
});

it("the quantum word appears only in the one framing sentence, never in a heading", () => {
  const { container } = render(<FormulationPanel f={{ qubo_variables: 24, qubit_count: 20, circuit_depth: null, p_layers: 2, shots: 1024, warm_start: "greedy",
    reduction: { original_nodes: 31, original_domains: 400, collapsed_groups: 6, kept_nodes: 20, pruned_nodes: 5, unreachable_weight: 0, notes: [] } }} />);
  expect(screen.getByTestId("framing").textContent).toContain(QUANTUM_FRAMING);
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
  container.querySelectorAll("h1,h2,h3,h4,th,[role=heading]").forEach((h) => expect(h.textContent!.toLowerCase()).not.toContain("quantum"));
  const sentences = (container.textContent ?? "").split(/(?<=\.)\s/).filter((s) => /quantum/i.test(s));
  expect(sentences).toHaveLength(1);
});
