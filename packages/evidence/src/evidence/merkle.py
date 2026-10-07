"""SHA-256 Merkle tree with domain-separated leaves and nodes (BLOCKCHAIN.md §5).

leaf  = sha256(0x00 || name || 0x00 || sha256(content))   -- the name is bound: renaming changes the root
node  = sha256(0x01 || left || right)
An odd node at any level is promoted unchanged. Empty tree = sha256(b"").
Callers MUST pass leaves sorted by artifact name: the same evidence must always yield the same root.
"""
from __future__ import annotations

import hashlib


def leaf_hash(name: str, content_sha256: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + name.encode("utf-8") + b"\x00" + content_sha256).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    level = list(leaves)
    while len(level) > 1:
        nxt = [hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def merkle_levels(leaves: list[bytes]) -> list[list[bytes]]:
    """Every level of the tree, leaves first and the root last (same pairing rule as merkle_root): for drawing it."""
    if not leaves:
        return [[hashlib.sha256(b"").digest()]]
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        level = levels[-1]
        nxt = [hashlib.sha256(b"" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        levels.append(nxt)
    return levels
