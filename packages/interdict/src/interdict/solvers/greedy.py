"""Classic max-coverage greedy. Stdlib only, cannot fail, (1 - 1/e) approximation guarantee."""
from __future__ import annotations

from interdict.types import Problem


def solve_greedy(p: Problem) -> list[str]:
    covers: dict[str, set[str]] = {v: set() for v in p.nodes}
    for d, s in p.deps.items():
        for v in s:
            if v in covers:
                covers[v].add(d)
    chosen: list[str] = []
    dead: set[str] = set()
    for _ in range(min(p.k, len(p.nodes))):
        best, gain = None, 0.0
        for v in sorted(covers):  # sorted: deterministic tie-break on id
            if v in chosen:
                continue
            g = sum(p.weights[d] for d in covers[v] - dead)
            if g > gain:
                best, gain = v, g
        if best is None:
            break
        chosen.append(best)
        dead |= covers[best]
    return chosen
