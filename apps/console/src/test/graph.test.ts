import { layoutGraph } from "../lib/graphLayout";
import type { CampaignGraph, NodeKind } from "../lib/api";
import RAW from "../fixtures/campaign_graph_400.json";

// The real 400-domain seeded campaign, converted from the old element format to the compact graph contract.
type El = { data: { id: string; kind: string; label: string; domain_count?: number; status?: string; source?: string; target?: string; weight?: number } };
function convert(raw: { campaign_id: string; elements: { nodes: El[]; edges: El[] } }): CampaignGraph {
  const num = (id: string) => Number(id.split(":")[1]);
  const doms = raw.elements.nodes.filter((n) => n.data.kind === "domain");
  const infra = raw.elements.nodes.filter((n) => n.data.kind !== "domain");
  const targetable = new Set(["ip", "nameserver", "registrar"]);
  return {
    campaign_id: raw.campaign_id, n_targetable: infra.filter((n) => targetable.has(n.data.kind)).length, search_space_log2: 0, built_at: "",
    domains: doms.map((d) => [num(d.data.id), d.data.label, (d.data.status ?? "confirmed") as "confirmed"]),
    nodes: infra.map((n) => [num(n.data.id), n.data.kind as NodeKind, n.data.label, n.data.domain_count ?? 0, targetable.has(n.data.kind)]),
    edges: raw.elements.edges.map((e) => [num(e.data.source!), num(e.data.target!), e.data.weight ?? 1]),
    targets: [],
  };
}
const G = convert(RAW as never);

it("lays out the real 400-domain campaign fast and deterministically", () => {
  const t = performance.now();
  const a = layoutGraph(G);
  expect(performance.now() - t).toBeLessThan(200);
  expect(a.domains).toHaveLength(G.domains.length);
  expect(layoutGraph(G)).toEqual(a);
  a.domains.forEach((d) => expect(Number.isFinite(d.x) && Number.isFinite(d.y)).toBe(true));
});

it("every domain sits inside its own cluster, and no two domains overlap", () => {
  const a = layoutGraph(G);
  const cl = new Map(a.clusters.map((c) => [c.anchor, c]));
  for (const d of a.domains) {
    const c = cl.get(d.anchor)!;
    expect(Math.hypot(d.x - c.x, d.y - c.y)).toBeLessThanOrEqual(c.r);
  }
  const keys = new Set(a.domains.map((d) => `${d.x.toFixed(1)},${d.y.toFixed(1)}`));
  expect(keys.size).toBe(a.domains.length);
  expect(a.infra.every((n) => n.x >= 0 && n.x <= a.width && n.y >= 0 && n.y <= a.height)).toBe(true);
});
