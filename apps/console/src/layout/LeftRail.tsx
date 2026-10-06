import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { VerdictChip } from "../components/VerdictChip";
import { DomainName, Num } from "../components/Mono";

// Campaign severity is the only other colour in the product, and only here and on the graph (DESIGN §3).
export function severity(n: number) {
  return n >= 500 ? "var(--sev-4)" : n >= 100 ? "var(--sev-3)" : n >= 10 ? "var(--sev-2)" : "var(--sev-1)";
}

export function LeftRail() {
  const [params, setParams] = useSearchParams();
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: api.campaigns, refetchInterval: 5000 });
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: () => api.candidates("?limit=60"), refetchInterval: 4000 });
  const selC = params.get("campaign");
  const selD = params.get("domain");
  return (
    <nav className="left rule-r" aria-label="Campaigns and candidates" style={{ background: "var(--ground-100)" }}>
      <div className="rule-b px-3 py-2 eyebrow">Campaigns</div>
      <ul>
        {campaigns.data?.items.length === 0 && (
          <li className="secondary px-3 py-2">No campaigns yet. A campaign forms once two confirmed domains share infrastructure.</li>
        )}
        {campaigns.data?.items.map((c) => (
          <li key={c.id}>
            <button className="row w-full text-left" aria-selected={selC === c.id}
                    style={{ border: 0, background: "transparent", padding: "6px 12px", height: "auto" }}
                    onClick={() => setParams({ campaign: c.id })}>
              <span className="flex items-center gap-2">
                <span aria-hidden style={{ width: 10, height: 10, background: severity(c.domain_count), display: "inline-block" }} />
                <span className="mono text-13 text-ink-0">{c.label}</span>
              </span>
              <span className="secondary pl-5 block"><Num v={c.domain_count} /> domains</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="rule-b rule-t px-3 py-2 eyebrow mt-2">Candidates</div>
      <ul>
        {candidates.data?.items.length === 0 && (
          <li className="secondary px-3 py-2">No candidates yet. They appear as the certificate stream is triaged.</li>
        )}
        {candidates.data?.items.map((d) => (
          <li key={d.id}>
            <button className="row w-full text-left" aria-selected={selD === String(d.id)}
                    style={{ border: 0, background: "transparent", padding: "6px 12px", height: "auto" }}
                    onClick={() => setParams({ domain: String(d.id) })}>
              <DomainName name={d.name} />
              <span className="flex items-center justify-between">
                <VerdictChip status={d.status} />
                <span className="secondary">{d.source}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
