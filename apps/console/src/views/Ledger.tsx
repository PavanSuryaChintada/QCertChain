import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, toApiError, type ByKit, type Campaign, type LedgerCampaign, type LedgerEvent, type LedgerStatus, type Page } from "../lib/api";
import { fmtDateTime, fmtInt, fmtNum, sentence } from "../lib/format";
import { POLL_MS, useLiveQuery } from "../lib/viewState";
import { useStatus } from "../lib/status";
import { Table, type Column } from "../components/Table";
import { HashDisplay } from "../components/HashDisplay";
import { Button } from "../components/Button";
import { ErrorState, SkeletonRows, ViewStateView, errorCopy } from "../components/States";
import { PageHeader, Section } from "../components/Page";
import { useToast } from "../components/Toast";

function orgName(status: LedgerStatus | undefined, address: string): string | null {
  if (!status) return null;
  const hit = Object.values(status.orgs).find((o) => o.address.toLowerCase() === address.toLowerCase());
  return hit?.name ?? null;
}

const num = (v: unknown) => (typeof v === "number" ? v : null);
const str = (v: unknown) => (typeof v === "string" ? v : null);

function eventColumns(status: LedgerStatus | undefined): Column<LedgerEvent>[] {
  return [
    { key: "tx", header: "Tx hash", width: 152, render: (e) => <HashDisplay value={e.tx_hash} label="transaction hash" /> },
    { key: "block", header: "Block", width: 88, align: "right", mono: true, render: (e) => fmtInt(e.block_number) },
    { key: "kind", header: "Event", width: 160, render: (e) => sentence(e.kind) },
    { key: "org", header: "Reporter org", render: (e) => orgName(status, e.org_address) ?? <HashDisplay value={e.org_address} label="org address" /> },
    { key: "at", header: "Timestamp", width: 176, mono: true, render: (e) => fmtDateTime(e.observed_at) },
    { key: "kit", header: "Kit hash", width: 152, render: (e) => <HashDisplay value={str(e.payload?.kit_hash)} label="kit hash" /> },
    { key: "domains", header: "Domains", width: 88, align: "right", mono: true, render: (e) => fmtInt(num(e.payload?.domain_count)) },
    { key: "conf", header: "Confidence", width: 104, align: "right", mono: true, render: (e) => fmtNum(num(e.payload?.confidence), 0) },
  ];
}

