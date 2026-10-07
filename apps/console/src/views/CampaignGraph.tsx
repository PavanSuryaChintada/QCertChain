import { memo, useMemo } from "react";
import type { CampaignGraph as G, DomainStatus, NodeKind } from "../lib/api";
import { type Layout, layoutGraph, shortLabel } from "../lib/graphLayout";
import { truncateHash } from "../lib/format";

export const KIND_LABEL: Record<NodeKind, string> = {
  ip: "Hosting IP", nameserver: "Nameserver", registrar: "Registrar", asn: "ASN", cert_issuer: "Certificate issuer",
  kit_hash: "Kit hash", favicon_hash: "Favicon hash",
};

const DOMAIN_FILL: Record<DomainStatus, string> = {
  confirmed: "var(--confirmed)", candidate: "var(--candidate)", dismissed: "var(--benign)", unreachable: "var(--unknown)",
};


/** Domains layer: memoised on the covered set, so moving the slider redraws only what changed. */
const Domains = memo(function Domains({ layout, killed }: { layout: Layout; killed: ReadonlySet<number> }) {
  return (
    <g data-layer="domains">
      {layout.domains.map((d) => {
        const dark = killed.has(d.id);
        return <circle key={d.id} cx={d.x} cy={d.y} r={2.25} fill={dark ? "var(--hairline)" : DOMAIN_FILL[d.status]} data-dark={dark || undefined} />;
      })}
    </g>
  );
});

export function CampaignGraphSvg({ graph, selected, killed }: {
  graph: G;
  /** node_id -> rank, for the targets selected at the current k */
  selected: ReadonlyMap<number, number>;
  killed: ReadonlySet<number>;
}) {
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  const pos = useMemo(() => new Map(layout.infra.map((n) => [n.id, n])), [layout]);
  const dark = killed.size;
  return (
    <svg viewBox={`0 0 ${layout.width} ${layout.height}`} width="100%" style={{ display: "block", maxHeight: 640 }}
         role="img" aria-label={`Campaign graph: ${graph.domains.length} domains on ${graph.nodes.length} infrastructure nodes; ${selected.size} targets selected, ${dark} domains covered.`}>
      <g data-layer="links">
        {layout.links.map((l) => {
          const a = pos.get(l.from), b = pos.get(l.to);
          if (!a || !b) return null;
          // Every link is the same light hairline: the plan is told by the selected nodes and the dimmed domains.
          return <line key={`${l.from}-${l.to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--hairline)" strokeWidth={1} />;
        })}
      </g>
      <Domains layout={layout} killed={killed} />
      <g data-layer="infra">
        {layout.infra.map((n) => {
          const rank = selected.get(n.id);
          const sel = rank !== undefined;
          const stroke = sel ? "var(--action)" : "var(--ink-2)";
          const label = `${KIND_LABEL[n.kind]} ${n.value}: ${n.domainCount} domains${n.targetable ? ", target-eligible" : ", evidence only"}${sel ? `, selected target ${rank}` : ""}`;
          return (
            <g key={n.id} data-node={n.id} data-targetable={n.targetable} data-selected={sel || undefined}>
              <title>{label}</title>
              {n.targetable ? (
                <rect x={n.x - 5} y={n.y - 5} width={10} height={10} fill={sel ? "var(--action)" : "var(--ink-2)"} stroke={stroke} strokeWidth={1.25} />
              ) : (
                <circle cx={n.x} cy={n.y} r={5} fill="var(--paper)" stroke={stroke} strokeWidth={1.25} strokeDasharray="2 2" />
              )}
              {sel && <text x={n.x + 8} y={n.y - 6} className="svg-mono" style={{ fill: "var(--action)", fontWeight: 500 }}>{rank}</text>}
              {!n.anchor && (
                <text x={n.x} y={n.y + (n.labelDy ?? 18)} textAnchor="middle" className="svg-mono" data-label={n.id}
                      style={sel ? { fill: "var(--action)", fontWeight: 500 } : undefined}>
                  {n.kind === "kit_hash" || n.kind === "favicon_hash" ? truncateHash(n.value) : shortLabel(n.value, n.labelChars ?? 16)}
                </text>
              )}
            </g>
          );
        })}
      </g>
      <g data-layer="cluster-labels">
        {layout.clusters.map((c) => {
          const sel = c.anchor !== null && selected.has(c.anchor);
          return (
            <text key={String(c.anchor)} x={c.x} y={c.y + c.r + 16} textAnchor="middle" className="svg-mono"
                  style={sel ? { fill: "var(--action)", fontWeight: 500 } : undefined}>
              <title>{c.anchor === null ? "Domains with no hosting link" : pos.get(c.anchor)?.value}</title>
              {c.label}
            </text>
          );
        })}
      </g>
    </svg>
  );
}

export function GraphLegend() {
  const sw = (svg: React.ReactNode) => <svg width="16" height="16" aria-hidden="true" style={{ flex: "none" }}>{svg}</svg>;
  const li = (svg: React.ReactNode, text: string) => <li style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>{sw(svg)}{text}</li>;
  return (
    <ul className="t-meta" aria-label="Graph legend" style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 12 }}>
      {li(<rect x="3" y="3" width="10" height="10" fill="var(--ink-2)" />, "Target-eligible: hosting IP, nameserver, registrar (filled square)")}
      {li(<circle cx="8" cy="8" r="5" fill="var(--paper)" stroke="var(--ink-2)" strokeWidth="1.25" strokeDasharray="2 2" />, "Evidence only: ASN, issuer, kit, favicon (hollow dashed circle)")}
      {li(<rect x="3" y="3" width="10" height="10" fill="var(--action)" />, "Selected takedown target, with its rank")}
      {li(<circle cx="8" cy="8" r="3" fill="var(--confirmed)" />, "Confirmed domain")}
      {li(<circle cx="8" cy="8" r="3" fill="var(--candidate)" />, "Suspicious - not verified")}
      {li(<circle cx="8" cy="8" r="3" fill="var(--hairline)" />, "Covered: goes dark under this plan")}
    </ul>
  );
}
