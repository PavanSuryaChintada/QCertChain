"""Temporal and campaign-disjoint splits (MODELS.md §2). NEVER a random split on this data."""
from __future__ import annotations

import random
from datetime import datetime

from services.ml.datasets import campaign_key


def temporal_split(rows: list[dict], cutoff: datetime) -> tuple[list[dict], list[dict]]:
    """Train strictly before the cutoff, test at/after it — the honest one."""
    return [r for r in rows if r["seen"] < cutoff], [r for r in rows if r["seen"] >= cutoff]


def campaign_disjoint_split(rows: list[dict], test_fraction: float = 0.25, seed: int = 0
                            ) -> tuple[list[dict], list[dict]]:
    """Whole campaigns go to one side: no member of a test campaign is ever seen in training."""
    keys = sorted({campaign_key(r["etld1"]) for r in rows})
    rng = random.Random(seed)
    rng.shuffle(keys)
    test_keys = set(keys[: max(1, round(len(keys) * test_fraction))])
    return ([r for r in rows if campaign_key(r["etld1"]) not in test_keys],
            [r for r in rows if campaign_key(r["etld1"]) in test_keys])
