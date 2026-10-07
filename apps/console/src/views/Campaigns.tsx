import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type Campaign, type Page } from "../lib/api";
import { fmtDateTime, fmtInt, sentence } from "../lib/format";
import { POLL_MS, useLiveQuery } from "../lib/viewState";
import { Table, type Column } from "../components/Table";
import { SkeletonRows, ViewStateView } from "../components/States";
import { PageHeader } from "../components/Page";

const yesNo = (v: boolean | undefined) => (v === undefined ? <span className="ink-3">{"–"}</span> : v ? "Yes" : "No");

const COLUMNS: Column<Campaign>[] = [
  { key: "id", header: "Campaign id", width: 200, mono: true, render: (c) => c.label ?? c.id, title: (c) => `${c.label ?? ""} ${c.id}`.trim() },
  { key: "brand", header: "Brand", render: (c) => c.brands.join(", ") || <span className="ink-3">None</span>, title: (c) => c.brands.join(", ") },
  { key: "domains", header: "Domains", width: 88, align: "right", mono: true, render: (c) => fmtInt(c.domain_count) },
  { key: "infra", header: "Infra nodes", width: 104, align: "right", mono: true, render: (c) => fmtInt(c.infra_count) },
  { key: "first", header: "First seen", width: 176, mono: true, render: (c) => fmtDateTime(c.first_seen) },
  { key: "last", header: "Last seen", width: 176, mono: true, render: (c) => fmtDateTime(c.last_seen ?? null) },
  { key: "status", header: "Status", width: 104, render: (c) => sentence(c.status) },
  { key: "plan", header: "Has plan", width: 88, render: (c) => yesNo(c.has_plan) },
  { key: "anchored", header: "Anchored", width: 88, render: (c) => yesNo(c.anchored ?? (c.published_tx ? true : undefined)) },
];

export function CampaignsPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useLiveQuery<Page<Campaign>>({ queryKey: ["campaigns"], queryFn: (s) => api.campaigns({ limit: 200 }, s), poll: POLL_MS });
  // Hovering a row prefetches its graph, so the detail page opens with the graph already drawn.
  const prefetch = (c: Campaign) =>
    qc.prefetchQuery({ queryKey: ["graph", c.id], queryFn: () => api.graph(c.id), staleTime: 5 * 60_000 });
  return (
    <div>
      <PageHeader title="Campaigns" meta="Confirmed domains grouped by shared infrastructure. Open one to plan the takedowns." />
      <ViewStateView
        state={q.state}
        what="the campaign list"
        onRetry={() => q.query.refetch()}
        skeleton={<SkeletonRows columns={COLUMNS.map((c) => c.width)} rows={12} />}
        empty="No campaigns yet. A campaign forms once two confirmed domains share infrastructure."
      >
        {(d) => (
          <Table<Campaign>
            label="Campaigns"
            columns={COLUMNS}
            rows={d.items}
            rowKey={(c) => c.id}
            onHoverRow={prefetch}
            onOpen={(c) => nav(`/campaigns/${encodeURIComponent(c.id)}`)}
          />
        )}
      </ViewStateView>
    </div>
  );
}
