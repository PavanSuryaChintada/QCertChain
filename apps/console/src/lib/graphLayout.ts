import type { CampaignGraph, DomainStatus, NodeKind } from "./api";

// Deterministic layout, O(n), no physics. Each domain is clustered around its primary piece of infrastructure
// (hosting IP first). Infrastructure that is shared ACROSS clusters (nameservers, registrars, ASN, kit, CA...)
// sits in a band above the clusters, with one line per cluster it touches.

const ANCHOR_RANK: Record<NodeKind, number> = { ip: 0, nameserver: 1, registrar: 2, asn: 3, kit_hash: 4, favicon_hash: 5, cert_issuer: 6 };
const SPACING = 7;
const GOLDEN = 2.399963;

export const LAYOUT_WIDTH = 1200;
/** IBM Plex Mono advance is 0.6em; labels are 11.5px. */
export const CHAR_W = 6.9;
const BAND_ROW = 64;
const labelChars = (px: number) => Math.max(6, Math.floor((px - 12) / CHAR_W));
export function shortLabel(v: string, n: number): string {
  return v.length > n ? `${v.slice(0, n - 1)}…` : v;
}

export interface InfraPos {
  id: number; kind: NodeKind; value: string; domainCount: number; targetable: boolean; x: number; y: number; anchor: boolean;
  /** band nodes only: label baseline offset (staggered) and the characters that fit without touching a neighbour */
  labelDy?: number; labelChars?: number;
}
export interface DomainPos { id: number; name: string; status: DomainStatus; x: number; y: number; anchor: number | null }
export interface Link { from: number; to: number; count: number }
export interface Layout {
  width: number; height: number;
  infra: InfraPos[]; domains: DomainPos[]; links: Link[];
  clusters: { anchor: number | null; x: number; y: number; r: number; size: number; label: string }[];
  domainsByNode: Map<number, number[]>;
}

export function layoutGraph(g: CampaignGraph): Layout {
  const nodes = new Map(g.nodes.map(([id, kind, value, domain_count, targetable]) => [id, { id, kind, value, domainCount: domain_count, targetable }]));
  const domainsByNode = new Map<number, number[]>();
  const nodesOf = new Map<number, number[]>();
  for (const [d, n] of g.edges) {
    if (!nodes.has(n)) continue;
    (domainsByNode.get(n) ?? domainsByNode.set(n, []).get(n)!).push(d);
    (nodesOf.get(d) ?? nodesOf.set(d, []).get(d)!).push(n);
  }
  const rank = (id: number) => {
    const n = nodes.get(id)!;
    return [ANCHOR_RANK[n.kind] ?? 9, -n.domainCount, id] as const;
  };
  const better = (a: number, b: number) => {
    const ra = rank(a), rb = rank(b);
    for (let i = 0; i < 3; i++) if (ra[i] !== rb[i]) return ra[i] < rb[i];
    return false;
  };

  const anchorOf = new Map<number, number | null>();
  const members = new Map<number | null, number[]>();
  const sortedDomains = [...g.domains].sort((a, b) => a[0] - b[0]);
  for (const [d] of sortedDomains) {
    let best: number | null = null;
    for (const n of nodesOf.get(d) ?? []) if (best === null || better(n, best)) best = n;
    // Only hosting-like infrastructure anchors a cluster; a domain whose best link is the CA would collapse everything.
    if (best !== null && ANCHOR_RANK[nodes.get(best)!.kind] > 2) best = null;
    anchorOf.set(d, best);
    (members.get(best) ?? members.set(best, []).get(best)!).push(d);
  }

  const order = [...members.keys()].sort((a, b) => {
    if (a === null) return 1;
    if (b === null) return -1;
    return members.get(b)!.length - members.get(a)!.length || a - b;
  });

  // Band of shared (non-anchor) infrastructure at the top.
  const shared = [...nodes.values()].filter((n) => !members.has(n.id)).sort((a, b) =>
    (ANCHOR_RANK[a.kind] - ANCHOR_RANK[b.kind]) || (b.domainCount - a.domainCount) || (a.id - b.id));
  // Target-eligible shared nodes on the first band rows, evidence-only below them; labels alternate between two
  // baselines (see labelDy), so each label has two slots of width.
  const perRow = 8;
  const bands = [shared.filter((n) => n.targetable), shared.filter((n) => !n.targetable)]
    .flatMap((group) => Array.from({ length: Math.ceil(group.length / perRow) }, (_, r) => group.slice(r * perRow, r * perRow + perRow)));
  const infra: InfraPos[] = [];
  bands.forEach((row, r) => {
    const slot = LAYOUT_WIDTH / row.length;
    row.forEach((n, i) => infra.push({ ...n, x: slot * i + slot / 2, y: 24 + r * BAND_ROW, anchor: false, labelDy: i % 2 ? 32 : 18, labelChars: labelChars(2 * slot) }));
  });
  const bandH = bands.length * BAND_ROW;

  // Shelf-pack the clusters below the band. A cluster is never narrower than its label.
  const radius = (n: number) => SPACING * Math.sqrt(n + 3) + 8;
  const clusters: Layout["clusters"] = [];
  const domains: DomainPos[] = [];
  const domainInfo = new Map(g.domains.map(([id, name, status]) => [id, { name, status }]));
  let x = 24, y = bandH + 48, rowH = 0;
  for (const a of order) {
    const ms = members.get(a)!;
    const r = radius(ms.length);
    const label = `${a === null ? "no hosting link" : shortLabel(nodes.get(a)!.value, 22)} (${ms.length})`;
    const w = Math.max(2 * r + 48, label.length * CHAR_W + 24);
    if (x + w > LAYOUT_WIDTH && x > 24) { x = 24; y += rowH + 40; rowH = 0; }
    const cx = x + w / 2, cy = y + r;
    clusters.push({ anchor: a, x: cx, y: cy, r, size: ms.length, label });
    if (a !== null) infra.push({ ...nodes.get(a)!, x: cx, y: cy, anchor: true });
    ms.forEach((d, j) => {
      const rr = SPACING * Math.sqrt(j + 3), t = j * GOLDEN;
      const info = domainInfo.get(d)!;
      domains.push({ id: d, name: info.name, status: info.status, x: cx + rr * Math.cos(t), y: cy + rr * Math.sin(t), anchor: a });
    });
    x += w;
    rowH = Math.max(rowH, 2 * r + 32);
  }

  // One aggregated link per (shared node, cluster) pair.
  const counts = new Map<string, Link>();
  const sharedIds = new Set(shared.map((n) => n.id));
  for (const [d, n] of g.edges) {
    if (!sharedIds.has(n)) continue;
    const a = anchorOf.get(d);
    if (a === undefined || a === null) continue;
    const k = `${n}:${a}`;
    const l = counts.get(k) ?? { from: n, to: a, count: 0 };
    l.count++;
    counts.set(k, l);
  }
  const links = [...counts.values()].sort((p, q) => p.from - q.from || p.to - q.to);
  return { width: LAYOUT_WIDTH, height: y + rowH + 24, infra, domains, links, clusters, domainsByNode };
}
