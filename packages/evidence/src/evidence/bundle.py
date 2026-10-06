"""Evidence bundles: artifacts on disk, SHA-256 Merkle root over SORTED leaves, Ed25519 signature over the root.

verify_bundle never answers just "failed": it names the artifact and both hashes (BLOCKCHAIN.md §5).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import nacl.exceptions
import nacl.signing

from evidence.merkle import leaf_hash, merkle_root

PK_PREFIX = "ed25519:"


@dataclass
class ArtifactMeta:
    name: str
    sha256: str
    size_bytes: int


@dataclass
class Bundle:
    bundle_id: str
    root: str
    signature: str
    collector_pk: str
    artifacts: list[ArtifactMeta]
    partial: bool
    dir: str


@dataclass
class Failure:
    artifact: str
    expected: str | None
    found: str | None
    reason: Literal["hash_mismatch", "missing", "unexpected"]


@dataclass
class VerifyResult:
    valid: bool
    root_matches: bool
    signature_valid: bool
    expected_root: str
    computed_root: str
    failures: list[Failure] = field(default_factory=list)


def _safe_name(name: str) -> str:
    if not name or name != Path(name).name or name in (".", ".."):
        raise ValueError(f"artifact name must be a plain file name: {name!r}")
    return name


def root_of(hashes: dict[str, str]) -> str:
    """Merkle root over {name: sha256 hex}, leaves sorted by name (deterministic)."""
    return merkle_root([leaf_hash(n, bytes.fromhex(hashes[n])) for n in sorted(hashes)]).hex()


def build_bundle(out_dir: Path | str, bundle_id: str, artifacts: dict[str, bytes], signing_key_hex: str,
                 partial: bool = False) -> Bundle:
    d = Path(out_dir) / bundle_id
    d.mkdir(parents=True, exist_ok=True)
    metas = []
    for name in sorted(artifacts):
        data = artifacts[_safe_name(name)]
        (d / name).write_bytes(data)
        metas.append(ArtifactMeta(name, hashlib.sha256(data).hexdigest(), len(data)))
    root = root_of({m.name: m.sha256 for m in metas})
    key = nacl.signing.SigningKey(bytes.fromhex(signing_key_hex))
    sig = key.sign(bytes.fromhex(root)).signature.hex()
    return Bundle(bundle_id, root, sig, PK_PREFIX + key.verify_key.encode().hex(), metas, partial, str(d))


def verify_bundle(bundle_dir: Path | str, expected_root: str, signature: str, public_key: str,
                  expected: dict[str, str]) -> VerifyResult:
    """Recompute every artifact hash, rebuild the root, check the signature over the expected root.
    `expected` is the recorded {name: sha256} (from the database), never re-read from the bundle itself."""
    d = Path(bundle_dir)
    failures: list[Failure] = []
    found: dict[str, str] = {}
    present = {p.name for p in d.iterdir() if p.is_file()} if d.exists() else set()
    for name in sorted(expected):
        if name not in present:
            failures.append(Failure(name, expected[name], None, "missing"))
            continue
        h = hashlib.sha256((d / name).read_bytes()).hexdigest()
        found[name] = h
        if h != expected[name]:
            failures.append(Failure(name, expected[name], h, "hash_mismatch"))
    for name in sorted(present - set(expected)):
        failures.append(Failure(name, None, hashlib.sha256((d / name).read_bytes()).hexdigest(), "unexpected"))
    computed = root_of({**found, **{n: "00" * 32 for n in expected if n not in found}}) if expected else root_of({})
    try:
        vk_hex = public_key.removeprefix(PK_PREFIX)
        nacl.signing.VerifyKey(bytes.fromhex(vk_hex)).verify(bytes.fromhex(expected_root), bytes.fromhex(signature))
        sig_ok = True
    except (nacl.exceptions.BadSignatureError, ValueError):
        sig_ok = False
    root_ok = computed == expected_root
    return VerifyResult(valid=root_ok and sig_ok and not failures, root_matches=root_ok, signature_valid=sig_ok,
                        expected_root=expected_root, computed_root=computed, failures=failures)
