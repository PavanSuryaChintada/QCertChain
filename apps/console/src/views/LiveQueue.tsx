import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, CATEGORIES, type CandidateItem, type CandidateCounts, type Page, type TriageReasons } from "../lib/api";
import { fmtNum, fmtTime, sentence } from "../lib/format";
import { POLL_MS, useLiveQuery } from "../lib/viewState";
import { domainSeverity, useStatus } from "../lib/status";
import { Table, type Column } from "../components/Table";
import { SegmentedControl } from "../components/SegmentedControl";
import { Dropdown } from "../components/Dropdown";
import { StatusIndicator } from "../components/StatusIndicator";
import { ScoreBreakdown, featureText } from "../components/ScoreBreakdown";
import { SkeletonRows, ViewStateView } from "../components/States";
import { PageHeader } from "../components/Page";
import { Button } from "../components/Button";
import { StreamRail } from "../layout/StreamRail";
import { useToast } from "../components/Toast";

type Filter = "all" | "candidate" | "confirmed" | "dismissed";
const FILTERS: Filter[] = ["all", "candidate", "confirmed", "dismissed"];
/** Owner decision 2026-10-09: the queue opens on confirmed domains; the live candidates are one click away. */
const DEFAULT_FILTER: Filter = "confirmed";

export function sourceLabel(s: string): string {
  return s === "certstream" || s === "replay" ? "ct" : s;
}

const SHORT: Record<string, string> = {
  brand_token_exact: "brand", lookalike: "lookalike", homoglyph_hit: "homoglyph", tld_risk: "tld risk", keyword_count: "keywords",
  shape: "shape", skeleton_exact: "skeleton", allowlisted: "allowlisted", public_suffix: "public suffix",
};
export function signalNames(reasons: TriageReasons | null | undefined): string {
  const rs = (reasons?.reasons ?? []).filter((x) => Number(x.contribution) > 0).sort((a, b) => Number(b.contribution) - Number(a.contribution));
  return rs.map((x) => SHORT[x.feature] ?? x.feature.replace(/_/g, " ")).join(", ");
}

/** Contributing features. Uses the row's triage_reasons, or the domain detail once it is cached (score hover). */
function SignalsCell({ r }: { r: CandidateItem }) {
  const cached = useQuery({ queryKey: ["domain", r.id], queryFn: () => api.domain(r.id), enabled: false });
  const text = signalNames(r.triage_reasons ?? cached.data?.triage);
  if (text) return <span title={(r.triage_reasons ?? cached.data?.triage)?.reasons.map((x) => `${featureText(x.feature)} ${fmtNum(Number(x.contribution), 2)}`).join("; ")}>{text}</span>;
  return <span className="ink-3" title="Not in the list response; hover the score to load the breakdown">{"–"}</span>;
}

const COLUMNS: Column<CandidateItem>[] = [
  { key: "time", header: "Time", width: 88, mono: true, render: (r) => fmtTime(r.first_seen), title: (r) => r.first_seen },
  { key: "domain", header: "Domain", mono: true, render: (r) => r.name, title: (r) => r.name },
  { key: "brand", header: "Brand matched", width: 112, render: (r) => r.brand_matched ?? <span className="ink-3">None</span>, title: (r) => r.brand_matched ?? "" },
  { key: "score", header: "Triage score", width: 96, align: "right", render: (r) => <ScoreBreakdown score={r.triage_score} reasons={r.triage_reasons} domainId={r.id} /> },
  { key: "signals", header: "Signals", width: 152, render: (r) => <SignalsCell r={r} /> },
  { key: "source", header: "Source", width: 64, mono: true, render: (r) => sourceLabel(r.source) },
  { key: "status", header: "Status", width: 192, render: (r) => { const s = domainSeverity(r.status); return <StatusIndicator severity={s.severity} label={s.label} />; } },
];

/** Keyed row diffing: never reorder under the pointer or while a row is open; queue new rows behind a bar. */
export function useHeldRows(incoming: CandidateItem[] | undefined, hold: boolean, resetKey: string) {
  const [shown, setShown] = useState<CandidateItem[]>([]);
  const [pending, setPending] = useState<CandidateItem[] | null>(null);
  const [flash, setFlash] = useState<Set<number>>(() => new Set());
  const shownRef = useRef<CandidateItem[]>([]);
  const keyRef = useRef(resetKey);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const apply = useCallback((rows: CandidateItem[], animate: boolean) => {
    const prev = new Map(shownRef.current.map((r) => [r.id, r]));
    const changed = animate && prev.size ? rows.filter((r) => prev.get(r.id)?.status !== r.status).map((r) => r.id) : [];
    shownRef.current = rows;
    setShown(rows);
    setPending(null);
    if (changed.length) {
      setFlash(new Set(changed));
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setFlash(new Set()), 400);
    }
  }, []);

  useEffect(() => {
    if (!incoming) return;
    if (keyRef.current !== resetKey) {
      keyRef.current = resetKey;
      apply(incoming, false);
      return;
    }
    if (hold && shownRef.current.length) {
      const by = new Map(incoming.map((r) => [r.id, r]));
      const updated = shownRef.current.map((r) => by.get(r.id) ?? r);
      shownRef.current = updated;
      setShown(updated);
      const known = new Set(updated.map((r) => r.id));
      setPending(incoming.some((r) => !known.has(r.id)) ? incoming : null);
    } else {
      apply(incoming, true);
    }
  }, [incoming]); // eslint-disable-line react-hooks/exhaustive-deps

  const known = new Set(shown.map((r) => r.id));
  const newCount = pending ? pending.filter((r) => !known.has(r.id)).length : 0;
  return { shown, flash, newCount, applyPending: () => pending && apply(pending, true) };
}

