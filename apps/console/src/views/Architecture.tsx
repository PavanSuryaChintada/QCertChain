import { useNavigate } from "react-router-dom";
import type { ComponentKey, SystemStatus } from "../lib/api";
import { fmtInt, fmtNum } from "../lib/format";
import { SYS_LABEL, type SysStatus, componentStatus, useStatus } from "../lib/status";
import { SystemIndicator } from "../components/StatusIndicator";
import { ErrorState, StaleBar } from "../components/States";
import { PageHeader } from "../components/Page";

// Hand-authored geometry. viewBox width 1000 so the text renders at 11.5px or larger at 1280x800.
const W = 152, H = 72, GAP = 52, M = 16;
const col = (i: number) => M + i * (W + GAP);
const ROW1 = 48, ROW_EMAIL = 168, ROW3 = 288;

type Kind = "input" | "stage" | "store";
interface ArchNode { id: string; name: string; does: string; x: number; y: number; kind: Kind; to: string; component: ComponentKey | "api"; dest: string }

export const ARCH_NODES: ArchNode[] = [
  { id: "ct", name: "CT firehose", does: "certstream v1.10.1", x: col(0), y: ROW1, kind: "input", to: "/queue", component: "ct", dest: "Live queue" },
  { id: "triage", name: "Triage", does: "Name scoring, <5 ms", x: col(1), y: ROW1, kind: "stage", to: "/queue", component: "triage", dest: "Live queue" },
  { id: "confirm", name: "Confirm", does: "2 strong signals", x: col(2), y: ROW1, kind: "stage", to: "/queue?status=confirmed", component: "confirm", dest: "Confirmed domains" },
  { id: "enrich", name: "Enrich", does: "TLS / DNS / RDAP", x: col(3), y: ROW1, kind: "stage", to: "/queue?status=confirmed", component: "enrich", dest: "Confirmed domains" },
  { id: "graph", name: "Campaign graph", does: "Shared infrastructure", x: col(4), y: ROW1, kind: "stage", to: "/campaigns", component: "graph", dest: "Campaigns" },
  { id: "interdiction", name: "Interdiction", does: "Takedown set (QUBO)", x: col(4), y: ROW3, kind: "stage", to: "/campaigns", component: "interdiction", dest: "Campaigns" },
  { id: "evidence", name: "Evidence", does: "Merkle + Ed25519", x: col(3), y: ROW3, kind: "store", to: "/evidence", component: "evidence", dest: "Evidence" },
  { id: "ledger", name: "Ledger", does: "Anchored hash only", x: col(2), y: ROW3, kind: "store", to: "/ledger", component: "ledger", dest: "Ledger" },
  { id: "console", name: "Console", does: "Analyst review", x: col(1), y: ROW3, kind: "stage", to: "/health", component: "api", dest: "System health" },
  { id: "email", name: "Email headers", does: "Paste or .eml upload", x: col(0), y: ROW_EMAIL, kind: "input", to: "/email", component: "email", dest: "Email analyzer" },
];

const FILL: Record<Kind, string> = { input: "var(--sunken)", stage: "var(--paper)", store: "var(--paper)" };

function nodeStatus(s: SystemStatus | undefined, n: ArchNode): { status: SysStatus; detail: string | null } {
  if (n.component === "api") return { status: s ? (s.health.status === "ok" ? "ok" : "degraded") : "none", detail: s ? `API ${s.health.status}` : null };
  return { status: componentStatus(s, n.component), detail: s?.components[n.component]?.detail ?? null };
}

