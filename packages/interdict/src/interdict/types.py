"""Problem and plan types for maximum-coverage takedown planning (NPHARD.md §3)."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Problem:
    """nodes: takedownable infrastructure ids. deps: domain -> nodes it depends on.
    A domain dies if ANY of its dependencies is taken down. Choose <= k nodes."""
    nodes: tuple[str, ...]
    deps: Mapping[str, frozenset[str]]
    weights: Mapping[str, float]
    k: int

    @property
    def domains(self) -> tuple[str, ...]:
        return tuple(self.deps)

    def coverage(self, targets: Iterable[str]) -> set[str]:
        t = set(targets)
        return {d for d, s in self.deps.items() if s & t}

    def objective(self, targets: Iterable[str]) -> float:
        return sum(self.weights[d] for d in self.coverage(targets))


@dataclass
class Plan:
    backend: str
    targets: list[str]
    killed: set[str]
    objective: float
    domains_total: int
    solve_ms: int
    valid: bool
    fell_back: bool = False
    fallback_from: str | None = None
    n_variables: int = 0
    qubit_count: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        return round(100.0 * len(self.killed) / self.domains_total, 2) if self.domains_total else 0.0
