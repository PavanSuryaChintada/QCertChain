import type { Core, StylesheetStyle } from "cytoscape";

// Cytoscape cannot read CSS variables, so these mirror tokens.css exactly (a test checks every hex is a token).
export const T = {
  ink000: "#efeae0", ink100: "#c6c0b5", ink200: "#97928a", ink300: "#67645e",
  ground000: "#0e1417", ground300: "#263840", ground400: "#35525c",
  candidate: "#67645e", confirmed: "#c0392b", dismissed: "#4a5d52", unreach: "#9a760c",
};

export function statusColor(status: string | undefined): string {
  switch (status) {
    case "confirmed": return T.confirmed;
    case "dismissed": return T.dismissed;
    case "unreachable": return T.unreach;
    default: return T.candidate; // a candidate is grey — never coloured
  }
}

const KIND_SHORT: Record<string, string> = {
  ip: "IP", nameserver: "NS", registrar: "REG", asn: "ASN", cert_issuer: "CA", kit_hash: "KIT", favicon_hash: "ICON",
};

export function buildStyle(): StylesheetStyle[] {
  return [
    { selector: "node", style: { shape: "rectangle", "border-width": 0, label: "", "font-family": "IBM Plex Mono",
                                 "font-size": 9, color: T.ink200, "text-valign": "bottom", "text-margin-y": 3 } },
    { selector: 'node[kind = "domain"]', style: { width: 6, height: 6, "background-color": T.candidate } },
    { selector: 'node[kind = "domain"][status = "confirmed"]', style: { "background-color": T.confirmed } },
    { selector: 'node[kind = "domain"][status = "dismissed"]', style: { "background-color": T.dismissed } },
    { selector: 'node[kind = "domain"][status = "unreachable"]', style: { "background-color": T.unreach } },
    { selector: 'node[kind != "domain"]', style: { width: 12, height: 12, "background-color": T.ink200,
                                                   label: "data(short)" } },
    { selector: "node[?is_target]", style: { "border-width": 2, "border-color": T.ink000, "border-style": "solid",
                                              color: T.ink000, label: "data(rankLabel)" } },
    { selector: "edge", style: { width: 1, "line-color": T.ground400, opacity: "data(opacity)" as never,
                                 "curve-style": "straight" } },
    { selector: ".dim", style: { opacity: 0.12 } },
    { selector: "node.hit", style: { "border-width": 1, "border-color": T.ink000 } },
  ];
}

export function decorate(nodeData: { kind: string; label: string; target_rank?: number }) {
  const short = `${KIND_SHORT[nodeData.kind] ?? nodeData.kind} ${nodeData.label.length > 18 ? nodeData.label.slice(0, 16) + "…" : nodeData.label}`;
  return { short, rankLabel: nodeData.target_rank ? `${nodeData.target_rank} · ${short}` : short };
}

export const CY_OPTIONS = {
  autoungrabify: true,          // no dragging: an analyst pulling the layout apart mid-demo is a bad minute
  boxSelectionEnabled: false,
  wheelSensitivity: 0.3,
  minZoom: 0.2,
  maxZoom: 4,
} as const;

type NodeIn = { data: { id: string; kind: string } };
type EdgeIn = { data: { source: string; target: string } };
type Pos = Record<string, { x: number; y: number }>;

const ANCHOR_RANK: Record<string, number> = { ip: 0, nameserver: 1, registrar: 2, asn: 3, kit_hash: 4, favicon_hash: 5, cert_issuer: 6 };
const SPACING = 9;        // px between domain squares
const GOLDEN = 2.399963;  // golden angle: an even sunflower with no overlaps

/** Deterministic radial layout, O(n). Force layouts (cose-bilkent, cose) took 17-22 s on a real 400-domain
 *  campaign and froze the tab. Hosting IPs sit on an outer ring, each with its domains in a sunflower around
 *  it; the shared infrastructure (nameservers, registrars, ASNs, kit, CA) sits on an inner ring. */
