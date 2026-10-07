import { Link, useLocation } from "react-router-dom";
import { fmtInt, fmtNum } from "../lib/format";
import { SYS_LABEL, useStatus, worstStatus } from "../lib/status";
import { SystemIndicator } from "../components/StatusIndicator";
import { truncateHash } from "../lib/format";

const SECTION: Record<string, string> = {
  queue: "Live queue", campaigns: "Campaigns", evidence: "Evidence", email: "Email analyzer", ledger: "Ledger",
  metrics: "Metrics", health: "System health", ops: "Ops log",
};

export function Breadcrumb() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const crumbs: { to: string; label: string; mono?: boolean }[] = [{ to: "/", label: "Architecture" }];
  if (parts[0]) crumbs.push({ to: `/${parts[0]}`, label: SECTION[parts[0]] ?? parts[0] });
  if (parts[1]) crumbs.push({ to: pathname, label: truncateHash(decodeURIComponent(parts[1])), mono: true });
  return (
    <nav aria-label="Breadcrumb" style={{ minWidth: 0 }}>
      <ol style={{ display: "flex", gap: 8, alignItems: "center", whiteSpace: "nowrap" }}>
        {crumbs.map((c, i) => (
          <li key={c.to} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {i > 0 && <span className="ink-3" aria-hidden="true">/</span>}
            {i === crumbs.length - 1 ? (
              <span aria-current="page" className={c.mono ? "mono" : undefined} style={{ fontWeight: 500 }}>{c.label}</span>
            ) : (
              <Link to={c.to} className="link" style={{ textDecoration: "none" }}>{c.label}</Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Stat({ label, children, title }: { label: string; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} style={{ display: "inline-flex", gap: 8, alignItems: "baseline", whiteSpace: "nowrap" }}>
      <span className="t-meta">{label}</span>
      <span className="t-data">{children}</span>
    </span>
  );
}

const KEY_KIND = { org: "org", demo: "demo", admin: "admin" } as const;

export function Header() {
  const { data, state } = useStatus();
  const worst = worstStatus(data);
  const failedReq = state.kind === "error" || (state.kind === "data" && state.staleSince !== null);
  return (
    <header className="topbar">
      <Breadcrumb />
      <div style={{ marginLeft: "auto", display: "flex", gap: 24, alignItems: "center" }}>
        <Stat label="Ingest" title={data ? `Stream ${data.stream.mode}, ${data.stream.connection}` : undefined}>
          {data ? `${fmtNum(data.stream.certs_per_sec, data.stream.certs_per_sec < 10 ? 1 : 0)} certs/s` : "–"}
          {data?.stream.mode === "replay" && (
            <span className="t-meta" data-testid="replay-clock">
              {" · Replay"}
              {data.stream.virtual_time && <> · <span className="mono">{data.stream.virtual_time.slice(11, 16)} UTC</span></>}
              {data.stream.replay_speed && <> · <span className="mono">{fmtNum(data.stream.replay_speed, 0)}×</span></>}
            </span>
          )}
        </Stat>
        <Stat label="Candidate queue" title="Candidates waiting for page confirmation">
          {data ? fmtInt(data.metrics.domains_candidate) : "–"}
        </Stat>
        <Link to="/health" style={{ textDecoration: "none", color: "inherit" }} title="Open system health">
          <SystemIndicator status={failedReq ? "failed" : worst}
                           label={failedReq ? "Status unavailable" : worst === "ok" ? "All systems ok" : SYS_LABEL[worst]} />
        </Link>
        <Stat label="Region">{data?.health.regions.api ?? "–"}</Stat>
        <Stat label="Key">{data ? KEY_KIND[data.key_kind] ?? data.key_kind : "–"}</Stat>
      </div>
    </header>
  );
}
