# NPHARD — the interdiction problem

The core contribution. Read this before writing anything in `packages/interdict/`.

---

## 1. The question

A campaign has 400 domains standing on shared infrastructure: 12 hosting IPs, 3 ASNs, 4 nameservers, 2 certificate issuers, 1 phishing kit.

**You cannot take down 400 things.** Registrars rate-limit, each report needs assembled evidence, and each takes hours to action.

So:

> **Which smallest set of takedown targets kills the most phishing domains?**

Take down one hosting IP and 300 domains die. Take down a nameserver and the rest go dark.

---

## 2. Why it is NP-hard

Each domain *d* depends on a set of infrastructure nodes **S(d)** — its IP, its nameserver, its certificate issuer, its kit host.

A domain dies if **any one** of its dependencies is removed.

So each infrastructure node *v* "covers" the set of domains that depend on it. Choosing *k* nodes to maximise the number of domains covered is **maximum coverage** — a classic NP-hard problem, and not approximable better than 1−1/e unless P=NP.

**This is the correct name for it. Use it.** Do not call it "network interdiction" or "graph partitioning" — a judge who knows the field will notice.

---

## 3. Formulation

### Variables

```
x_v ∈ {0,1}   take down infrastructure node v
y_d ∈ {0,1}   domain d is killed
```

### Objective

```
maximise   Σ_d  w_d · y_d
```

`w_d` is the domain's weight — default 1, optionally scaled by observed traffic, brand criticality, or whether credentials have already been posted to it.

### Constraints

```
(C1)  y_d  ≤  Σ_{v ∈ S(d)} x_v        domain dies only if a dependency is removed
(C2)  Σ_v x_v  ≤  k                    takedown budget
```

`k` defaults to 5. It is the analyst's lever.

---

## 4. Reference implementation — OR-Tools CP-SAT

**This is what runs in production.** Build it first.

```python
from ortools.sat.python import cp_model

def solve_cpsat(nodes, domains, deps, weights, k, timeout_s=10.0):
    """
    nodes    : list[str]                infrastructure node ids
    domains  : list[str]                domain ids
    deps     : dict[str, set[str]]      domain -> set of node ids it depends on
    weights  : dict[str, float]         domain -> weight
    k        : int                      takedown budget
    """
    m = cp_model.CpModel()
    x = {v: m.NewBoolVar(f"x_{v}") for v in nodes}
    y = {d: m.NewBoolVar(f"y_{d}") for d in domains}

    for d in domains:
        covering = [x[v] for v in deps[d] if v in x]
        if covering:
            m.Add(y[d] <= sum(covering))
        else:
            m.Add(y[d] == 0)          # unreachable by any takedown

    m.Add(sum(x.values()) <= k)
    m.Maximize(sum(int(weights[d] * 1000) * y[d] for d in domains))

    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = timeout_s
    s.parameters.num_search_workers = 8
    r = s.Solve(m)
    ...
```

**Trap:** CP-SAT wants integer objectives. Scale float weights by 1000 and round. Do not pass floats.

---

## 5. Reduction — do this before any QUBO

A 400-domain campaign has too many variables for a simulator. Reduce classically first. **This is the same move as the zone partition that worked before, and it is honest, not a shortcut.**

### 5a · Collapse domains by dependency signature

Hundreds of domains usually share an identical dependency set. Group them.

```python
def collapse(deps, weights):
    """400 domains -> ~15 groups with identical S(d)."""
    groups = {}
    for d, s in deps.items():
        key = frozenset(s)
        groups.setdefault(key, []).append(d)
    return [
        {"id": f"grp{i}", "deps": set(key),
         "weight": sum(weights[d] for d in members),
         "members": members}
        for i, (key, members) in enumerate(groups.items())
    ]
```

### 5b · Prune dominated nodes

If node A covers a strict subset of node B's coverage and costs the same, drop A.

### 5c · Keep the top-C candidates

Rank remaining nodes by weighted coverage, keep the top **C = 12**.

### Resulting size

```
400 domains, 21 nodes
   → collapse   → ~14 groups
   → prune+top  → 12 candidate nodes
   → QUBO       = 12 + 14 = 26 variables
```

**Hard cap: 24 qubits.** Aer statevector is ~268 MB at 24 qubits and ~17 GB at 30 — the process dies. If reduction leaves more than 24, lower `C` until it fits, and **log that you did**.

---

## 6. QUBO form

> **Correction (2026-10-06, implementation).** The penalty form below rewards over-coverage: each
> extra selected node covering an already-covered group subtracts λ₁, and the budget penalty does
> **not** cap it (competing plans both pick exactly k). Counter-example: g1={a,b} w=5, g2={c} w=1,
> k=2 → the energy prefers {a,b} (−11) over the true optimum {a,c} (−6). `packages/interdict/qubo.py`
> therefore uses the **x-only** formulation `value(g) = w_g·[1 − Π(1 − x_v)]` expanded to second
> order (exact for ≤ 2 dependencies per group; under-values only all-dependencies-selected cases),
> plus `λ₂(Σx − k)²`. One qubit per candidate node — ≤ 12 after reduction instead of 26.
> Tested by brute-force ground-state checks in `tests/test_qubo.py`. The text below is the original
> specification, kept for the record.

Penalty form of the same problem:

```
H  =  − Σ_g w_g · y_g                                   (reward)
      + λ₁ · Σ_g [ y_g − Σ_{v ∈ S(g)} x_v · y_g ]       (coverage penalty)
      + λ₂ · ( Σ_v x_v − k )²                            (budget penalty)
```

