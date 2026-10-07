import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, toApiError, type EmailAnalysis, type Page } from "../lib/api";
import { domainOfUrl, fmtDateTime, fmtNum, sentence } from "../lib/format";
import { emailSeverity, domainSeverity } from "../lib/status";
import { useLiveQuery } from "../lib/viewState";
import { StatusIndicator, SystemIndicator } from "../components/StatusIndicator";
import { Button } from "../components/Button";
import { ErrorState, ViewStateView } from "../components/States";
import { PageHeader, Section } from "../components/Page";
import { Table, type Column } from "../components/Table";
import { Gate, SignalGroups } from "./DomainDetail";

const VERDICT_TEXT = {
  malicious: "Malicious: at least two independent strong signals.",
  suspicious: "Suspicious - not verified. Fewer than two strong signals; nothing here is an accusation yet.",
  clean: "No signals found in the headers.",
};

function authResult(v: string | undefined): { s: "ok" | "failed" | "none"; label: string } {
  if (!v) return { s: "none", label: "Absent" };
  const x = v.toLowerCase();
  if (x === "pass") return { s: "ok", label: "Pass" };
  if (["fail", "softfail", "permerror", "temperror"].includes(x)) return { s: "failed", label: sentence(x) };
  return { s: "none", label: sentence(x) };
}