export function LiveQueuePage() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const raw = params.get("status");
  const filter: Filter = FILTERS.includes(raw as Filter) ? (raw as Filter) : DEFAULT_FILTER;
  // spec 2026-10-09 §5: an organisation sees its own sector first ("other": every sector)
  const { data: sys } = useStatus();
  const own = sys?.org.category && sys.org.category !== "other" ? sys.org.category : "all";
  const sector = params.get("sector") ?? own;
  const setSector = (v: string) => {
    const next = new URLSearchParams(params);
    next.set("sector", v);
    setParams(next, { replace: true });
  };
  const domainId = params.get("domain");
  const [pointerIn, setPointerIn] = useState(false);
  const [older, setOlder] = useState<{ rows: CandidateItem[]; cursor: string | null; filter: Filter } | null>(null);

  const q = useLiveQuery<Page<CandidateItem>>({
    queryKey: ["candidates", filter, sector],
    queryFn: (s) => api.candidates({ status: filter === "all" ? undefined : filter, sector: sector === "all" ? undefined : sector, limit: 200 }, s),
    poll: POLL_MS,
    keepPrevious: true,
  });
  // Counts change slowly; polled at a third of the rate to stay well inside the request budget.
  const counts = useLiveQuery<CandidateCounts>({ queryKey: ["candidate-counts"], queryFn: api.candidateCounts, poll: 15000, isEmpty: () => false });

  const incoming = q.query.isPlaceholderData ? undefined : q.data?.items;
  const held = useHeldRows(incoming, pointerIn || domainId !== null, filter);
  const extra = older && older.filter === filter ? older.rows : [];
  const ids = new Set(held.shown.map((r) => r.id));
  const rows = [...held.shown, ...extra.filter((r) => !ids.has(r.id))];
  const nextCursor = older && older.filter === filter ? older.cursor : q.data?.next_cursor ?? null;

  const loadOlder = async () => {
    if (!nextCursor) return;
    try {
      const p = await api.candidates({ status: filter === "all" ? undefined : filter, limit: 200, cursor: nextCursor });
      setOlder({ rows: [...extra, ...p.items], cursor: p.next_cursor, filter });
    } catch {
      toast("Could not load older rows. The API did not answer; try again in a moment.");
    }
  };

  const setFilter = (f: Filter) => {
    const next = new URLSearchParams(params);
    if (f === DEFAULT_FILTER) next.delete("status"); else next.set("status", f);
    setParams(next, { replace: true });
  };
  const open = (id: number) => {
    const next = new URLSearchParams(params);
    next.set("domain", String(id));
    setParams(next);
  };
  const c = counts.data;

  return (
    <div>
      <PageHeader
        title="Live queue"
        meta="Nominated by triage from CT and email links. Refreshes every 5s."
        actions={<div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Dropdown label="Sector" value={sector} onChange={setSector}
                    options={[{ value: "all", label: "All sectors" }, ...CATEGORIES.filter((c) => c.value !== "other")]} />
          <div data-tour="status-filter">
          <SegmentedControl<Filter>
            label="Filter by status"
            value={filter}
            onChange={setFilter}
            segments={[
              { value: "all", label: "All", count: c ? c.all : null },
              { value: "candidate", label: "Candidates", count: c ? c.candidate : null },
              { value: "confirmed", label: "Confirmed", count: c ? c.confirmed : null },
              { value: "dismissed", label: "Dismissed", count: c ? c.dismissed : null },
            ]}
          /></div>
        </div>}
      />
      {held.newCount > 0 && (
        <button type="button" className="btn btn-ghost" onClick={held.applyPending}
                style={{ width: "100%", justifyContent: "flex-start", background: "var(--action-weak)", marginBottom: 8 }}>
          {held.newCount} new - click to apply
        </button>
      )}
      <ViewStateView
        state={q.state}
        what="the live queue"
        onRetry={() => q.query.refetch()}
        skeleton={<SkeletonRows columns={COLUMNS.map((x) => x.width)} rows={25} density="compact" />}
        empty={filter === "all"
          ? "No domains yet. Candidates appear here as the certificate stream is triaged; if the stream is down, System health says why."
          : `No ${sentence(filter).toLowerCase()} domains yet.`}
      >
        {() => (
          <>
            <div data-tour="queue"><Table<CandidateItem>
              label="Live queue"
              columns={COLUMNS}
              rows={rows}
              rowKey={(r) => r.id}
              density="compact"
              selectedKey={domainId ? Number(domainId) : null}
              rowBar={(r) => domainSeverity(r.status).severity}
              flashKeys={held.flash}
              virtualizeAbove={200}
              maxHeight={rows.length > 200 ? "calc(100vh - 220px)" : undefined}
              onOpen={(r) => open(r.id)}
              onPointerInside={setPointerIn}
            /></div>
            <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8 }}>
              <span className="t-meta">{rows.length} rows</span>
              {nextCursor && <Button size="sm" onClick={loadOlder}>Load older</Button>}
            </div>
          </>
        )}
      </ViewStateView>
      <StreamRail onOpen={open} />
    </div>
  );
}
