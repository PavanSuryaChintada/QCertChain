import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api } from "../lib/api";
import { setKey } from "../lib/auth";
import { ModeIndicator } from "../components/ModeIndicator";
import { Num } from "../components/Mono";

const NAV = [
  { to: "/", label: "Console", end: true },
  { to: "/email", label: "Email headers" },
  { to: "/ledger", label: "Shared ledger" },
  { to: "/ops", label: "Ops log" },
];

export function Header() {
  const state = useQuery({ queryKey: ["stream-state"], queryFn: api.streamState, refetchInterval: 3000 });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 5000 });
  const ledger = useQuery({ queryKey: ["ledger-status"], queryFn: api.ledgerStatus, refetchInterval: 15000 });
  const me = ledger.data ? ledger.data.orgs[ledger.data.you]?.name ?? ledger.data.you : null;
  const s = state.data;
  const m = metrics.data;
  return (
    <header className="rule-b flex items-center gap-6 px-4" style={{ background: "var(--ground-100)" }}>
      <span className="panel-title" style={{ fontSize: 18 }}>QCertChain</span>
      {s ? (
        <ModeIndicator mode={s.mode} connection={s.connection} certsPerSec={s.certs_per_sec}
                       replayFile={s.replay_file ?? undefined} />
      ) : (
        <ModeIndicator mode="live" connection="down" certsPerSec={0} />
      )}
      <nav className="flex gap-1" aria-label="Views">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
                   className={({ isActive }) => `px-3 py-1 text-13 ${isActive ? "text-ink-0" : "text-ink-200"}`}
                   style={({ isActive }) => ({ borderBottom: isActive ? "2px solid var(--ink-000)" : "2px solid transparent" })}>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-5 text-13 text-ink-200">
        {m && (
          <>
            <span><Num v={m.campaigns_active} /> campaigns</span>
            <span><Num v={m.domains_confirmed} /> confirmed</span>
            <span><Num v={m.domains_candidate} /> candidates</span>
            <span title="Ledger writes waiting for the chain"><Num v={m.anchor_queue_depth} /> queued for ledger</span>
          </>
        )}
        {me && <span title="Your organisation: everything shown is scoped to it" style={{ color: "var(--ink-000)" }}>{me}</span>}
        <button onClick={() => setKey(null)}>Sign out</button>
      </div>
    </header>
  );
}