function StatusSquare({ x, y, status }: { x: number; y: number; status: SysStatus }) {
  const color = status === "ok" ? "var(--ok)" : status === "degraded" ? "var(--degraded)" : "var(--failed)";
  if (status === "ok") return <rect className="status-sq" x={x} y={y} width={8} height={8} fill={color} />;
  if (status === "degraded") return <g><rect x={x + 0.5} y={y + 0.5} width={7} height={7} fill="none" stroke={color} /><rect className="status-sq" x={x} y={y} width={4} height={8} fill={color} /></g>;
  if (status === "failed") return <g><rect x={x + 0.5} y={y + 0.5} width={7} height={7} fill="none" stroke={color} /><line x1={x + 0.5} y1={y + 7.5} x2={x + 7.5} y2={y + 0.5} stroke={color} /></g>;
  return <rect x={x + 0.5} y={y + 0.5} width={7} height={7} fill="none" stroke={color} />;
}

function EdgeLabel({ x, y, value, unit }: { x: number; y: number; value: string; unit: string }) {
  return (
    <g>
      <text x={x} y={y} textAnchor="middle" className="svg-mono" style={{ fill: "var(--ink)", fontWeight: 500 }}>{value}</text>
      <text x={x} y={y + 16} textAnchor="middle" className="svg-text">{unit}</text>
    </g>
  );
}

