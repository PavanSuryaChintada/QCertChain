"""Campaign clustering (TRD §4). Deterministic: the edges are facts, not predictions.

Connected components over edges with weight >= 0.6 (kit hash, favicon, IP, nameserver), then merge
components that share >= 2 distinct medium-weight nodes (0.3 <= w < 0.6, i.e. ASN). Shared ASN or
cert issuer alone never merges: that would fold half the internet into one campaign.
Do not lower the threshold to make a campaign look bigger.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

import networkx as nx


@dataclass
class Cluster:
    domain_ids: set[int]
    node_ids: set[int] = field(default_factory=set)
    confidence: float = 0.0


def cluster(edges: list[tuple[int, int, float]], threshold: float = 0.6, medium_floor: float = 0.3) -> list[Cluster]:
    g = nx.Graph()
    domains: set[int] = set()
    for d, n, w in edges:
        domains.add(d)
        g.add_node(("d", d))
        if w >= threshold:
            g.add_edge(("d", d), ("n", n), weight=w)
    comp_of: dict[int, int] = {}
    comps: list[set[int]] = []
    for comp in nx.connected_components(g):
        members = {k for kind, k in comp if kind == "d"}
        if members:
            for d in members:
                comp_of[d] = len(comps)
            comps.append(members)

    # merge on >= 2 distinct shared medium-weight nodes
    medium_touch: dict[int, set[int]] = defaultdict(set)
    for d, n, w in edges:
        if medium_floor <= w < threshold:
            medium_touch[n].add(comp_of[d])
    shared: Counter[tuple[int, int]] = Counter()
    for touched in medium_touch.values():
        for a, b in combinations(sorted(touched), 2):
            shared[(a, b)] += 1
    parent = list(range(len(comps)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), count in shared.items():
        if count >= 2:
            parent[find(a)] = find(b)
    merged: dict[int, set[int]] = defaultdict(set)
    for i, members in enumerate(comps):
        merged[find(i)] |= members

    by_domain: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for d, n, w in edges:
        by_domain[d].append((n, w))
    out = []
    for members in merged.values():
        if len(members) < 2:
            continue  # a single domain is not a campaign
        nodes = {n for d in members for n, _ in by_domain[d]}
        strong = [w for d in members for _, w in by_domain[d] if w >= threshold]
        out.append(Cluster(set(members), nodes, round(sum(strong) / len(strong), 4) if strong else 0.0))
    out.sort(key=lambda c: (-len(c.domain_ids), min(c.domain_ids)))
    return out
