import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, toApiError, type ApiError, type Evidence, type EvidenceSummary, type VerifyResult } from "../lib/api";
import { fmtDateTime, fmtInt, sentence, truncateHash } from "../lib/format";
import { POLL_MS, useLiveQuery } from "../lib/viewState";
import { Table, type Column } from "../components/Table";
import type { SysStatus } from "../lib/status";
import { HashDisplay } from "../components/HashDisplay";
import { SystemIndicator, StatusIndicator } from "../components/StatusIndicator";
import { Button } from "../components/Button";
import { Dropdown } from "../components/Dropdown";
import { ErrorState, SkeletonRows, ViewStateView, errorCopy } from "../components/States";
import { PageHeader, Section } from "../components/Page";

export const ONLY_HASHES = "Only hashes are anchored on the ledger, never evidence content.";

/** Expected and found side by side, every differing character marked. */
export function HashDiff({ expected, found }: { expected: string | null; found: string | null }) {
  const a = expected ?? "", b = found ?? "";
  const n = Math.max(a.length, b.length);
  const render = (s: string, other: string) => {
    const out: React.ReactNode[] = [];
    let run = "", runDiff = false;
    const flush = (i: number) => {
      if (!run) return;
      out.push(runDiff ? <mark key={i} className="diff-mark">{run}</mark> : <span key={i}>{run}</span>);
      run = "";
    };
    for (let i = 0; i < n; i++) {
      const ch = s[i] ?? "";
      if (!ch) break;
      const diff = ch !== other[i];
      if (diff !== runDiff) { flush(i); runDiff = diff; }
      run += ch;
    }
    flush(n);
    return out;
  };
  return (
    <div style={{ display: "grid", gridTemplateColumns: "72px minmax(0, 1fr)", gap: "4px 12px", alignItems: "baseline" }} data-testid="hash-diff">
      <span className="t-label">Expected</span>
      <span className="mono" data-testid="diff-expected" style={{ whiteSpace: "nowrap", overflowX: "auto" }}>{expected ? render(a, b) : <span className="ink-3">none</span>}</span>
      <span className="t-label">Found</span>
      <span className="mono" data-testid="diff-found" style={{ whiteSpace: "nowrap", overflowX: "auto" }}>{found ? render(b, a) : <span className="ink-3">missing</span>}</span>
    </div>
  );
}

/** The Merkle tree from tree.levels, root highlighted. Levels may come leaves-first or root-first. */
export function MerkleTree({ levels, failing }: { levels: string[][]; failing: Set<number> }) {
  if (!levels.length) return <p className="t-meta">No tree returned.</p>;
  const rows = levels[0].length === 1 && levels.length > 1 ? levels : [...levels].reverse(); // root first
  // Drawn at 1:1 (never scaled down below 11.5px text): width grows with the leaf count.
  const leaves = rows[rows.length - 1].length;
  const boxW = 96, rowH = 56, boxH = 24;
  const W = Math.max(400, leaves * (boxW + 8) + 16);
  const x = (row: number, i: number) => { const n = rows[row].length; const slot = W / n; return slot * i + slot / 2; };
  const H = rows.length * rowH;
  const chars = Math.max(4, Math.floor((boxW - 8) / 7));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", maxWidth: W }} role="img"
         aria-label={`Merkle tree with ${leaves} leaves and ${rows.length} levels; root ${rows[0][0]}`}>
      {rows.slice(1).map((row, r) => row.map((_, i) => {
        const parent = Math.floor(i / 2);
        return <line key={`${r}-${i}`} x1={x(r + 1, i)} y1={(r + 1) * rowH + 12} x2={x(r, Math.min(parent, rows[r].length - 1))} y2={r * rowH + 12 + boxH}
                     stroke="var(--hairline-firm)" strokeWidth={1} />;
      }))}
      {rows.map((row, r) => row.map((h, i) => {
        const root = r === 0;
        const leaf = r === rows.length - 1;
        const bad = leaf && failing.has(i);
        return (
          <g key={`${r}-${i}`} data-root={root || undefined}>
            <title>{h}</title>
            <rect x={x(r, i) - boxW / 2 + 0.5} y={r * rowH + 12.5} width={boxW - 1} height={boxH - 1}
                  fill={root ? "var(--action-weak)" : "var(--paper)"} stroke={root ? "var(--action)" : bad ? "var(--ink)" : "var(--hairline-firm)"}
                  strokeWidth={root ? 1.25 : 1} strokeDasharray={bad ? "3 2" : undefined} />
            <text x={x(r, i)} y={r * rowH + 12 + 16} textAnchor="middle" className="svg-mono" style={root ? { fill: "var(--action)", fontWeight: 500 } : undefined}>
              {h.slice(0, chars)}
            </text>
          </g>
        );
      }))}
    </svg>
  );
}

