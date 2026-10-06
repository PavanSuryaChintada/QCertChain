import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";

const CHANNELS = ["", "triage", "confirm", "enrich", "interdict", "evidence", "ledger", "email", "system"];

export function OpsLog() {
  const [channel, setChannel] = useState("");
  const q = useQuery({ queryKey: ["ops", channel], queryFn: () => api.ops(channel || undefined), refetchInterval: 4000 });
  return (
    <div className="p-6">
      <div className="flex items-center justify-between">
        <p className="panel-title" style={{ fontSize: 22 }}>Ops log</p>
        <label className="secondary flex items-center gap-2">channel
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            {CHANNELS.map((c) => <option key={c} value={c}>{c || "all"}</option>)}
          </select>
        </label>
      </div>
      <p className="secondary">Append-only. Every degradation the system hits is written here.</p>
      <ol className="mt-3">
        {q.data?.items.length === 0 && <li className="secondary">Nothing logged on this channel yet.</li>}
        {q.data?.items.map((i) => (
          <li key={i.id} className="grid gap-3 py-1 rule-b" style={{ gridTemplateColumns: "180px 88px 1fr" }}>
            <span className="mono secondary" style={{ fontSize: 12 }}>{i.at.slice(0, 19)}Z</span>
            <span className="mono" style={{ fontSize: 12, color: i.severity >= 3 ? "var(--ink-000)" : "var(--ink-200)" }}>{i.channel}</span>
            <span className="mono" style={{ fontSize: 12 }}>{i.message}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
