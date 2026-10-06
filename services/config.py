"""Single source of configuration. Never hardcode a setting twice (TRD §8)."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    test_database_url: str = "postgresql+psycopg://qcertchain:qcertchain@localhost:5433/qcertchain_test"
    redis_url: str = "redis://localhost:6379"
    certstream_url: str = "ws://localhost:8080/full-stream"
    stream_mode: str = "live"
    replay_file: str = "data/capture.jsonl"
    replay_speed: float = 1.0
    triage_threshold: float = 0.45
    triage_model_path: str = "services/ml/artifacts/triage_lr.joblib"
    brands_file: str = "data/brands.yaml"
    allowlist_file: str = "data/allowlist.txt"
    confirm_timeout_s: float = 15.0
    enrich_workers: int = 4
    per_host_rate_limit_s: float = 2.0
    user_agent: str = "QCertChain-Scanner/0.1 (phishing research)"
    cluster_edge_threshold: float = 0.6
    interdict_budget_k: int = 5
    interdict_backend: str = "cpsat"
    max_qubo_variables: int = 24
    evidence_dir: str = "data/evidence"
    collector_private_key: str = ""
    chain_rpc: str = "http://localhost:8545"
    org_private_key: str = ""
    org2_private_key: str = ""
    raw_cert_retention_h: int = 24


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


def load_settings(env_file: Path | None = None) -> Settings:
    file_vals = _parse_env_file(env_file or ROOT / ".env")
    kwargs = {}
    for f in fields(Settings):
        raw = os.environ.get(f.name.upper(), file_vals.get(f.name.upper()))
        if raw is None or raw == "":
            continue
        typ = type(f.default)
        kwargs[f.name] = typ(raw) if typ in (int, float) else raw
    return Settings(**kwargs)


SETTINGS = load_settings()
