import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Hash, Num } from "../components/Mono";
import { CampaignGraph } from "./CampaignGraph";

export function CampaignView({ id }: { id: string }) {
  const c = useQuery({ queryKey: ["campaign", id], queryFn: () => api.campaign(id) });
  const g = useQuery({ queryKey: ["graph", id], queryFn: () => api.graph(id) });
  if (c.isError) return <p className="p-6">This campaign could not be loaded: {(c.error as Error).message}</p>;
  return (
    <div className="flex flex-col h-full">
      {c.data && (
        <header className="p-4 rule-b">
          <span className="mono" style={{ fontSize: 22, color: "var(--ink-000)" }}>{c.data.label}</span>
          <p className="secondary">
            <Num v={c.data.domain_count} /> domains on <Num v={c.data.infra_count} /> infrastructure nodes ·
            brands {c.data.brands.join(", ") || "—"} · kit <Hash v={c.data.kit_hash} /> · confidence{" "}
            <Num v={c.data.confidence} digits={2} />
          </p>
        </header>
      )}
      <div className="flex-1 min-h-0">{g.data ? <CampaignGraph graph={g.data} /> : <div className="solving" />}</div>
    </div>
  );
}
