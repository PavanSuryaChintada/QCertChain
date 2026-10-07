"""What the formulation panel shows: QUBO size, qubits, circuit depth, and what the reduction discarded."""
import pytest

from interdict.benchmark import formulation
from interdict.types import Problem

P = Problem(tuple("abcdef"), {"d1": frozenset("a"), "d2": frozenset("a"), "d3": frozenset("ab"),
                              "d4": frozenset("c"), "d5": frozenset(), "d6": frozenset("f")},
            {f"d{i}": 1.0 for i in range(1, 7)}, 2)


def test_reduction_reports_what_it_kept_and_discarded():
    f = formulation(P, with_circuit=False)
    r = f["reduction"]
    assert r["original_nodes"] == 6 and r["original_domains"] == 6
    assert r["collapsed_groups"] == 4            # {a}x2 collapse; {a,b}, {c}, {f}; d5 has no takedownable node
    assert r["kept_nodes"] == f["qubo_variables"] <= 6
    assert r["pruned_nodes"] == 6 - r["kept_nodes"] and r["unreachable_weight"] == 1.0
    assert f["circuit_depth"] is None and f["p_layers"] == 3 and f["shots"] == 1024


def test_circuit_depth_is_measured_when_qiskit_is_present():
    pytest.importorskip("qiskit")
    f = formulation(P, with_circuit=True)
    assert f["qubit_count"] == f["qubo_variables"] and f["circuit_depth"] > 0
