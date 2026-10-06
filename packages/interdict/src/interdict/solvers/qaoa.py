"""QAOA backend on the reduced QUBO (NPHARD.md §7). Qiskit 1.2.4 + Aer 0.15.1, imported lazily.

Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same
formulation runs on QAOA. Quantum is not in the critical path.

- Ising map: x = (1 - z) / 2, qubit i <-> bit i (Qiskit is little-endian). Verified by brute force
  in tests/test_ising.py: Ising energy + offset equals the QUBO energy for every bitstring.
- Ansatz: QAOAAnsatz, p = 3, initial state biased toward the greedy plan (Ry, epsilon = 0.25:
  warm start, not random initialisation).
- Optimiser: COBYLA (maxiter 150). COBYLA has no wall-clock limit, so the cost function checks
  elapsed time and raises TimeoutError, which the router turns into a fallback.
- Read-out: 1024 shots; every sampled bitstring is scored on the QUBO and the BEST is returned,
  then trimmed to the budget if the penalty was violated.
"""
from __future__ import annotations

import math
import time

from interdict.qubo import build_qubo, decode, qubo_energy
from interdict.solvers.greedy import solve_greedy
from interdict.types import Problem

P_DEPTH = 3
MAXITER = 150
SHOTS = 1024
MAX_VARIABLES = 24  # Aer statevector: ~268 MB at 24 qubits, ~17 GB at 30
WARM_EPS = 0.25


def qubo_to_ising(Q: dict[tuple[int, int], float], const: float, n: int):
    """Return (SparsePauliOp H, offset) with  <x|H|x> + offset == qubo_energy(Q, const, x)."""
    from qiskit.quantum_info import SparsePauliOp

    offset = const
    lin = [0.0] * n
    terms = []
    for (i, j), v in Q.items():
        if i == j:          # v x_i = v (1 - z_i)/2
            offset += v / 2
            lin[i] -= v / 2
        else:               # v x_i x_j = v (1 - z_i - z_j + z_i z_j)/4
            offset += v / 4
            lin[i] -= v / 4
            lin[j] -= v / 4
            terms.append(("ZZ", [i, j], v / 4))
    terms += [("Z", [i], c) for i, c in enumerate(lin) if c]
    if not terms:
        terms = [("Z", [0], 0.0)]
    return SparsePauliOp.from_sparse_list(terms, num_qubits=n).simplify(), offset


def solve_qaoa(p: Problem, timeout_s: float = 15.0, p_depth: int = P_DEPTH, shots: int = SHOTS,
               seed: int = 0) -> tuple[list[str], int]:
    import numpy as np
    from qiskit import QuantumCircuit, transpile
    from qiskit.circuit.library import QAOAAnsatz
    from qiskit_aer import AerSimulator
    from scipy.optimize import minimize

    Q, const, names = build_qubo(p)
    n = len(names)
    if n > MAX_VARIABLES:
        raise ValueError(f"{n} variables exceeds the {MAX_VARIABLES}-qubit cap; reduce first")
    if n == 0 or p.k <= 0:
        return [], n
    H, _ = qubo_to_ising(Q, const, n)

    warm = set(solve_greedy(p))
    init = QuantumCircuit(n)
    for i, v in enumerate(names):
        c = 1 - WARM_EPS if v in warm else WARM_EPS
        init.ry(2 * math.asin(math.sqrt(c)), i)
    ansatz = QAOAAnsatz(cost_operator=H, reps=p_depth, initial_state=init)
    t0 = time.perf_counter()
    sim = AerSimulator(method="statevector", seed_simulator=seed)
    # One transpile; each evaluation binds parameters and runs with save_expectation_value.
    # ~3x faster than EstimatorV2's per-call overhead (measured 57 vs 190 ms at 12 qubits).
    expv = ansatz.copy()
    expv.save_expectation_value(H, list(range(n)), label="energy")
    expv = transpile(expv, sim, optimization_level=1)
    order = list(ansatz.parameters)

    def cost(theta):
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError(f"qaoa exceeded {timeout_s}s")
        bound = expv.assign_parameters(dict(zip(order, theta)))
        return float(sim.run(bound).result().data(0)["energy"])

    # linear-ramp initial parameters (gammas small and increasing, betas decreasing)
    gammas = [0.1 * (i + 1) for i in range(p_depth)]
    betas = [0.4 * (1 - i / p_depth) for i in range(p_depth)]
    x0 = np.array(betas + gammas) if order[0].name.startswith("β") else np.array(gammas + betas)
    res = minimize(cost, x0, method="COBYLA", options={"maxiter": MAXITER})
    if time.perf_counter() - t0 > timeout_s:
        raise TimeoutError(f"qaoa exceeded {timeout_s}s before sampling")

    measured = ansatz.assign_parameters(dict(zip(order, res.x)))
    measured.measure_all()
    counts = sim.run(transpile(measured, sim, optimization_level=1), shots=shots).result().get_counts()
    best_bits, best_e = None, math.inf
    for bitstring in counts:
        bits = [int(b) for b in reversed(bitstring)]  # rightmost character is qubit 0
        e = qubo_energy(Q, const, bits)
        if e < best_e:
            best_bits, best_e = bits, e
    chosen = decode(best_bits, names)
    if len(chosen) > p.k:  # budget penalty violated in the best sample: keep the k best by marginal gain
        kept: list[str] = []
        for _ in range(p.k):
            kept.append(max((c for c in chosen if c not in kept), key=lambda c: p.objective(kept + [c])))
        chosen = kept
    return chosen, n