export function ArchitectureDiagram({ status }: { status: SystemStatus | undefined }) {
  const nav = useNavigate();
  const mid = (n: ArchNode) => n.y + H / 2;
  const by = Object.fromEntries(ARCH_NODES.map((n) => [n.id, n]));
  const row1 = ["ct", "triage", "confirm", "enrich", "graph"];
  const row3 = ["interdiction", "evidence", "ledger", "console"];
  const m = status?.metrics;
  const counters = [
    { value: status ? fmtNum(status.stream.certs_per_sec, 0) : "–", unit: "certs/s" },
    { value: m ? fmtInt(m.candidates_last_hour) : "–", unit: "candidates/h" },
    { value: m ? fmtInt(m.confirmations_last_hour) : "–", unit: "confirmed/h" },
  ];
  return (
    <svg viewBox="0 0 1000 384" width="100%" style={{ maxWidth: 1000, display: "block" }} role="group" aria-label="System architecture with live status">
      <defs>
        <marker id="arrow" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M0 0 L8 4 L0 8 z" fill="var(--ink-2)" />
        </marker>
      </defs>
      {/* row 1, left to right */}
      {row1.slice(0, -1).map((id, i) => {
        const a = by[id], b = by[row1[i + 1]];
        return <line key={id} x1={a.x + W} y1={mid(a)} x2={b.x - 2} y2={mid(b)} stroke="var(--ink-2)" strokeWidth={1.25} markerEnd="url(#arrow)" />;
      })}
      {counters.map((c, i) => <EdgeLabel key={c.unit} x={col(i) + W + GAP / 2} y={20} {...c} />)}
      {/* wrap: campaign graph down to interdiction */}
      <line x1={by.graph.x + W / 2} y1={ROW1 + H} x2={by.graph.x + W / 2} y2={ROW3 - 2} stroke="var(--ink-2)" strokeWidth={1.25} markerEnd="url(#arrow)" />
      {/* row 3, right to left */}
      {row3.slice(0, -1).map((id, i) => {
        const a = by[id], b = by[row3[i + 1]];
        return <line key={id} x1={a.x} y1={mid(a)} x2={b.x + W + 2} y2={mid(b)} stroke="var(--ink-2)" strokeWidth={1.25} markerEnd="url(#arrow)" />;
      })}
      {/* email headers: a second input into triage */}
      <polyline points={`${col(0) + W},${ROW_EMAIL + H / 2} ${col(1) + W / 2},${ROW_EMAIL + H / 2} ${col(1) + W / 2},${ROW1 + H + 2}`}
                fill="none" stroke="var(--ink-2)" strokeWidth={1.25} strokeDasharray="4 3" markerEnd="url(#arrow)" />
      <text x={col(1) + W / 2 + 8} y={ROW_EMAIL + H / 2 - 8} className="svg-text">link domains</text>

      {ARCH_NODES.map((n) => {
        const st = nodeStatus(status, n);
        const go = () => nav(n.to);
        return (
          <g key={n.id} className="arch-node" role="link" tabIndex={0} data-node={n.id} data-status={st.status}
             aria-label={`${n.name}: ${n.does}. Status ${SYS_LABEL[st.status]}. Opens ${n.dest}.`}
             onClick={go} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }}>
            <title>{`${n.name}: ${SYS_LABEL[st.status]}${st.detail ? ` - ${st.detail}` : ""}`}</title>
            <rect className="box" x={n.x + 0.5} y={n.y + 0.5} width={W - 1} height={H - 1} fill={FILL[n.kind]}
                  stroke="var(--hairline-firm)" strokeWidth={1} strokeDasharray={n.kind === "input" ? "4 3" : undefined} />
            {n.kind === "store" && <rect x={n.x} y={n.y} width={3} height={H} fill="var(--ink-3)" />}
            <text x={n.x + 12} y={n.y + 22} style={{ fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 600, fill: "var(--ink)" }}>{n.name}</text>
            <text x={n.x + 12} y={n.y + 40} className="svg-text">{n.does}</text>
            <StatusSquare x={n.x + 12} y={n.y + 52} status={st.status} />
            <text x={n.x + 26} y={n.y + 60} className="svg-text">{SYS_LABEL[st.status]}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Legend() {
  const item = (svg: React.ReactNode, text: string) => (
    <li style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <svg width="24" height="16" aria-hidden="true">{svg}</svg>
      <span>{text}</span>
    </li>
  );
  return (
    <ul className="t-meta" aria-label="Legend" style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 12 }}>
      {item(<rect x="0.5" y="0.5" width="23" height="15" fill="var(--sunken)" stroke="var(--hairline-firm)" strokeDasharray="4 3" />, "Input source")}
      {item(<rect x="0.5" y="0.5" width="23" height="15" fill="var(--paper)" stroke="var(--hairline-firm)" />, "Pipeline stage")}
      {item(<g><rect x="0.5" y="0.5" width="23" height="15" fill="var(--paper)" stroke="var(--hairline-firm)" /><rect x="0" y="0" width="3" height="16" fill="var(--ink-3)" /></g>, "Record store")}
      <li><SystemIndicator status="ok" label="Ok" /></li>
      <li><SystemIndicator status="degraded" label="Degraded (half-filled)" /></li>
      <li><SystemIndicator status="failed" label="Failed (crossed, grey)" /></li>
      <li><SystemIndicator status="none" label="No report (hollow)" /></li>
      <li>Click a stage to open its page.</li>
    </ul>
  );
}

const POSITIONS = [
  { title: "Nothing is ever sent", body: "Takedown plans and abuse reports are generated for review. A database constraint pins sent=false: no code path submits a report, files a form or calls a registrar." },
  { title: "Two strong signals to confirm", body: "A name match only nominates a candidate. A domain is confirmed only when the fetched page shows two independent strong signals, and the database rejects a confirmation with fewer." },
  { title: "Hashes on-chain, never evidence content", body: "The ledger holds Merkle roots, kit fingerprints, counts and the reporting organisation. Pages, screenshots, domain names and personal data never leave the evidence store." },
];

export function ArchitecturePage() {
  const { state, data, query } = useStatus();
  return (
    <div>
      <PageHeader title="Architecture" meta="The live pipeline. Each stage shows its status from the batched status poll (every 5s)." />
      {state.kind === "data" && state.staleSince !== null && <StaleBar since={state.staleSince} error={state.error} what="status" />}
      {state.kind === "error" && <div style={{ marginBottom: 8 }}><ErrorState error={state.error} what="the system status" onRetry={() => query.refetch()} /></div>}
      <section className="panel" style={{ padding: 16 }} aria-label="Architecture diagram">
        <ArchitectureDiagram status={data} />
        <Legend />
      </section>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginTop: 24 }}>
        {POSITIONS.map((p) => (
          <section key={p.title} className="panel panel-body">
            <h2 className="t-section">{p.title}</h2>
            <p className="prose ink-2" style={{ marginTop: 8 }}>{p.body}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