function KitResult({ c, demo }: { c: LedgerCampaign; demo: boolean }) {
  const toast = useToast();
  const done = (what: string) => ({
    onSuccess: () => toast(`${what} queued for the ledger. It appears in the record list once the transaction lands.`),
    onError: (e: unknown) => toast(errorCopy(toApiError(e), what.toLowerCase())),
  });
  const corroborate = useMutation({ mutationFn: () => api.corroborate(c.chain_campaign_id), ...done("Corroboration") });
  const dispute = useMutation({ mutationFn: () => api.attest(c.ioc_root, "disputed"), ...done("Dispute") });
  const ro = demo ? "The demo key is read-only." : undefined;
  return (
    <section className="panel panel-body" style={{ marginTop: 12 }} data-testid={`kit-${c.chain_campaign_id}`}>
      <p>
        Reported by <strong style={{ fontWeight: 600 }}>{c.reporter.name}</strong> (<HashDisplay value={c.reporter.address} label="reporter address" />)
        {c.yours ? <>; this is your organisation's report{c.campaign_id && <>: <Link className="link" to={`/campaigns/${encodeURIComponent(c.campaign_id)}`}>open the campaign</Link></>}.</>
          : <>; another organisation's report, so there is no local record to open.</>}
      </p>
      <table className="kv" style={{ marginTop: 8 }}>
        <tbody>
          <tr><th scope="row">Domains</th><td className="mono">{fmtInt(c.domain_count)}</td></tr>
          <tr><th scope="row">Confidence</th><td className="mono">{fmtNum(c.confidence, 0)}</td></tr>
          <tr><th scope="row">Published</th><td className="mono">{fmtDateTime(c.published_at)}</td></tr>
          <tr><th scope="row">Transaction</th><td><HashDisplay value={c.tx_hash} label="transaction hash" /></td></tr>
          <tr><th scope="row">IOC root</th><td><HashDisplay value={c.ioc_root} label="IOC root" /></td></tr>
          <tr><th scope="row">Corroborations</th><td>{c.corroborations.length === 0 ? "None yet" : c.corroborations.map((x) => x.name).join(", ")}</td></tr>
        </tbody>
      </table>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Button onClick={() => corroborate.mutate()} disabled={corroborate.isPending || corroborate.isSuccess || c.yours || demo}
                disabledReason={ro ?? (c.yours ? "You cannot corroborate your own report." : undefined)}>Corroborate</Button>
        <Button onClick={() => dispute.mutate()} disabled={dispute.isPending || dispute.isSuccess || demo} disabledReason={ro}>Dispute</Button>
      </div>
    </section>
  );
}

function campaignName(c: Campaign): string {
  return c.label ?? (c.brands.length ? `${c.brands.join(", ")} campaign` : `campaign ${c.id.slice(0, 8)}`);
}

function kitColumns(lookUp: (kit: string) => void): Column<Campaign>[] {
  return [
    { key: "name", header: "Campaign", render: (c) => campaignName(c) },
    { key: "domains", header: "Domains", width: 96, align: "right", mono: true, render: (c) => fmtInt(c.domain_count) },
    { key: "kit", header: "Kit hash", width: 176, render: (c) => <HashDisplay value={c.kit_hash!} label="kit hash" /> },
    { key: "go", header: "", width: 112, render: (c) => (
      <Button size="sm" iconLabel={`Look up the kit hash of ${campaignName(c)}`} onClick={() => lookUp(c.kit_hash!)}>Look up</Button>
    ) },
  ];
}

export function LedgerPage() {
  const [params] = useSearchParams();
  const fromUrl = params.get("kit")?.trim() || null; // the tour (or any link) can open a lookup directly
  const [kit, setKit] = useState(fromUrl ?? "");
  const [lookup, setLookup] = useState<string | null>(fromUrl);
  // a new ?kit= while the page stays open (the tour moving between steps, a pasted link) runs that lookup
  useEffect(() => { if (fromUrl) { setKit(fromUrl); setLookup(fromUrl); } }, [fromUrl]);
  const { data: sys } = useStatus();
  const demo = sys?.key_kind === "demo";
  const status = useQuery({ queryKey: ["ledger-status"], queryFn: () => api.ledgerStatus(), staleTime: 60_000 });
  const events = useLiveQuery<Page<LedgerEvent>>({ queryKey: ["ledger-events"], queryFn: (s) => api.ledgerEvents(null, s), poll: POLL_MS });
  const mine = useLiveQuery<Page<Campaign>>({ queryKey: ["campaigns"], queryFn: (s) => api.campaigns({ limit: 200 }, s), poll: POLL_MS });
  const kits = (mine.query.data?.items ?? []).filter((c) => c.kit_hash);
  const lookUp = (k: string) => { setKit(k); setLookup(k); };
  const found = useLiveQuery<ByKit>({ queryKey: ["by-kit", lookup], queryFn: (s) => api.byKit(lookup!, s), enabled: lookup !== null, isEmpty: (d) => d.campaigns.length === 0, retry: 0 });
  const me = status.data ? status.data.orgs[status.data.you] : undefined;
  const cols = eventColumns(status.data);
  return (
    <div>
      <PageHeader title="Ledger" meta={<>Signed in as {me?.name ?? status.data?.you ?? "your organisation"}{me && <> (<HashDisplay value={me.address} label="your address" />)</>}. The ledger holds hashes, counts, the reporter and a timestamp; never domain names, addresses or page content.</>} />
      {status.data && !status.data.available && (
        <p className="stale-bar">The chain is not reachable{status.data.reason ? `: ${status.data.reason}` : ""}. Queued writes: {fmtInt(status.data.queue_depth)}.</p>
      )}
      <Section id="sec-kit" tour="kit-lookup" title="Kit-hash lookup">
        <p className="prose ink-2">The consortium moment: search a kit hash seen on one of your own domains and find whether another organisation already reported it. You receive their hashes and counts only. No raw telemetry is shared.</p>
        <form style={{ display: "flex", gap: 8, marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); if (kit.trim()) setLookup(kit.trim()); }}>
          <label htmlFor="kit" className="sr-only">Kit hash</label>
          <input id="kit" className="input mono" style={{ flex: 1 }} placeholder="Kit hash (64 hex characters)" value={kit} onChange={(e) => setKit(e.target.value)} />
          <Button type="submit" variant="primary" disabled={!kit.trim()}>Look up</Button>
        </form>
        {kits.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <p className="t-label">Kit hashes of your campaigns: pick one to see whether another organisation reported the same kit.</p>
            <Table<Campaign> label="Kit hashes of your campaigns" density="compact" rows={kits} rowKey={(c) => c.id}
                             columns={kitColumns(lookUp)} />
          </div>
        )}
        {lookup !== null && (
          <div style={{ marginTop: 12 }}>
            <ViewStateView state={found.state} what="the kit-hash lookup" empty="No organisation has published a campaign for this kit hash yet."
                           skeleton={<div style={{ height: 96, background: "var(--sunken)" }} aria-busy="true" />}>
              {(d) => (
                <>
                  <p className="t-section" data-testid="hashes-only">Hashes and counts only. No raw telemetry received.</p>
                  {d.campaigns.map((c) => <KitResult key={c.chain_campaign_id} c={c} demo={demo} />)}
                </>
              )}
            </ViewStateView>
          </div>
        )}
      </Section>
      <h2 className="t-section" style={{ marginBottom: 8 }}>Anchored records</h2>
      <ViewStateView state={events.state} what="the ledger records" onRetry={() => events.query.refetch()}
                     empty="Nothing anchored yet. Records appear once a campaign is published or a bundle is anchored."
                     skeleton={<SkeletonRows columns={cols.map((c) => c.width)} rows={10} />}>
        {(p) => <Table<LedgerEvent> label="Anchored records" columns={cols} rows={p.items} rowKey={(e) => e.id} />}
      </ViewStateView>
      {status.isError && <div style={{ marginTop: 8 }}><ErrorState error={toApiError(status.error)} what="the ledger status" /></div>}
    </div>
  );
}
