import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { Hash, Num } from "../components/Mono";
import { CampaignGraph } from "./CampaignGraph";
import { PlanPanel } from "./PlanPanel";

export function CampaignView({ id }: { id: string }) {
  const qc = useQueryClient();
  const c = useQuery({ queryKey: ["campaign", id], queryFn: () => api.campaign(id), refetchInterval: 5000 });
  const g = useQuery({ queryKey: ["graph", id], queryFn: () => api.graph(id) });
  const [hoverNode, setHoverNode] = useState<number | null>(null);
  const publish = useMutation({ mutationFn: () => api.publish(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["metrics"] }) });

  // domains a hovered takedown target removes = the domains with an edge to it
  const highlight = useMemo(() => {
    if (hoverNode == null || !g.data) return null;
    const target = `n:${hoverNode}`;
    return new Set(g.data.elements.edges.filter((e) => e.data.target === target).map((e) => e.data.source));
  }, [hoverNode, g.data]);

  if (c.isError) return <p className="p-6">This campaign could not be loaded: {(c.error as Error).message}</p>;
  return (
    <div className="grid h-full" style={{ gridTemplateRows: "auto minmax(360px, 1fr) auto" }}>
      {c.data && (
        <header className="p-4 rule-b flex items-start justify-between gap-4">
          <div>
            <span className="mono" style={{ fontSize: 22, color: "var(--ink-000)" }}>{c.data.label}</span>
            <p className="secondary">
              <Num v={c.data.domain_count} /> domains on <Num v={c.data.infra_count} /> infrastructure nodes ·
              brands {c.data.brands.join(", ") || "—"} · kit <Hash v={c.data.kit_hash} /> · confidence{" "}
              <Num v={c.data.confidence} digits={2} />
            </p>
          </div>
          <div className="text-right">
            {c.data.published_tx ? (
              <p className="secondary">On the ledger: <Hash v={c.data.published_tx} /></p>
            ) : (
              <button onClick={() => publish.mutate()} disabled={publish.isPending || publish.isSuccess || !c.data.kit_hash}>
                {publish.isSuccess ? "Queued for the ledger" : "Publish to ledger"}
              </button>
            )}
            <p className="secondary mt-1">Publishes hashes only: the IOC root and kit fingerprint.</p>
          </div>
        </header>
      )}
      <div className="min-h-0 rule-b">{g.data ? <CampaignGraph graph={g.data} highlight={highlight} /> : <div className="solving" />}</div>
      <PlanPanel campaignId={id} onPlan={() => qc.invalidateQueries({ queryKey: ["graph", id] })} onHover={setHoverNode} />
    </div>
  );
}
