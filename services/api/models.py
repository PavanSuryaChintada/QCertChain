"""Pydantic v2 models — field for field with docs/API_CONTRACT.md. Enum strings are exact."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DomainStatus = Literal["candidate", "confirmed", "dismissed", "unreachable"]
StreamMode = Literal["live", "replay"]
ConnState = Literal["connected", "reconnecting", "down", "replay"]
Backend = Literal["cpsat", "qaoa", "annealing", "greedy"]
NodeKind = Literal["ip", "asn", "nameserver", "cert_issuer", "kit_hash", "favicon_hash", "registrar"]
SignalStrength = Literal["strong", "moderate", "weak"]
Provenance = Literal["model", "rules"]
Source = Literal["certstream", "replay", "seed", "email", "sample"]
Verdict = Literal["confirmed", "dismissed", "disputed"]


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class Page(BaseModel, Generic[T]):
    """Keyset pagination: pass next_cursor back as ?cursor= for the next page; null = last page."""
    items: list[T]
    limit: int
    next_cursor: str | None = None


class CandidateCounts(BaseModel):
    all: int
    candidate: int
    confirmed: int
    dismissed: int
    unreachable: int


# ---- stream ----------------------------------------------------------------------------------------
class StreamState(BaseModel):
    mode: StreamMode
    connection: ConnState
    certs_per_sec: float = 0
    names_per_sec: float = 0
    candidates_per_min: float = 0
    queue_depth: dict[str, int] = Field(default_factory=dict)
    replay_file: str | None = None
    uptime_s: int | None = None
    last_heartbeat: datetime | None = None


class ModeRequest(BaseModel):
    mode: StreamMode
    speed: float = Field(1.0, gt=0, le=1000)


# ---- domains ---------------------------------------------------------------------------------------
class CandidateItem(BaseModel):
    id: int
    name: str
    etld1: str
    status: DomainStatus
    triage_score: float | None
    brand_matched: str | None
    confidence: float | None
    campaign_id: str | None
    first_seen: datetime
    source: Source


class Reason(BaseModel):
    feature: str
    value: Any = None
    contribution: float


class TriageOut(BaseModel):
    score: float | None
    provenance: Provenance
    threshold: float
    reasons: list[Reason]


class SignalOut(BaseModel):
    name: str
    strength: SignalStrength
    detail: str


class ConfirmationOut(BaseModel):
    verdict: str
    confidence: float | None
    confirmed_at: datetime | None
    signals: list[SignalOut]
    strong_count: int
    screenshot_url: str | None


class EnrichmentOut(BaseModel):
    ip_addresses: list[str] = []
    asn: int | None = None
    asn_name: str | None = None
    country: str | None = None
    nameservers: list[str] = []
    cert_issuer: str | None = None
    registrar: str | None = None
    registered_at: datetime | None = None
    dom_hash: str | None = None
    favicon_hash: str | None = None
    partial: bool = False
    errors: dict | None = None


class DomainDetail(BaseModel):
    id: int
    name: str
    etld1: str
    status: DomainStatus
    source: Source
    first_seen: datetime
    last_seen: datetime
    triage: TriageOut
    confirmation: ConfirmationOut | None
    enrichment: EnrichmentOut | None
    campaign_id: str | None
    evidence_bundle_id: str | None


# ---- campaigns -------------------------------------------------------------------------------------
class CampaignOut(BaseModel):
    id: str
    label: str | None
    kit_hash: str | None
    domain_count: int
    infra_count: int
    confidence: float | None
    brands: list[str]
    status: str
    first_seen: datetime
    last_seen: datetime | None = None
    published_tx: str | None
    anchored: bool = False
    has_plan: bool = False


class GraphOut(BaseModel):
    """Compact campaign graph (precomputed). domains: [id, name, status]; nodes: [id, kind, value, domain_count,
    targetable] (targetable = ip / nameserver / registrar, the takedown routes); edges: [domain_id, node_id,
    weight]; targets: [node_id, rank] of the latest plan."""
    campaign_id: str
    n_targetable: int
    search_space_log2: int          # 2^n candidate takedown sets for n targetable nodes
    domains: list[list]
    nodes: list[list]
    edges: list[list]
    targets: list[list]
    built_at: datetime


class SweepTarget(BaseModel):
    node_id: int
    kind: str
    value: str
    kills: int
    route: str


class SweepPoint(BaseModel):
    k: int
    backend: str
    domains_killed: int
    domains_total: int
    coverage_pct: float
    solve_ms: int
    valid: bool
    notes: list[str]
    targets: list[SweepTarget]
    killed_ids: list[int]


class SweepOut(BaseModel):
    """CP-SAT for every budget k = 1..10 (fewer if there are fewer targetable nodes): the slider is a lookup."""
    campaign_id: str
    n_targetable: int
    search_space_log2: int
    cached: bool
    points: list[SweepPoint]


# ---- interdiction ----------------------------------------------------------------------------------
class InterdictRequest(BaseModel):
    k: int = Field(5, ge=1)
    backend: Backend = "cpsat"
    timeout_s: float = Field(10.0, gt=0, le=60)


class TargetOut(BaseModel):
    rank: int
    node_id: int
    kind: NodeKind
    value: str
    kills: int
    takedown_route: str


class PlanOut(BaseModel):
    plan_id: str
    campaign_id: str
    budget_k: int
    backend: Backend
    fell_back: bool
    fallback_from: str | None
    objective: float
    domains_killed: int
    domains_total: int
    coverage_pct: float
    n_variables: int
    qubit_count: int | None
    solve_ms: int
    valid: bool
    targets: list[TargetOut]
    killed_domain_ids: list[int]
    notes: list[str] = []


class BenchmarkRowOut(BaseModel):
    backend: Backend
    objective: float
    domains_killed: int
    coverage_pct: float
    solve_ms: int
    valid: bool
    qubit_count: int | None
    n_variables: int
    is_best: bool
    error: str | None = None
    notes: list[str] = []


class BenchmarkOut(BaseModel):
    plan_id: str
    n_variables: int
    rows: list[BenchmarkRowOut]
    note: str


# ---- evidence --------------------------------------------------------------------------------------
class ArtifactOut(BaseModel):
    name: str
    sha256: str
    size_bytes: int | None
    url: str


class EvidenceOut(BaseModel):
    id: str
    domain_id: int | None
    campaign_id: str | None
    bundle_root: str
    signature: str
    collector_pk: str
    partial: bool
    created_at: datetime
    anchored_tx: str | None
    anchored_at: datetime | None
    artifacts: list[ArtifactOut]


class FailureOut(BaseModel):
    artifact: str
    expected: str | None
    found: str | None
    reason: str


class AnchorCheck(BaseModel):
    status: Literal["matches", "mismatch", "not_anchored", "unavailable"]
    tx: str | None = None


class MerkleTree(BaseModel):
    leaves: list[dict]       # [{name, leaf}] in leaf order (sorted by artifact name)
    levels: list[list[str]]  # leaf hashes first, the root last


class VerifyOut(BaseModel):
    """Three independent checks: the recomputed Merkle root, the Ed25519 signature, and the hash anchored on chain.
    simulated_tamper names the artifact whose bytes were flipped IN MEMORY for the demo (stored evidence is never
    modified)."""
    valid: bool
    root_matches: bool
    signature_valid: bool
    expected_root: str | None = None
    computed_root: str | None = None
    failures: list[FailureOut]
    anchor: AnchorCheck | None = None
    tree: MerkleTree | None = None
    attestations: dict[str, str] = {}
    disputed: bool = False
    simulated_tamper: str | None = None


class ReportOut(BaseModel):
    bundle_id: str
    recipient: str | None
    format: Literal["markdown"] = "markdown"
    body: str
    sent: Literal[False] = False
    generated_at: datetime


# ---- ops / seed ------------------------------------------------------------------------------------
class Metrics(BaseModel):
    campaigns_active: int
    domains_confirmed: int
    domains_candidate: int
    certs_per_sec: float
    plans_today: int
    bundles_today: int
    anchor_queue_depth: int


class OpsLogItem(BaseModel):
    id: int
    at: datetime
    channel: str
    severity: int
    message: str
    context: dict | None


class SeedRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=40)
    domains: int = Field(400, ge=2, le=2000)
    ips: int = Field(12, ge=1, le=200)
    asns: int = Field(3, ge=1, le=6)
    nameservers: int = Field(4, ge=1, le=50)
    registrars: int = Field(3, ge=1, le=26)
    brands: list[str] = ["ICICI Bank"]
