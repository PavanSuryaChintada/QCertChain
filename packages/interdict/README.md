# interdict

Maximum-coverage takedown planning. Given domains that each depend on a set of infrastructure nodes
(a domain dies if **any** dependency is taken down), choose at most `k` nodes to kill the most weighted
domains. Maximum coverage is NP-hard and not approximable better than 1 − 1/e unless P = NP.

Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same
formulation runs on QAOA. Quantum is not in the critical path.

- `solve_cpsat` — production. Collapses identical dependency signatures, warm-starts from greedy, reports
  `OPTIMAL` vs `FEASIBLE` (time limit hit) with the optimality gap.
- `solve_greedy` — stdlib only, cannot fail, (1 − 1/e) guarantee.
- `validate` — every plan passes this gate: within budget, known nodes, no duplicates.

Zero imports from the rest of the QCertChain repository. MIT licensed. Qiskit is an optional extra.
