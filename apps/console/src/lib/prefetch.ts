import type { QueryClient } from "@tanstack/react-query";
import { api } from "./api";

/**
 * Warm the pages a demo walks through, once, right after sign-in, so each opens from cache instead of waiting on
 * the database round trips (Supabase is ~75-100 ms per round trip from India). Keys and fetchers are exactly the
 * views' own, so a view finds the data already there. Best-effort: nothing here ever throws or shows an error; a
 * failed prefetch leaves the page to load normally. The benchmark is the CACHED result (run=false), never a live run.
 */
export async function prefetchDemoPath(qc: QueryClient): Promise<void> {
  const warm = (queryKey: unknown[], queryFn: () => Promise<unknown>, staleTime = 60_000) =>
    qc.prefetchQuery({ queryKey, queryFn, staleTime });
  try {
    const list = await qc.fetchQuery({ queryKey: ["campaigns"], queryFn: () => api.campaigns({ limit: 200 }),
                                       staleTime: 30_000 });
    const top = [...(list?.items ?? [])].sort((a, b) => b.domain_count - a.domain_count)[0];
    const jobs: Promise<unknown>[] = [
      warm(["candidates", "all"], () => api.candidates({ status: undefined, limit: 200 }), 5_000),
      warm(["candidate-counts"], () => api.candidateCounts(), 15_000),
      warm(["metrics-report"], () => api.metricsReport()),
      warm(["ledger-status"], () => api.ledgerStatus()),
      warm(["scaling"], () => api.scaling(), 10 * 60_000),
    ];
    if (top) {
      jobs.push(
        warm(["campaign", top.id], () => api.campaign(top.id), 30_000),
        warm(["graph", top.id], () => api.graph(top.id), 5 * 60_000),
        warm(["sweep", top.id], () => api.sweep(top.id), 5 * 60_000),
        warm(["benchmark", top.id, 5], () => api.benchmark(top.id, 5, false)),
      );
    }
    await Promise.all(jobs);
  } catch {
    // best-effort by design: the views fetch on their own
  }
}