function checkStatus(ok: boolean): SysStatus { return ok ? "ok" : "failed"; }
const ANCHOR: Record<VerifyResult["anchor"]["status"], { s: SysStatus; label: string }> = {
  matches: { s: "ok", label: "Pass" },
  mismatch: { s: "failed", label: "Fail" },
  not_anchored: { s: "none", label: "Not anchored yet" },
  unavailable: { s: "degraded", label: "Chain unavailable" },
};

export function Checks({ r }: { r: VerifyResult }) {
  const anchor = ANCHOR[r.anchor.status] ?? { s: "none" as SysStatus, label: sentence(r.anchor.status) };
  return (
    <div data-testid="checks">
      <p className="t-section" data-testid="verdict" style={{ marginBottom: 12 }}>
        {r.valid ? "Pass: the bundle verifies." : "Fail: the bundle does not verify."}
        {r.simulated_tamper && <span className="t-meta"> Simulated one-byte flip in <span className="mono">{r.simulated_tamper}</span>, in memory only; the stored evidence is unchanged.</span>}
      </p>
      <table className="tbl" aria-label="Verification checks">
        <colgroup><col style={{ width: 232 }} /><col style={{ width: 176 }} /><col /></colgroup>
        <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
        <tbody>
          <tr data-check="root">
            <td>Recomputed Merkle root</td>
            <td><SystemIndicator status={checkStatus(r.root_matches)} label={r.root_matches ? "Pass" : "Fail"} /></td>
            <td className="t-meta">Recorded <HashDisplay value={r.expected_root} label="recorded root" />; recomputed <HashDisplay value={r.computed_root} label="recomputed root" /></td>
          </tr>
          <tr data-check="signature">
            <td>Ed25519 signature</td>
            <td><SystemIndicator status={checkStatus(r.signature_valid)} label={r.signature_valid ? "Pass" : "Fail"} /></td>
            <td className="t-meta">{r.signature_valid ? "Valid over the recorded root." : "Does not verify against the collector key."}</td>
          </tr>
          <tr data-check="anchor">
            <td>Anchored hash on chain</td>
            <td><SystemIndicator status={anchor.s} label={anchor.label} /></td>
            <td className="t-meta">{r.anchor.tx ? <>Transaction <HashDisplay value={r.anchor.tx} label="transaction hash" /></> : "No anchoring transaction."}</td>
          </tr>
        </tbody>
      </table>
      {r.failures.length > 0 && (
        <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
          {r.failures.map((f) => (
            <div key={f.artifact} className="panel panel-body" data-testid={`failure-${f.artifact}`}>
              <p style={{ marginBottom: 8 }}>
                <span className="mono">{f.artifact}</span>: {f.reason === "hash_mismatch" ? "hash mismatch" : f.reason === "missing" ? "missing from the bundle" : "not in the signed manifest"}
              </p>
              <HashDiff expected={f.expected} found={f.found} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Attestations({ r }: { r: VerifyResult }) {
  const entries = Object.entries(r.attestations ?? {});
  return (
    <>
      {r.disputed && (
        <p style={{ marginBottom: 12 }}><StatusIndicator severity="unknown" label="Disputed" /> <span className="ink-2">Another organisation disputes this record. Both attestations stand on the ledger.</span></p>
      )}
      {entries.length === 0 ? <p className="t-meta">No organisation has attested to this record yet.</p> : (
        <table className="tbl" aria-label="Attestations">
          <thead><tr><th>Organisation</th><th>Attestation</th></tr></thead>
          <tbody>
            {entries.map(([org, v]) => {
              const sev = v === "confirmed" ? "confirmed" : v === "dismissed" ? "benign" : "unknown";
              return <tr key={org}><td>{org}</td><td><StatusIndicator severity={sev} label={sentence(v)} /></td></tr>;
            })}
          </tbody>
        </table>
      )}
    </>
  );
}

export function EvidenceBody({ b, initial }: { b: Evidence; initial: VerifyResult | undefined }) {
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState<"verify" | "tamper" | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [target, setTarget] = useState(b.artifacts[0]?.name ?? "");
  const [showReport, setShowReport] = useState(false);
  const ctrl = useRef<AbortController | null>(null);
  useEffect(() => () => ctrl.current?.abort(), []);
  const report = useQuery({ queryKey: ["report", b.id], queryFn: () => api.report(b.id), enabled: showReport, staleTime: Infinity });

  const run = async (tamper: string | null) => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setBusy(tamper ? "tamper" : "verify");
    setErr(null);
    try {
      setResult(await api.verify(b.id, tamper, c.signal));
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") setErr(toApiError(e));
    } finally {
      if (ctrl.current === c) setBusy(null);
    }
  };

  const tree = (result ?? initial)?.tree;
  const failingNames = new Set((result?.failures ?? []).map((f) => f.artifact));
  const failingLeaves = new Set((tree?.leaves ?? []).map((l, i) => (failingNames.has(l.name) ? i : -1)).filter((i) => i >= 0));
  const tampered = !!result?.simulated_tamper;

  return (
    <>
      <p className="t-meta" style={{ marginBottom: 16 }} data-testid="only-hashes">{ONLY_HASHES}</p>
      <Section id="sec-verify" tour="verify" title="Verify" aside={
        <>
          <Button variant="primary" onClick={() => run(null)} disabled={busy !== null}>{tampered ? "Restore" : "Verify"}</Button>
          <Dropdown label="Artifact to tamper" hideLabel value={target} onChange={setTarget}
                    options={b.artifacts.map((a) => ({ value: a.name, label: a.name }))} />
          <Button onClick={() => run(target)} disabled={busy !== null || !target}
                  title="Flips one byte of the artifact in memory and re-verifies. Stored evidence is never modified.">Tamper (demo)</Button>
        </>
      }>
        {busy && <p className="t-meta" role="status">{busy === "tamper" ? "Re-verifying with a simulated one-byte flip" : "Verifying"}</p>}
        {err && <ErrorState error={err} what="the verification" />}
        {result ? <Checks r={result} /> : !busy && !err && (
          <p className="ink-2 prose">Verify recomputes every artifact hash and the Merkle root, checks the Ed25519 signature, and compares the root with the hash anchored on the ledger.</p>
        )}
      </Section>
      <div>
        <Section id="sec-artifacts" title="Bundle contents">
          <table className="tbl" aria-label="Artifacts">
            <colgroup><col /><col style={{ width: 168 }} /><col style={{ width: 96 }} /><col style={{ width: 96 }} /></colgroup>
            <thead><tr><th>Artifact</th><th>SHA-256</th><th className="num">Size</th><th>Check</th></tr></thead>
            <tbody>
              {b.artifacts.map((a) => (
                <tr key={a.name} data-testid={`artifact-${a.name}`}>
                  <td className="mono" title={a.name}>{a.name}</td>
                  <td><HashDisplay value={a.sha256} label={`${a.name} hash`} /></td>
                  <td className="num mono">{a.size_bytes === null ? "–" : fmtInt(a.size_bytes)}</td>
                  <td>{result ? <SystemIndicator status={failingNames.has(a.name) ? "failed" : "ok"} label={failingNames.has(a.name) ? "Fail" : "Pass"} /> : <span className="ink-3">{"–"}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="kv" style={{ marginTop: 16 }}>
            <tbody>
              <tr><th scope="row">Bundle root</th><td><HashDisplay value={b.bundle_root} label="bundle root" /></td></tr>
              <tr><th scope="row">Signature</th><td><HashDisplay value={b.signature} label="signature" /></td></tr>
              <tr><th scope="row">Collector key</th><td><HashDisplay value={b.collector_pk} label="collector key" /></td></tr>
              <tr><th scope="row">Created</th><td className="mono">{fmtDateTime(b.created_at)}</td></tr>
              <tr><th scope="row">Anchored</th><td>{b.anchored_tx ? <><HashDisplay value={b.anchored_tx} label="transaction hash" /> <span className="mono t-meta">{fmtDateTime(b.anchored_at)}</span></> : "Not yet"}</td></tr>
            </tbody>
          </table>
          {b.partial && <p className="t-meta" style={{ marginTop: 8 }}>Partial bundle: some artifacts could not be collected.</p>}
        </Section>
        <Section id="sec-tree" title="Merkle tree" aside={tree && <span className="t-meta">Root <span className="mono">{truncateHash(tree.levels.length ? (tree.levels[0].length === 1 ? tree.levels[0][0] : tree.levels[tree.levels.length - 1][0]) : "")}</span></span>}>
          {tree ? <MerkleTree levels={tree.levels} failing={failingLeaves} /> : <p className="t-meta">The tree appears once the bundle has been verified.</p>}
        </Section>
      </div>
      <Section id="sec-attest" title="Attestations">
        {result ?? initial ? <Attestations r={(result ?? initial)!} /> : <p className="t-meta">Attestations load with the verification.</p>}
      </Section>
      <Section id="sec-report" tour="report" title="Abuse report" aside={<Button size="sm" onClick={() => setShowReport((v) => !v)}>{showReport ? "Hide report" : "Show report"}</Button>}>
        <p className="t-meta">Generated for review. Never sent: QCertChain does not submit takedown requests.</p>
        {showReport && (report.isError ? <p className="ink-2" style={{ marginTop: 8 }}>{errorCopy(toApiError(report.error), "the report")}</p>
          : report.data ? <pre className="code" style={{ marginTop: 8, maxHeight: 360, whiteSpace: "pre-wrap" }}>{report.data.body}</pre>
          : <div style={{ height: 96, marginTop: 8, background: "var(--sunken)" }} aria-busy="true" />)}
      </Section>
    </>
  );
}

export function EvidencePage() {
  const { id = "" } = useParams();
  const b = useLiveQuery<Evidence>({ queryKey: ["evidence", id], queryFn: (s) => api.evidence(id, s), isEmpty: () => false, staleTime: 60_000 });
  // The plain verification is fetched in parallel for the tree and attestations; the checks show on "Verify".
  const v = useLiveQuery<VerifyResult>({ queryKey: ["verify", id], queryFn: (s) => api.verify(id, null, s), isEmpty: () => false, staleTime: 60_000, retry: 0 });
  return (
    <div>
      <PageHeader title="Evidence" meta={<>Bundle <span className="mono">{id}</span>{b.data?.domain_id != null && <>; <Link className="link" to={`?domain=${b.data.domain_id}`}>open the domain</Link></>}</>} />
      <ViewStateView state={b.state} what="this evidence bundle" empty={null} onRetry={() => b.query.refetch()}
                     skeleton={<div className="panel" style={{ height: 320, background: "var(--sunken)" }} aria-busy="true" />}>
        {(bundle) => <EvidenceBody b={bundle} initial={v.data} />}
      </ViewStateView>
    </div>
  );
}

const BUNDLE_COLUMNS: Column<EvidenceSummary>[] = [
  { key: "domain", header: "Domain", render: (b) => (
    <Link className="link mono" to={`/evidence/${encodeURIComponent(b.bundle_id)}`}
          aria-label={b.domain ? `Open the evidence for ${b.domain}` : `Open bundle ${b.bundle_id}`}>{b.domain ?? "Domain no longer stored"}</Link>
  ) },
  { key: "created", header: "Sealed", width: 176, mono: true, render: (b) => fmtDateTime(b.created_at) },
  { key: "ledger", header: "Ledger", width: 168, render: (b) => (b.anchored ? "Anchored" : "Queued for the ledger") },
  { key: "id", header: "Bundle id", width: 176, render: (b) => <HashDisplay value={b.bundle_id} label="bundle id" /> },
];

export function EvidenceIndexPage() {
  const nav = useNavigate();
  const [id, setId] = useState("");
  const list = useLiveQuery<EvidenceSummary[]>({ queryKey: ["evidence-list"], queryFn: (s) => api.evidenceList(20, s),
                                                 poll: POLL_MS, isEmpty: (d) => d.length === 0 });
  return (
    <div>
      <PageHeader title="Evidence" meta={ONLY_HASHES} />
      <Section id="sec-bundles" title="Your evidence bundles">
        <p className="prose ink-2">The newest bundles your organisation sealed. Open one to see its artifacts, verify it against the ledger, or read its abuse report.</p>
        <div style={{ marginTop: 12 }}>
          <ViewStateView state={list.state} what="your evidence bundles" onRetry={() => list.query.refetch()}
                         empty="No bundles yet. A bundle is sealed when a page check confirms a domain, and for every seeded demo campaign."
                         skeleton={<SkeletonRows columns={[240, 176, 168, 176]} rows={6} />}>
            {(rows) => <Table<EvidenceSummary> label="Your evidence bundles" columns={BUNDLE_COLUMNS} rows={rows}
                                               rowKey={(b) => b.bundle_id}
                                               onOpen={(b) => nav(`/evidence/${encodeURIComponent(b.bundle_id)}`)} />}
          </ViewStateView>
        </div>
      </Section>
      <section className="panel panel-body prose">
        <p>Evidence bundles are built for confirmed domains. Open one from the list above, from a domain's detail (Live queue, then a confirmed row), or enter a bundle id.</p>
        <form style={{ display: "flex", gap: 8, marginTop: 16 }} onSubmit={(e) => { e.preventDefault(); if (id.trim()) nav(`/evidence/${encodeURIComponent(id.trim())}`); }}>
          <label htmlFor="bundle-id" className="sr-only">Bundle id</label>
          <input id="bundle-id" className="input mono" style={{ flex: 1 }} placeholder="Bundle id" value={id} onChange={(e) => setId(e.target.value)} />
          <button type="submit" className="btn btn-primary" disabled={!id.trim()}>Open bundle</button>
        </form>
      </section>
    </div>
  );
}
