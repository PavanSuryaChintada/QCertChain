"""Validation gate (NPHARD.md §8). Nothing leaves the package unvalidated."""
from __future__ import annotations

from interdict.types import Problem


class PlanInvalid(Exception):
    pass


def validate(p: Problem, targets: list[str]) -> set[str]:
    """Return the killed domain set, or raise PlanInvalid."""
    if len(targets) != len(set(targets)):
        raise PlanInvalid(f"duplicate targets: {targets}")
    if len(targets) > p.k:
        raise PlanInvalid(f"{len(targets)} targets exceed budget k={p.k}")
    unknown = set(targets) - set(p.nodes)
    if unknown:
        raise PlanInvalid(f"targets not in the problem: {sorted(unknown)}")
    return p.coverage(targets)