function HeadersTable({ a }: { a: EmailAnalysis }) {
  const align = (d: string | null) => (!d || !a.from_etld1 ? { s: "none" as const, label: d ? "Not comparable" : "Absent" }
    : d === a.from_etld1 ? { s: "ok" as const, label: "Aligned with From" } : { s: "failed" as const, label: "Differs from From" });
  const rows: { name: string; value: React.ReactNode; result: { s: "ok" | "failed" | "none"; label: string } }[] = [
    { name: "From", value: <span className="mono">{a.from_addr ?? "absent"}</span>, result: a.from_addr ? { s: "ok", label: "Present" } : { s: "none", label: "Absent" } },
    { name: "Reply-To domain", value: <span className="mono">{a.reply_to_etld1 ?? "absent"}</span>, result: align(a.reply_to_etld1) },
    { name: "Return-Path domain", value: <span className="mono">{a.return_path_etld1 ?? "absent"}</span>, result: align(a.return_path_etld1) },
    { name: "SPF", value: <span className="mono">{a.auth.spf ?? "absent"}</span>, result: authResult(a.auth.spf) },
    { name: "DKIM", value: <span className="mono">{a.auth.dkim ?? "absent"}</span>, result: authResult(a.auth.dkim) },
    { name: "DMARC", value: <span className="mono">{a.auth.dmarc ?? "absent"}</span>, result: authResult(a.auth.dmarc) },
  ];
  return (
    <>
      <table className="tbl" aria-label="Parsed headers">
        <colgroup><col style={{ width: 176 }} /><col /><col style={{ width: 200 }} /></colgroup>
        <thead><tr><th>Header</th><th>Value</th><th>Check</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}><td>{r.name}</td><td>{r.value}</td><td><SystemIndicator status={r.result.s} label={r.result.label} /></td></tr>
          ))}
        </tbody>
      </table>
      {a.received.length > 0 && (
        <table className="tbl" aria-label="Received chain" style={{ marginTop: 16 }}>
          <colgroup><col /><col /><col style={{ width: 160 }} /><col style={{ width: 192 }} /></colgroup>
          <thead><tr><th>Received from</th><th>By</th><th>IP</th><th>At</th></tr></thead>
          <tbody>
            {a.received.map((r, i) => (
              <tr key={i}>
                <td className="mono" title={r.from_host ?? ""}>{r.from_host ?? "–"}</td>
                <td className="mono" title={r.by_host ?? ""}>{r.by_host ?? "–"}</td>
                <td className="mono">{r.ip ?? "–"}</td>
                <td className="mono">{r.at ? fmtDateTime(r.at) : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {a.absent.length > 0 && <p className="t-meta" style={{ marginTop: 8 }}>Not in the message: {a.absent.join(", ")}.</p>}
    </>
  );
}

function LinkDomains({ a }: { a: EmailAnalysis }) {
  // The contract gives URLs plus linked domain ids, not per-link scores; each linked domain is looked up (once,
  // in parallel) for its triage score and status.
  const ids = a.linked_domain_ids.slice(0, 20);
  const qs = useQueries({ queries: ids.map((id) => ({ queryKey: ["domain", id], queryFn: () => api.domain(id), staleTime: 60_000 })) });
  const known = new Map(qs.flatMap((q) => (q.data ? [[q.data.etld1, q.data] as const, [q.data.name, q.data] as const] : [])));
  const hosts = [...new Set(a.urls.map(domainOfUrl))];
  if (!hosts.length) return <p className="t-meta">No links in the message.</p>;
  const newIds = new Set(a.new_candidate_ids);
  return (
    <table className="tbl" aria-label="Link domains">
      <colgroup><col /><col style={{ width: 120 }} /><col style={{ width: 216 }} /><col style={{ width: 200 }} /></colgroup>
      <thead><tr><th>Link domain</th><th className="num">Triage score</th><th>Status</th><th>Pipeline</th></tr></thead>
      <tbody>
        {hosts.map((h) => {
          const d = known.get(h) ?? [...known.values()].find((x) => h.endsWith(`.${x.etld1}`));
          const sev = d ? domainSeverity(d.status) : null;
          return (
            <tr key={h}>
              <td className="mono" title={h}>{h}</td>
              <td className="num mono">{d ? fmtNum(d.triage.score, 2) : "–"}</td>
              <td>{sev ? <StatusIndicator severity={sev.severity} label={sev.label} /> : <span className="ink-3">Not a candidate</span>}</td>
              <td>{d ? <Link className="link" to={`/queue?domain=${d.id}`}>{newIds.has(d.id) ? "New candidate: open" : "Open in pipeline"}</Link> : <span className="ink-3">{"–"}</span>}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function AnalysisResult({ a }: { a: EmailAnalysis }) {
  const sev = emailSeverity(a.verdict);
  return (
    <div style={{ display: "grid", gap: 24 }}>
      {a.linked_campaigns.length > 0 && (
        <section className="panel panel-body" style={{ borderLeft: "3px solid var(--confirmed)" }} data-testid="correlation">
          <p className="t-section">Correlates with a known campaign</p>
          <p style={{ marginTop: 4 }}>
            {a.linked_campaigns.map((c, i) => (
              <span key={c.id}>{i > 0 && ", "}<Link className="link mono" to={`/campaigns/${encodeURIComponent(c.id)}`}>{c.label ?? c.id}</Link></span>
            ))}
          </p>
        </section>
      )}
      <section className="panel panel-body">
        <StatusIndicator severity={sev.severity} label={sev.label} />
        <p className="prose" style={{ marginTop: 8 }}>{VERDICT_TEXT[a.verdict]}</p>
        <div style={{ marginTop: 8 }}><Gate strong={a.strong_count} /></div>
        {a.verdict_history && a.verdict_history.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <p className="t-label">Verdict history{a.rescored_at && <> (re-scored <span className="mono">{fmtDateTime(a.rescored_at)}</span>)</>}</p>
            <ul style={{ marginTop: 4 }}>
              {a.verdict_history.map((h, i) => (
                <li key={i} className="t-meta"><span className="mono">{fmtDateTime(h.at)}</span> {sentence(h.from)} to {h.to}: {h.reason}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
      <Section id="sec-headers" title="Parsed headers"><HeadersTable a={a} /></Section>
      <Section id="sec-signals" title="Signals"><SignalGroups signals={a.signals} /></Section>
      <Section id="sec-links" title="Extracted link domains"><LinkDomains a={a} /></Section>
    </div>
  );
}

const RECENT: Column<EmailAnalysis>[] = [
  { key: "from", header: "From", mono: true, render: (a) => a.from_addr ?? "absent", title: (a) => a.from_addr ?? "" },
  { key: "verdict", header: "Verdict", width: 216, render: (a) => { const s = emailSeverity(a.verdict); return <StatusIndicator severity={s.severity} label={s.label} />; } },
  { key: "strong", header: "Strong signals", width: 120, align: "right", mono: true, render: (a) => String(a.strong_count) },
  { key: "source", header: "Source", width: 96, render: (a) => sentence(a.source) },
];

export function EmailAnalyzerPage() {
  const qc = useQueryClient();
  const [raw, setRaw] = useState("");
  const [dragging, setDragging] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const done = (a: EmailAnalysis) => { qc.invalidateQueries({ queryKey: ["email-analyses"] }); setOpenId(null); return a; };
  const analyze = useMutation({ mutationFn: (input: string | File) => (typeof input === "string" ? api.analyzeEmail(input) : api.analyzeEmailFile(input)).then(done) });
  const recent = useLiveQuery<Page<EmailAnalysis>>({ queryKey: ["email-analyses"], queryFn: (s) => api.emailAnalyses(null, s) });
  const opened = useLiveQuery<EmailAnalysis>({ queryKey: ["email-analysis", openId], queryFn: (s) => api.emailAnalysis(openId!, s), enabled: openId !== null, isEmpty: () => false });
  const shown = openId ? opened.data : analyze.data;
  const err = analyze.error ? toApiError(analyze.error) : null;

  return (
    <div>
      <PageHeader title="Email analyzer" meta="Paste raw headers or a whole message, or drop a .eml file. Nothing connects to a mailbox; bodies are read only for links and are not stored." />
      <section className="panel panel-body" style={{ marginBottom: 24 }}>
        <label htmlFor="raw-email" className="t-label">Raw message or headers</label>
        <textarea id="raw-email" className="input" rows={8} style={{ width: "100%", marginTop: 4, borderStyle: dragging ? "dashed" : "solid", borderColor: dragging ? "var(--action)" : undefined }}
                  value={raw} onChange={(e) => setRaw(e.target.value)}
                  placeholder={"From: \"Bank\" <alerts@bank-verify.example>\nAuthentication-Results: ...\n\nOr drop a .eml file here."}
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) analyze.mutate(f); }} />
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8 }}>
          <Button variant="primary" onClick={() => analyze.mutate(raw)} disabled={!raw.trim() || analyze.isPending}>Analyse</Button>
          <label className="btn" style={{ cursor: "pointer" }}>
            Choose .eml file
            <input type="file" accept=".eml,message/rfc822,text/plain" className="sr-only"
                   onChange={(e) => { const f = e.target.files?.[0]; if (f) analyze.mutate(f); e.target.value = ""; }} />
          </label>
          {analyze.isPending && <span className="t-meta" role="status">Analysing</span>}
        </div>
        {err && (
          <div style={{ marginTop: 12 }}>
            {err.status === 413
              ? <div className="state-box" role="alert">That message is larger than 2 MB. Paste just the headers, or trim the body.</div>
              : <ErrorState error={err} what="the analysis" />}
          </div>
        )}
      </section>
      {shown && <div style={{ marginBottom: 24 }}><AnalysisResult a={shown} /></div>}
      <h2 className="t-section" style={{ marginBottom: 8 }}>Recent analyses</h2>
      <ViewStateView state={recent.state} what="recent analyses" empty="No emails analysed yet." onRetry={() => recent.query.refetch()}
                     skeleton={<div style={{ height: 160, background: "var(--sunken)" }} aria-busy="true" />}>
        {(p) => <Table<EmailAnalysis> label="Recent analyses" columns={RECENT} rows={p.items} rowKey={(a) => a.id}
                                      selectedKey={openId} onOpen={(a) => setOpenId(a.id)} />}
      </ViewStateView>
    </div>
  );
}
