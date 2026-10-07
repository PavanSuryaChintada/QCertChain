"""Scaling benchmark (A1c): why takedown planning is NP-hard, measured instead of asserted.

Synthetic campaigns with n targetable nodes (n = 10 .. 80) and a budget that grows with the campaign, k = n/4.
For each n: CP-SAT, greedy and QAOA (on its reduced <= 12-qubit problem) are TIMED; exhaustive search is TIMED where
n <= 22 and EXTRAPOLATED beyond (plans to check, C(n, k), times the measured cost per plan). The output marks every
extrapolated value as such. The n at which exhaustive search passes 1 second, 1 hour and 1 year is computed from the
same measured rate.

    python -m scripts.scaling_benchmark            -> reports/scaling.json (served by GET /scaling)
"""
from __future__ import annotations

import json
import math
import os
import platform
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from interdict.router import run_one
from interdict.solvers.bruteforce import MAX_NODES, solve_bruteforce
from interdict.solvers.cpsat import solve_cpsat
from interdict.types import Problem

NS = (10, 15, 20, 25, 30, 40, 60, 80)
CALIBRATE = (18, 20, 22)          # extra exhaustive runs to fit the cost per plan
DOMAINS_PER_NODE = 15
OUT = Path(__file__).resolve().parent.parent / "reports/scaling.json"
YEAR_MS = 365.25 * 24 * 3600 * 1000


def k_for(n: int) -> int:
    return max(2, n // 4)


def campaign(n: int, seed: int = 7) -> Problem:
    """Zipf-ish shared infrastructure: a few nodes host many domains, most host few; each domain depends on 1-3
    nodes. Weights 1-3."""
    rng = random.Random(f"{seed}:{n}")
    nodes = tuple(f"n{i}" for i in range(n))
    pop = [1 / (i + 1) ** 0.8 for i in range(n)]
    deps = {}
    for j in range(DOMAINS_PER_NODE * n):
        deps[f"d{j}"] = frozenset(rng.choices(nodes, weights=pop, k=rng.randint(1, 3)))
    return Problem(nodes, deps, {d: float(rng.randint(1, 3)) for d in deps}, k_for(n))


def _timed(fn):
    t = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t) * 1000


def main() -> None:
    import interdict.router
    interdict.router.ISOLATE_QAOA = False  # this script owns its process
    points, rate_samples = [], []
    warm = campaign(8)  # library start-up (OR-Tools load, Qiskit import) is not solve time: warm before timing
    solve_cpsat(warm, timeout_s=5)
    try:
        run_one(warm, "qaoa", timeout_s=60, max_vars=24)
    except Exception:
        pass
    for n in CALIBRATE:
        p = campaign(n)
        (_, plans), ms = _timed(lambda: solve_bruteforce(p))
        rate_samples.append(ms * 1e6 / plans)
    for n in NS:
        p = campaign(n)
        k, plans = p.k, math.comb(n, p.k)
        stats: dict = {}
        cp_targets, cp_ms = _timed(lambda: solve_cpsat(p, timeout_s=30, stats=stats))
        (g_out, g_killed, g_ms) = run_one(p, "greedy", timeout_s=30, max_vars=24)
        pt = {"n": n, "k": k, "subsets_log2": n, "plans_log2": round(math.log2(plans), 2), "plans_at_k": plans,
              "cpsat_ms": round(cp_ms, 1), "cpsat_status": stats.get("status"),
              "greedy_ms": g_ms, "coverage": {"cpsat": round(p.objective(cp_targets), 1),
                                               "greedy": round(p.objective(g_out.targets), 1)}}
        if n <= MAX_NODES:
            (bf, _), bf_ms = _timed(lambda: solve_bruteforce(p))
            rate_samples.append(bf_ms * 1e6 / plans)
            pt.update(bruteforce_ms=round(bf_ms, 1), bruteforce_extrapolated=False)
            pt["coverage"]["bruteforce"] = round(p.objective(bf), 1)
        else:
            pt.update(bruteforce_ms=None, bruteforce_extrapolated=True)
        try:
            q_out, q_killed, q_ms = run_one(p, "qaoa", timeout_s=60, max_vars=24)
            pt.update(qaoa_ms=q_ms, qaoa_note=f"on the reduced problem ({q_out.qubit_count} qubits): "
                                              + "; ".join(q_out.notes))
            pt["coverage"]["qaoa"] = round(p.objective(q_out.targets), 1)
        except Exception as e:  # Qiskit absent or over budget: the row says so, it is not dropped
            pt.update(qaoa_ms=None, qaoa_note=f"{type(e).__name__}: {e}"[:200])
        points.append(pt)
    ns_per_plan = statistics.median(rate_samples)
    for pt in points:
        est = pt["plans_at_k"] * ns_per_plan / 1e6
        pt["bruteforce_estimate_ms"] = round(est, 3)
        if pt["bruteforce_extrapolated"]:
            pt["bruteforce_ms"] = round(est, 3)

    def crossing(limit_ms: float) -> int | None:
        for n in range(4, 1000):
            if math.comb(n, k_for(n)) * ns_per_plan / 1e6 > limit_ms:
                return n
        return None

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "k_rule": "n/4", "k": "n/4",
           "method": (f"Synthetic campaigns, {DOMAINS_PER_NODE} domains per targetable node, Zipf-shaped sharing, "
                      "budget k = n/4. CP-SAT, greedy and QAOA are timed at every n. Exhaustive search checks all "
                      f"C(n, k) plans; it is timed for n <= {MAX_NODES} and extrapolated above (C(n, k) x the "
                      "measured cost per plan). QAOA runs on the reduced problem (<= 12 qubits)."),
           "machine": f"{platform.processor() or platform.machine()}, {os.cpu_count()} logical CPUs, "
                      f"Python {platform.python_version()}",
           "fit": {"ns_per_subset": round(ns_per_plan, 2), "samples": len(rate_samples)},
           "thresholds": {"one_second": {"n": crossing(1e3)}, "one_hour": {"n": crossing(3.6e6)},
                          "one_year": {"n": crossing(YEAR_MS)}},
           "points": points}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for pt in points:
        bf = f"{pt['bruteforce_ms']:,.1f} ms" + (" (extrapolated)" if pt["bruteforce_extrapolated"] else "")
        print(f"n={pt['n']:>2} k={pt['k']:>2} plans=2^{pt['plans_log2']:<5} exhaustive={bf:>34}  "
              f"cpsat={pt['cpsat_ms']:>8.1f} ms {pt['cpsat_status']:<8} greedy={pt['greedy_ms']} ms  "
              f"qaoa={pt['qaoa_ms']} ms")
    print("thresholds:", out["thresholds"], "ns/plan:", out["fit"]["ns_per_subset"])


if __name__ == "__main__":
    main()