export function computePositions(nodes: NodeIn[], edges: EdgeIn[]): Pos {
  const kind = new Map(nodes.map((n) => [n.data.id, n.data.kind]));
  const anchorOf = new Map<string, string>();
  for (const { data: e } of edges) {
    const [d, t] = kind.get(e.source) === "domain" ? [e.source, e.target] : [e.target, e.source];
    const cur = anchorOf.get(d);
    if (!cur || (ANCHOR_RANK[kind.get(t) ?? ""] ?? 9) < (ANCHOR_RANK[kind.get(cur) ?? ""] ?? 9)) anchorOf.set(d, t);
  }
  const members = new Map<string, string[]>();
  const loose: string[] = [];
  for (const n of nodes) {
    if (n.data.kind !== "domain") continue;
    const a = anchorOf.get(n.data.id);
    if (a) members.set(a, [...(members.get(a) ?? []), n.data.id]);
    else loose.push(n.data.id);
  }
  const anchors = [...members.keys()].sort((a, b) => members.get(b)!.length - members.get(a)!.length || a.localeCompare(b));
  const inner = nodes.filter((n) => n.data.kind !== "domain" && !members.has(n.data.id)).map((n) => n.data.id).sort();
  const radius = (n: number) => SPACING * Math.sqrt(n + 1) + 14;
  const arcs = anchors.map((a) => 2 * radius(members.get(a)!.length) + 18);
  const total = arcs.reduce((s, x) => s + x, 0);
  const radii = anchors.map((a) => radius(members.get(a)!.length));
  // Angles are fixed by arc share; grow the ring until adjacent anchors are at least twice the larger cluster
  // radius apart (chord, not arc): then no domain can sit closer to a neighbouring IP than to its own.
  const centres = () => {
    let a = 0;
    return arcs.map((arc) => { const t = ((a + arc / 2) / total) * 2 * Math.PI - Math.PI / 2; a += arc; return t; });
  };
  const thetas = centres();
  let R = Math.max(total / (2 * Math.PI), 160);
  for (let k = 0; k < 60 && anchors.length > 1; k++) {
    let ok = true;
    for (let i = 0; i < anchors.length; i++) {
      for (let j = i + 1; j < anchors.length; j++) {
        const chord = 2 * R * Math.abs(Math.sin((thetas[i] - thetas[j]) / 2));
        if (chord < 2 * Math.max(radii[i], radii[j]) + 8) ok = false;
      }
    }
    if (ok) break;
    R *= 1.12;
  }
  const pos: Pos = {};
  anchors.forEach((a, i) => {
    const theta = thetas[i];
    const cx = R * Math.cos(theta), cy = R * Math.sin(theta);
    pos[a] = { x: cx, y: cy };
    members.get(a)!.sort().forEach((d, j) => {
      const r = SPACING * Math.sqrt(j + 1.5), t = j * GOLDEN;
      pos[d] = { x: cx + r * Math.cos(t), y: cy + r * Math.sin(t) };
    });
  });
  const r0 = anchors.length ? R * 0.42 : 0;
  inner.forEach((id, i) => {
    const t = (i / Math.max(inner.length, 1)) * 2 * Math.PI;
    pos[id] = { x: r0 * Math.cos(t), y: r0 * Math.sin(t) };
  });
  loose.sort().forEach((d, j) => {
    const r = SPACING * Math.sqrt(j + 1.5), t = j * GOLDEN;
    pos[d] = { x: r * Math.cos(t), y: R + 60 + r * Math.sin(t) };
  });
  return pos;
}

/** One 400 ms settle from precomputed positions, then stop. No continuous physics (DESIGN.md §7). */
export function runLayout(cy: Pick<Core, "layout">, positions: Pos) {
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const layout = cy.layout({ name: "preset", positions, animate: !reduced, animationDuration: 400, fit: true,
                             padding: 24 } as never);
  layout.run();
  setTimeout(() => layout.stop(), 420);
  return layout;
}
