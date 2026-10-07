import type { ComponentKey } from "../lib/api";
import { fmtDateTime, fmtInt, fmtNum, sentence } from "../lib/format";
import { componentStatus, useStatus } from "../lib/status";
import { SystemIndicator } from "../components/StatusIndicator";
import { ViewStateView } from "../components/States";
import { Fact, PageHeader, Section } from "../components/Page";

const COMPONENTS: { key: ComponentKey; label: string }[] = [
  { key: "ct", label: "CT firehose" }, { key: "triage", label: "Triage" }, { key: "confirm", label: "Confirm" },
  { key: "enrich", label: "Enrich" }, { key: "graph", label: "Campaign graph" }, { key: "interdiction", label: "Interdiction" },
  { key: "evidence", label: "Evidence" }, { key: "ledger", label: "Ledger" }, { key: "email", label: "Email" },
];

/** Everything here comes from the shared /status poll: this page adds no request of its own. */
export function HealthPage() {
  const { state, query } = useStatus();
  return (
    <div>
      <PageHeader title="System health" meta="From the batched status poll, every 5s. Failed is grey: a failing system is not a threat." />
      <ViewStateView state={state} what="the system status" empty={null} onRetry={() => query.refetch()}
                     skeleton={<div className="panel" style={{ height: 320, background: "var(--sunken)" }} aria-busy="true" />}>
        {(s) => {
          const h = s.health;
          const endpoints = Object.entries(h.endpoints).sort((a, b) => (b[1].p95_ms ?? 0) - (a[1].p95_ms ?? 0));
          return (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 24 }}>
                <Section id="sec-components" title="Components">
                  <table className="tbl" aria-label="Component status">
                    <colgroup><col style={{ width: 160 }} /><col style={{ width: 144 }} /><col /></colgroup>
                    <thead><tr><th>Component</th><th>Status</th><th>Detail</th></tr></thead>
                    <tbody>
                      {COMPONENTS.map((c) => (
                        <tr key={c.key}>
                          <td>{c.label}</td>
                          <td><SystemIndicator status={componentStatus(s, c.key)} /></td>
                          <td className="t-meta" title={s.components[c.key]?.detail ?? ""}>{s.components[c.key]?.detail ?? "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Section>
                <Section id="sec-queues" title="Queues and regions">
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
                    <Fact label="Redis stream depth (certs raw)">{fmtInt(s.stream.queue_depth.certs_raw)}</Fact>
                    <Fact label="Enrichment queue">{fmtInt(s.stream.queue_depth.enrich)}</Fact>
                    <Fact label="Candidate queue">{fmtInt(s.metrics.domains_candidate)}</Fact>
                    <Fact label="Ledger write queue">{fmtInt(s.ledger.queue_depth)}{!s.ledger.available && <span className="t-meta"> (chain unreachable)</span>}</Fact>
                    <Fact label="Stream">{sentence(s.stream.mode)}, {s.stream.connection}</Fact>
                    <Fact label="Last heartbeat">{fmtDateTime(s.stream.last_heartbeat)}</Fact>
                    <Fact label="API region">{h.regions.api ?? "–"}{h.regions.api_city && <span className="t-meta"> {h.regions.api_city}</span>}</Fact>
                    <Fact label="Database region">{h.regions.database ?? "–"}{h.regions.database_city && <span className="t-meta"> {h.regions.database_city}</span>}</Fact>
                    <Fact label="Colocated">{h.regions.colocated === null ? "Unknown" : h.regions.colocated ? "Yes" : "No"}</Fact>
                    <Fact label="Database round trip">{h.database_round_trip_ms === null ? "–" : `${fmtNum(h.database_round_trip_ms, 1)} ms`}</Fact>
                  </div>
                </Section>
              </div>
              <Section id="sec-endpoints" title="Endpoint latency" aside={<span className="t-meta">Window <span className="mono">{fmtInt(h.window_s)} s</span></span>}>
                {endpoints.length === 0 ? <p className="t-meta">No requests in the window yet.</p> : (
                  <table className="tbl" aria-label="Endpoint latency">
                    <colgroup><col /><col style={{ width: 104 }} /><col style={{ width: 104 }} /><col style={{ width: 104 }} /></colgroup>
                    <thead><tr><th>Endpoint</th><th className="num">Requests</th><th className="num">p50 ms</th><th className="num">p95 ms</th></tr></thead>
                    <tbody>
                      {endpoints.map(([name, e]) => (
                        <tr key={name}><td className="mono">{name}</td><td className="num mono">{fmtInt(e.count)}</td>
                          <td className="num mono">{fmtNum(e.p50_ms, 1)}</td><td className="num mono">{fmtNum(e.p95_ms, 1)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>
            </>
          );
        }}
      </ViewStateView>
    </div>
  );
}