### Reading the coverage term

For group *g*:

| Situation | Term value | Effect |
|---|---|---|
| No selected node covers *g* | `+λ₁ · y_g` | Claiming the kill costs λ₁. If λ₁ > max w, never worth it. |
| Exactly one covers it | `0` | Free. Correct. |
| Two or more cover it | `−λ₁ · y_g` | A small bonus for over-coverage. |

**The third row is a known imperfection.** It creates a mild pull toward redundant coverage, which the budget penalty caps. Document it in the code comment. Do not hide it — a reviewer will spot it, and having flagged it first is worth more than pretending it isn't there.

### Penalty calibration — compute at runtime, never hardcode

```python
lam1 = 1.2 * max(w.values())          # must exceed the largest single reward
lam2 = 1.2 * sum(w.values())          # budget must dominate everything
```

**Why 1.2 and not 10:** λ must exceed the maximum gain from violating the constraint, or violating is rational. But oversized penalties flatten the energy landscape and stall COBYLA inside QAOA — every feasible solution starts to look identical. 1.2 is the smallest safe margin.

---

## 7. QAOA backend

```python
p              = 3                  # ansatz depth
optimizer      = COBYLA(maxiter=150)
shots          = 1024               # take the BEST bitstring, not the mean
warm_start     = greedy solution    # not random initialisation
aer_method     = "statevector"      # "matrix_product_state" for headroom
max_variables  = 24                 # hard guard, raise if exceeded
```

### Traps

**Ising sign convention.** Substitute `x = (1 − z)/2` to build the `SparsePauliOp`. **Verify it:** on a 4-variable instance, brute-force all 16 assignments and confirm the Ising energy ordering matches the QUBO objective ordering exactly. Get this backwards and QAOA confidently returns the *worst* plan.

**Keep Q upper-triangular.** Always store at `(min(i,j), max(i,j))`. Writing both `(i,j)` and `(j,i)` double-counts every quadratic term and silently doubles your penalties.

**Timeout.** COBYLA takes no wall-clock limit. Check elapsed time in the cost-function callback and raise to trigger the fallback.

**Lazy import.** `from qiskit_aer...` goes *inside* `solve()`, never at module top level. Package import must succeed with Qiskit absent.

---

## 8. Solver router

```python
CHAINS = {
    "cpsat":     ["cpsat", "greedy"],
    "qaoa":      ["qaoa", "cpsat", "greedy"],
    "annealing": ["annealing", "cpsat", "greedy"],
    "greedy":    ["greedy"],
}
```

For each solver in the chain: run it, catch **every** exception including `ImportError`, validate, return on success with `fell_back` set. If greedy fails, raise — that is a genuine bug.

**Default backend is `cpsat`.** QAOA is opt-in.

### Validation gate

```python
def validate(plan, nodes, deps, k):
    assert len(plan.targets) <= k
    assert set(plan.targets) <= set(nodes)
    killed = {d for d in deps if deps[d] & set(plan.targets)}
    assert killed == set(plan.killed_domains)
```

Nothing leaves the package unvalidated.

---

## 9. Greedy baseline

Classic max-coverage greedy: repeatedly pick the node covering the most remaining weight. Stdlib only, cannot fail, and gives the **(1 − 1/e) ≈ 63% approximation guarantee** — which is worth stating in the benchmark table as the theoretical floor.

Also used to warm-start QAOA.

---

## 10. Benchmark output

`benchmark(problem, backends=["cpsat","qaoa","annealing","greedy"])` returns per backend:

| Field | |
|---|---|
| `backend` | name |
| `objective` | weighted domains killed |
| `domains_killed` / `domains_total` | raw coverage |
| `coverage_pct` | |
| `solve_ms` | wall clock |
| `targets` | the chosen nodes |
| `valid` | passed validation |
| `n_variables` / `qubit_count` | problem size |

**Report it exactly as measured.** At 24 variables CP-SAT will match or beat QAOA and will be far faster. A table where the quantum backend wins every row reads as fabricated; honest parity reads as engineering.

---

## 11. Package layout

```
packages/interdict/
├── README.md
├── pyproject.toml            # quantum extra optional
├── src/interdict/
│   ├── types.py              # Campaign, InterdictionPlan, BenchmarkRow
│   ├── reduce.py             # collapse, prune, top-C
│   ├── qubo.py               # build_qubo, evaluate
│   ├── penalties.py          # runtime λ calibration
│   ├── router.py             # solve() + fallback chain + validate
│   ├── benchmark.py
│   └── solvers/
│       ├── base.py  greedy.py  cpsat.py  annealing.py  qaoa.py
└── tests/
    ├── test_interdict.py     # RELEASE GATE: 500 random instances
    ├── test_fallback.py      # RELEASE GATE: Qiskit absent
    ├── test_reduce.py        # collapse preserves total weight
    └── test_ising.py         # brute-force sign-convention check
```

**Zero imports from `services/` or `apps/`.** MIT licensed, publishable standalone.

---

## 12. Build order

1. `types.py`
2. `solvers/greedy.py` → `test_interdict.py` green on greedy
3. `solvers/cpsat.py` → **this is production, get it right**
4. `reduce.py` → `test_reduce.py`
5. `router.py` → `test_fallback.py`
6. `benchmark.py`
7. `qubo.py` + `penalties.py` → `test_ising.py`
8. `solvers/qaoa.py` — **last, and timeboxed**

**Do QAOA last.** It is the highest-risk piece and the one most likely to burn hours on a dependency conflict. Everything else must work without it.
