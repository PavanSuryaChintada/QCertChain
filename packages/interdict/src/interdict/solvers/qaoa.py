"""QAOA backend on the reduced QUBO. Implemented in Task 9; qiskit is imported lazily."""
from __future__ import annotations

from interdict.types import Problem


def solve_qaoa(p: Problem, timeout_s: float = 15.0) -> tuple[list[str], int]:
    import qiskit  # noqa: F401  lazy: package import must succeed without Qiskit
    import qiskit_aer  # noqa: F401

    raise NotImplementedError("QAOA solver body lands in Task 9")
