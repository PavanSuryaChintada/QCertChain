import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, toApiError, type DomainDetail as D, type Signal } from "../lib/api";
import { fmtDateTime, sentence } from "../lib/format";
import { domainSeverity } from "../lib/status";
import { useLiveQuery } from "../lib/viewState";
import { Drawer } from "../components/Drawer";
import { StatusIndicator } from "../components/StatusIndicator";
import { HashDisplay } from "../components/HashDisplay";
import { ReasonsTable } from "../components/ScoreBreakdown";
import { Button } from "../components/Button";
import { ViewStateView, errorCopy } from "../components/States";
import { useToast } from "../components/Toast";

export function SignalGroups({ signals }: { signals: Signal[] }) {
  const groups = (["strong", "moderate", "weak"] as const).map((g) => ({ g, items: signals.filter((s) => s.strength === g) }));
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {groups.map(({ g, items }) => (
        <div key={g}>
          <p className="t-label">{sentence(g)} ({items.length})</p>
          {items.length === 0 ? <p className="t-meta">None found.</p> : (
            <ul>
              {items.map((s, i) => (
                <li key={i} style={{ padding: "4px 0", borderBottom: "1px solid var(--hairline)" }}>
                  <span>{sentence(s.name)}</span>
                  <span className="mono t-meta" style={{ display: "block", overflowWrap: "anywhere" }}>{s.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

/** The gate stated explicitly: "2 strong required - N found". */
export function Gate({ strong }: { strong: number }) {
  return (
    <p className="t-data" data-testid="gate">
      2 strong required - {strong} found{strong >= 2 ? " (gate passed)" : " (gate not passed)"}
    </p>
  );
}

function Screenshot({ path, alt }: { path: string; alt: string }) {
  const q = useQuery({ queryKey: ["artifact", path], queryFn: () => api.artifactBlobUrl(path), staleTime: Infinity, retry: false });
  if (q.isError) return <p className="t-meta">The screenshot could not be loaded ({errorCopy(toApiError(q.error), "the screenshot")}).</p>;
  if (!q.data) return <div style={{ height: 192, background: "var(--sunken)" }} aria-label="Loading screenshot" />;
  return <img src={q.data} alt={alt} style={{ width: "100%", border: "1px solid var(--hairline)" }} />;
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return <tr><th scope="row">{k}</th><td>{children}</td></tr>;
}

export function DomainBody({ d }: { d: D }) {
  const toast = useToast();
  const sev = domainSeverity(d.status);
  const c = d.confirmation;
  const e = d.enrichment;
  const reconfirm = useMutation({
    mutationFn: () => api.reconfirm(d.id),
    onSuccess: () => toast("Re-check queued. The verdict updates when the page has been fetched again."),
    onError: (err) => toast(errorCopy(toApiError(err), "the re-check")),
  });
  return (
    <div style={{ display: "grid", gap: 24 }}>
      <div>
        <p className="t-data" style={{ overflowWrap: "anywhere", fontSize: 15, lineHeight: "20px" }}>{d.name}</p>
        <p className="t-meta" style={{ marginTop: 4 }}>
          Registrable domain <span className="mono">{d.etld1}</span>; source <span className="mono">{d.source}</span>; first seen <span className="mono">{fmtDateTime(d.first_seen)}</span>
        </p>
        <div style={{ marginTop: 8 }}><StatusIndicator severity={sev.severity} label={sev.label} /></div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <Button size="sm" onClick={() => reconfirm.mutate()} disabled={reconfirm.isPending}>Re-check the page</Button>
          {d.campaign_id && <Link className="btn btn-sm" to={`/campaigns/${encodeURIComponent(d.campaign_id)}`}>Open campaign</Link>}
          {d.evidence_bundle_id && <Link className="btn btn-sm" to={`/evidence/${encodeURIComponent(d.evidence_bundle_id)}`}>Open evidence</Link>}
        </div>
      </div>
      <section>
        <h3 className="t-section">Triage reasons</h3>
        <p className="t-meta" style={{ marginBottom: 8 }}>{d.triage.provenance === "rules" ? "Hand-set rule weights" : "Trained model"}. Triage only nominates; it never confirms.</p>
        <ReasonsTable reasons={d.triage} />
      </section>
      <section>
        <h3 className="t-section">Confirmation signals</h3>
        {c ? (
          <>
            <Gate strong={c.strong_count} />
            <div style={{ marginTop: 8 }}><SignalGroups signals={c.signals} /></div>
          </>
        ) : <p className="t-meta">Not checked yet. The page is fetched and checked once the domain reaches the confirmation queue.</p>}
      </section>
      {c?.screenshot_url && (
        <figure>
          <Screenshot path={c.screenshot_url} alt={`Screenshot of ${d.name} as fetched`} />
          <figcaption className="t-meta" style={{ marginTop: 4 }}>Captured page. Fetched and observed only; no form was touched.</figcaption>
        </figure>
      )}
      <section>
        <h3 className="t-section">Enrichment</h3>
        {e ? (
          <>
            {e.partial && <p className="t-meta">Partial: {Object.entries(e.errors ?? {}).map(([k, v]) => `${k} (${v})`).join("; ")}</p>}
            <table className="kv" style={{ marginTop: 8 }}>
              <tbody>
                <Row k="IP addresses"><span className="mono">{e.ip_addresses.join(", ") || "–"}</span></Row>
                <Row k="ASN"><span className="mono">{e.asn ? `AS${e.asn}` : "–"}</span>{e.asn_name && ` ${e.asn_name}`}</Row>
                <Row k="Country"><span className="mono">{e.country ?? "–"}</span></Row>
                <Row k="Nameservers"><span className="mono">{e.nameservers.join(", ") || "–"}</span></Row>
                <Row k="Registrar">{e.registrar ?? "–"}</Row>
                <Row k="Registered"><span className="mono">{fmtDateTime(e.registered_at)}</span></Row>
                <Row k="Certificate issuer">{e.cert_issuer ?? "–"}</Row>
                <Row k="Kit hash"><HashDisplay value={e.dom_hash} label="kit hash" /></Row>
                <Row k="Favicon hash"><HashDisplay value={e.favicon_hash} label="favicon hash" /></Row>
              </tbody>
            </table>
          </>
        ) : <p className="t-meta">Not enriched yet.</p>}
      </section>
    </div>
  );
}

/** Opened from any page with ?domain=<id>. */
export function DomainDrawer() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("domain");
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : null;
  const close = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("domain");
    setParams(next);
  }, [params, setParams]);
  const q = useLiveQuery<D>({ queryKey: ["domain", id], queryFn: (s) => api.domain(id!, s), enabled: id !== null, isEmpty: () => false, staleTime: 10000 });
  return (
    <Drawer open={id !== null} onClose={close} title={q.data && q.data.id === id ? q.data.name : "Domain"}>
      <ViewStateView state={q.state} what="this domain" skeleton={<div style={{ height: 192, background: "var(--sunken)" }} aria-busy="true" />}
                     empty={null} onRetry={() => q.query.refetch()}>
        {(d) => <DomainBody d={d} />}
      </ViewStateView>
    </Drawer>
  );
}
