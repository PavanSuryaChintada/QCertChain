import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type ByKit } from "../lib/api";
import { Hash, Num } from "../components/Mono";

// The shared ledger, seen as whichever organisation is signed in. The chain is public to every member (hashes,
// counts, reporter, timestamp); another organisation's rows are not reachable through the API at all.
export function SharedLedger() {
  const [kit, setKit] = useState("");
  const status = useQuery({ queryKey: ["ledger-status"], queryFn: api.ledgerStatus, refetchInterval: 5000 });
  const look = useMutation<ByKit, Error, string>({ mutationFn: (k) => api.byKit(k.trim()) });
  const corroborate = useMutation({ mutationFn: (chainId: string) => api.corroborate(chainId) });
  const dispute = useMutation({ mutationFn: (root: string) => api.attest(root, "disputed") });
  const err = look.error instanceof ApiError ? look.error.problem : null;
  const me = status.data ? status.data.orgs[status.data.you] : undefined;
  return (
    <div className="p-6 max-w-[960px]">
      <p className="panel-title" style={{ fontSize: 22 }}>Shared ledger</p>
      <p className="secondary">
        Signed in as {me?.name ?? status.data?.you ?? "your organisation"}{me && <> (<Hash v={me.address} n={10} />)</>}.
        The ledger holds hashes, counts, the reporter and a timestamp — never domain names, addresses or page content.
        Another organisation's campaigns appear here as commitments only.
        {status.data && !status.data.available && " The ledger is not reachable right now."}
      </p>
      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (kit.trim()) look.mutate(kit); }}>
        <label htmlFor="kit" className="sr-only">Kit fingerprint</label>
        <input id="kit" className="flex-1 mono" placeholder="Kit fingerprint seen on one of our own domains (64 hex characters)"
               value={kit} onChange={(e) => setKit(e.target.value)} />
        <button type="submit" disabled={look.isPending || !kit.trim()}>Look up on the ledger</button>
      </form>
      {err && <p className="mt-3">{err.status === 503 ? err.detail : `Lookup failed: ${err.detail}`}</p>}
      {look.data && look.data.campaigns.length === 0 && (
        <p className="mt-4 secondary">No organisation has published a campaign for this kit yet.</p>
      )}
      {look.data && look.data.campaigns.length > 0 && (
        <>
          <p className="mt-6" style={{ color: "var(--ink-000)" }}>Inherited from ledger. No raw telemetry received.</p>
          {look.data.campaigns.map((c) => (
            <section key={c.chain_campaign_id} className="mt-3 rule-t pt-3">
              <p><Num v={c.domain_count} /> domains · confidence <Num v={c.confidence} />% · reported by{" "}
                <span style={{ color: "var(--ink-000)" }}>{c.reporter.name}</span> (<Hash v={c.reporter.address} n={10} />)</p>
              <p className="secondary">published {c.published_at.slice(0, 19)}Z · transaction <Hash v={c.tx_hash} /> ·
                IOC root <Hash v={c.ioc_root} /></p>
              <p className="secondary">
                {c.corroborations.length === 0 ? "No corroborations yet."
                  : `Corroborated by ${c.corroborations.map((x) => x.name).join(", ")}.`}
              </p>
              <div className="mt-2 flex gap-2">
                <button onClick={() => corroborate.mutate(c.chain_campaign_id)}
                        disabled={corroborate.isPending || c.yours}
                        title={c.yours ? "Your own campaign" : undefined}>Corroborate</button>
                <button onClick={() => dispute.mutate(c.ioc_root)} disabled={dispute.isPending}>Dispute</button>
              </div>
              {(corroborate.isSuccess || dispute.isSuccess) && (
                <p className="secondary mt-1">Queued for the ledger. It appears here once the transaction lands.</p>
              )}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
