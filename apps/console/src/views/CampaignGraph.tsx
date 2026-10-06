import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { Graph } from "../lib/api";
import { CY_OPTIONS, buildStyle, computePositions, decorate, runLayout } from "../lib/cyto";
import { Num } from "../components/Mono";

export function GraphNotice({ truncated, nodeCount }: { truncated: boolean; nodeCount: number }) {
  return (
    <p className="secondary">
      <Num v={nodeCount} /> nodes
      {truncated && " — over 1,000, so domains are collapsed into per-infrastructure counts."}
    </p>
  );
}

/** Domains (6px squares, verdict colour) on their infrastructure (12px squares). Takedown targets are ringed.
 *  `highlight` (domain ids) dims everything else — used when hovering a takedown target. */
export function CampaignGraph({ graph, highlight }: { graph: Graph; highlight?: Set<string> | null }) {
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const nodes = graph.elements.nodes.map((n) => ({ data: { ...n.data, ...(n.data.kind !== "domain" ? decorate(n.data) : {}) } }));
    const edges = graph.elements.edges.map((e) => ({ data: { ...e.data, opacity: Math.max(0.15, e.data.weight * 0.6) } }));
    const cy = cytoscape({ container: host.current, elements: { nodes, edges }, style: buildStyle(), ...CY_OPTIONS });
    cyRef.current = cy;
    runLayout(cy, computePositions(nodes, edges));
    return () => cy.destroy();
  }, [graph]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("dim hit");
    if (highlight && highlight.size) {
      cy.nodes('[kind = "domain"]').forEach((n) => {
        if (!highlight.has(n.id())) n.addClass("dim");
        else n.addClass("hit");
      });
      cy.edges().forEach((e) => { if (!highlight.has(e.source().id())) e.addClass("dim"); });
    }
  }, [highlight]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 rule-b flex items-center justify-between">
        <GraphNotice truncated={graph.truncated} nodeCount={graph.node_count} />
        <span className="secondary">Squares: domains (colour = verdict) and their infrastructure. Ringed: takedown targets.</span>
      </div>
      <div ref={host} className="flex-1" style={{ minHeight: 360 }} aria-label="Campaign graph" role="img" />
    </div>
  );
}
