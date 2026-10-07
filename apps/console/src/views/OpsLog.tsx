import { useState } from "react";
import { api, type OpsItem, type Page } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { POLL_MS, useLiveQuery } from "../lib/viewState";
import { Dropdown } from "../components/Dropdown";
import { Table, type Column } from "../components/Table";
import { Button } from "../components/Button";
import { SkeletonRows, ViewStateView } from "../components/States";
import { PageHeader } from "../components/Page";
import { useToast } from "../components/Toast";

const CHANNELS = ["", "triage", "confirm", "enrich", "interdict", "evidence", "ledger", "email", "system"] as const;
type Channel = (typeof CHANNELS)[number];
const SEVERITY = ["Debug", "Info", "Notice", "Warning", "Error", "Critical"];

const COLUMNS: Column<OpsItem>[] = [
  { key: "at", header: "Time", width: 184, mono: true, render: (i) => fmtDateTime(i.at) },
  { key: "channel", header: "Channel", width: 104, mono: true, render: (i) => i.channel },
  { key: "sev", header: "Severity", width: 96, render: (i) => SEVERITY[i.severity] ?? String(i.severity) },
  { key: "msg", header: "Message", mono: true, render: (i) => i.message, title: (i) => `${i.message}${i.context ? `\n${JSON.stringify(i.context)}` : ""}` },
];

export function OpsLogPage() {
  const toast = useToast();
  const [channel, setChannel] = useState<Channel>("");
  const [older, setOlder] = useState<{ ch: Channel; rows: OpsItem[]; cursor: string | null } | null>(null);
  const q = useLiveQuery<Page<OpsItem>>({ queryKey: ["ops", channel], queryFn: (s) => api.ops({ channel: channel || undefined, limit: 100 }, s), poll: POLL_MS, keepPrevious: true });
  const mine = older && older.ch === channel ? older : null;
  const cursor = mine ? mine.cursor : q.data?.next_cursor ?? null;
  const loadOlder = async () => {
    if (!cursor) return;
    try {
      const p = await api.ops({ channel: channel || undefined, limit: 100, cursor });
      setOlder({ ch: channel, rows: [...(mine?.rows ?? []), ...p.items], cursor: p.next_cursor });
    } catch {
      toast("Could not load older entries. The API did not answer; try again in a moment.");
    }
  };
  return (
    <div>
      <PageHeader title="Ops log" meta="Append-only. Every degradation the system hits is written here."
                  actions={<Dropdown<Channel> label="Channel" value={channel} onChange={setChannel}
                                              options={CHANNELS.map((c) => ({ value: c, label: c ? c[0].toUpperCase() + c.slice(1) : "All channels" }))} />} />
      <ViewStateView state={q.state} what="the ops log" onRetry={() => q.query.refetch()} empty="Nothing logged on this channel yet."
                     skeleton={<SkeletonRows columns={COLUMNS.map((c) => c.width)} rows={20} density="compact" />}>
        {(p) => {
          const ids = new Set(p.items.map((i) => i.id));
          const rows = [...p.items, ...(mine?.rows ?? []).filter((i) => !ids.has(i.id))];
          return (
            <>
              <Table<OpsItem> label="Ops log" columns={COLUMNS} rows={rows} rowKey={(i) => i.id} density="compact" virtualizeAbove={200}
                              maxHeight={rows.length > 200 ? "calc(100vh - 200px)" : undefined} />
              {cursor && <div style={{ marginTop: 8 }}><Button size="sm" onClick={loadOlder}>Load older</Button></div>}
            </>
          );
        }}
      </ViewStateView>
    </div>
  );
}
