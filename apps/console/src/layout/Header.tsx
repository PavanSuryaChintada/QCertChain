import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api } from "../lib/api";
import { ModeIndicator } from "../components/ModeIndicator";
import { Num } from "../components/Mono";

const NAV = [
  { to: "/", label: "Console", end: true },
  { to: "/email", label: "Email headers" },
  { to: "/org2", label: "Second organisation" },
  { to: "/ops", label: "Ops log" },
];

export function Header() {
  const qc = useQueryClient();
  const state = useQuery({ queryKey: ["stream-state"], queryFn: api.streamState, refetchInterval: 3000 });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 5000 });
  const mode = useMutation({
    mutationFn: (m: "live" | "replay") => api.setMode(m, m === "replay" ? 5 : 1),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stream-state"] }),
  });
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
        <button onClick={() => mode.mutate(s?.mode === "replay" ? "live" : "replay")} disabled={mode.isPending}>
          {s?.mode === "replay" ? "Switch to live" : "Switch to replay"}
        </button>
      </div>
    </header>
  );
}
