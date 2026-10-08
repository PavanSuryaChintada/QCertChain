import { QueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { prefetchDemoPath } from "../lib/prefetch";

afterEach(() => vi.restoreAllMocks());

const big = { id: "c-big", domain_count: 470 };
const small = { id: "c-small", domain_count: 12 };

it("warms the demo path under the views' own query keys, for the largest campaign", async () => {
  vi.spyOn(api, "campaigns").mockResolvedValue({ items: [small, big], next_cursor: null } as never);
  const spies = {
    campaign: vi.spyOn(api, "campaign").mockResolvedValue({ id: "c-big" } as never),
    graph: vi.spyOn(api, "graph").mockResolvedValue({} as never),
    sweep: vi.spyOn(api, "sweep").mockResolvedValue({} as never),
    benchmark: vi.spyOn(api, "benchmark").mockResolvedValue({} as never),
    scaling: vi.spyOn(api, "scaling").mockResolvedValue({} as never),
    candidates: vi.spyOn(api, "candidates").mockResolvedValue({ items: [], next_cursor: null } as never),
    candidateCounts: vi.spyOn(api, "candidateCounts").mockResolvedValue({} as never),
    metricsReport: vi.spyOn(api, "metricsReport").mockResolvedValue({} as never),
    ledgerStatus: vi.spyOn(api, "ledgerStatus").mockResolvedValue({} as never),
  };
  const qc = new QueryClient();
  await prefetchDemoPath(qc);
  for (const key of [["campaigns"], ["campaign", "c-big"], ["graph", "c-big"], ["sweep", "c-big"],
                     ["benchmark", "c-big", 5], ["scaling"], ["candidates", "all"], ["candidate-counts"],
                     ["metrics-report"], ["ledger-status"]]) {
    expect(qc.getQueryData(key), JSON.stringify(key)).toBeDefined();
  }
  expect(spies.benchmark).toHaveBeenCalledWith("c-big", 5, false); // cached result only: never a live solver run
  expect(spies.graph).not.toHaveBeenCalledWith("c-small");
});

it("never throws: a failing endpoint leaves the page to load normally", async () => {
  vi.spyOn(api, "campaigns").mockRejectedValue(new Error("down"));
  const qc = new QueryClient();
  await expect(prefetchDemoPath(qc)).resolves.toBeUndefined();
});
