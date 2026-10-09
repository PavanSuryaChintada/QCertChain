import { api, isUnavailable, type LeadTime, type MetricsReport, type StageTiming } from "../lib/api";
import { fmtDateTime, fmtDuration, fmtInt, fmtNum, sentence } from "../lib/format";
import { useLiveQuery } from "../lib/viewState";
import { LineChart, SeriesLegend, type Series } from "../components/charts";
import { ViewStateView } from "../components/States";
import { Fact, PageHeader, Section } from "../components/Page";

function NotMeasured({ reason }: { reason: string }) {
  return <p className="ink-2" data-testid="not-measured">Not measured - {reason}</p>;
}

/** Lead time: the largest figure on the page when it is measured; otherwise "Not measured yet" with the reason. */
export function leadTimeFigure(lt: MetricsReport["lead_time"]): { measured: true; seconds: number; n: number } | { measured: false; reason: string } {
  if (isUnavailable(lt)) return { measured: false, reason: lt.unavailable };
  const l = lt as LeadTime;
  const n = typeof l.ct_first === "number" ? l.ct_first : typeof l.n_ct_first === "number" ? l.n_ct_first : 0;
  const secs = typeof l.lead_hours?.p50 === "number" ? l.lead_hours.p50 * 3600
    : typeof l.median_lead_s === "number" ? l.median_lead_s
    : typeof l.median_lead_minutes === "number" ? l.median_lead_minutes * 60 : null;
  const matched = typeof l.matched_domains === "number" ? l.matched_domains : l.n_matched;
  if (n <= 0) {
    const why = typeof matched === "number"
      ? `${matched} phishing domains matched our CT capture, and every one was listed before CT showed its certificate` +
        (l.caveat ? ` (${l.caveat})` : "")
      : "no case yet where the certificate appeared in CT before the phishing-feed listing";
    return { measured: false, reason: why };
  }
  if (secs === null) return { measured: false, reason: "the report carries CT-first cases but no median lead time" };
  return { measured: true, seconds: secs, n };
}

function LeadTimePanel({ lt }: { lt: MetricsReport["lead_time"] }) {
  const f = leadTimeFigure(lt);
  const l = isUnavailable(lt) ? null : (lt as LeadTime);
  return (
    <Section id="sec-lead" title="Lead time: CT certificate vs phishing-feed listing"
             aside={typeof l?.dataset === "string" && l.dataset ? <span className="t-meta" data-testid="lead-dataset">Dataset: {l.dataset}</span> : undefined}>
      {f.measured ? (
        <>
          <p className="mono" data-testid="lead-time" style={{ fontSize: 48, lineHeight: "48px", fontWeight: 500 }}>{fmtDuration(f.seconds)}</p>
          <p className="t-meta" style={{ marginTop: 8 }}>
            Median head start over <span className="mono">{fmtInt(f.n)}</span> CT-first cases
            {typeof (l?.matched_domains ?? l?.n_matched) === "number" && <> of <span className="mono">{fmtInt((l?.matched_domains ?? l?.n_matched) as number)}</span> matched domains</>}
            {typeof l?.p25_lead_s === "number" && typeof l?.p75_lead_s === "number" && <>; interquartile range <span className="mono">{fmtDuration(l.p25_lead_s)}</span> to <span className="mono">{fmtDuration(l.p75_lead_s)}</span></>}.
          </p>
        </>
      ) : (
        <>
          <p className="t-display" data-testid="lead-time">Not measured yet</p>
          <p className="ink-2 prose" style={{ marginTop: 8 }}>{sentence(f.reason)}.</p>
        </>
      )}
    </Section>
  );
}

function PrecisionPanel({ r }: { r: MetricsReport }) {
  const t = r.triage_rules;
  if (isUnavailable(t)) return <Section id="sec-precision" title="Triage precision"><NotMeasured reason={t.unavailable} /></Section>;
  const p = t.precision_at_1_in_1000_base_rate;
  return (
    <Section id="sec-precision" title="Triage precision at a 1:1000 base rate">
      <div style={{ display: "grid", gridTemplateColumns: "minmax(200px, auto) 1fr", gap: 24, alignItems: "start" }}>
        <div>
          <p className="mono" data-testid="precision" style={{ fontSize: 32, lineHeight: "32px", fontWeight: 500 }}>{p.value === null ? "–" : fmtNum(p.value, 4)}</p>
          <p className="t-meta" style={{ marginTop: 8 }}>at threshold <span className="mono">{fmtNum(t.threshold, 2)}</span></p>
        </div>
        <div className="prose">
          <p>This is NOT balanced-set precision: it assumes one phishing name per thousand certificates, as on the live stream ({p.method}).</p>
          <p className="ink-2" style={{ marginTop: 8 }}>Triage only nominates candidates; the two-strong-signal confirmation gate is what protects precision.</p>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(176px, 1fr))", gap: 16, marginTop: 24 }}>
        <Fact label="Recall, phishing naming our 40 brands">{fmtNum(t.recall_on_phishing_naming_our_40_brands.value, 3)} <span className="t-meta">n={fmtInt(t.recall_on_phishing_naming_our_40_brands.n)}</span></Fact>
        <Fact label="False positive rate">{fmtNum(t.false_positive_rate.value, 4)} <span className="t-meta">n={fmtInt(t.false_positive_rate.n)}</span></Fact>
        <Fact label="Hard-negative FP rate">{fmtNum(t.hard_negative_fp_rate.value, 4)} <span className="t-meta">n={fmtInt(t.hard_negative_fp_rate.n)}</span></Fact>
        <Fact label="Latency per name p50 / p95 / p99">{fmtNum(t.latency_us_per_name.p50, 0)} / {fmtNum(t.latency_us_per_name.p95, 0)} / {fmtNum(t.latency_us_per_name.p99, 0)} us</Fact>
      </div>
    </Section>
  );
}

function ThresholdPanel({ r }: { r: MetricsReport }) {
  const o = r.triage_threshold_options;
  if (isUnavailable(o)) return <Section id="sec-threshold" title="Threshold sweep"><NotMeasured reason={o.unavailable} /></Section>;
  const opts = o.options.filter((x) => x.threshold >= 0.2 - 1e-9 && x.threshold <= 0.8 + 1e-9).sort((a, b) => a.threshold - b.threshold);
  if (!opts.length) return <Section id="sec-threshold" title="Threshold sweep"><NotMeasured reason="no thresholds between 0.20 and 0.80 in the report" /></Section>;
  const series: Series[] = [
    { name: "Recall, our brands", points: opts.map((x) => ({ x: x.threshold, y: x.recall_our_brands })), stroke: "var(--ink)" },
    { name: "Recall, global feeds", points: opts.map((x) => ({ x: x.threshold, y: x.recall_global_feeds })), stroke: "var(--ink-2)", dash: "6 3" },
    { name: "Precision at 1:1000", points: opts.map((x) => ({ x: x.threshold, y: x.precision_at_1_in_1000 })), stroke: "var(--ink-3)", dash: "2 3" },
  ];
  const current = isUnavailable(r.triage_rules) ? null : r.triage_rules.threshold;
  return (
    <Section id="sec-threshold" title="Threshold sweep 0.20 to 0.80">
      <LineChart label="Recall and precision by triage threshold" series={series} width={720} height={260} xLabel="Triage threshold" yLabel="Rate"
                 yMin={0} yMax={1} xFmt={(v) => fmtNum(v, 2)} yFmt={(v) => fmtNum(v, 1)}
                 marker={current !== null ? { x: current, label: `current ${fmtNum(current, 2)}` } : undefined} />
      <SeriesLegend series={series} />
      <table className="tbl" style={{ marginTop: 16 }} aria-label="Threshold options">
        <thead><tr><th className="num">Threshold</th><th className="num">Precision at 1:1000</th><th className="num">Recall, our brands</th><th className="num">Recall, global feeds</th><th className="num">FP rate, random Tranco</th><th className="num">Hard-negative FP</th><th className="num">Candidates/h live</th></tr></thead>
        <tbody>
          {opts.map((x) => (
            <tr key={x.threshold} aria-selected={current !== null && Math.abs(x.threshold - current) < 1e-9 ? true : undefined}>
              <td className="num mono">{fmtNum(x.threshold, 2)}</td>
              <td className="num mono">{fmtNum(x.precision_at_1_in_1000, 4)}</td>
              <td className="num mono">{fmtNum(x.recall_our_brands, 3)}</td>
              <td className="num mono">{fmtNum(x.recall_global_feeds, 3)}</td>
              <td className="num mono">{fmtNum(x.fp_rate_random_tranco, 4)}</td>
              <td className="num mono">{fmtNum(x.hard_negative_fp_rate, 4)}</td>
              <td className="num mono">{fmtInt(x.candidates_per_hour_live)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="t-meta" style={{ marginTop: 8 }}>{o.precision_method}</p>
    </Section>
  );
}

const num = (v: unknown): number | null => typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : null;

/** Stage timings in MILLISECONDS. evaluate.py writes `<stage>_s` (seconds) and `<stage>_ms` keys with p50/p95, and
 *  sometimes numeric strings; everything is normalised so the bars share one scale. */
export function stageRows(rt: Record<string, unknown>): { stage: string; p50: number | null; p95: number | null }[] {
  const src = (rt.stages && typeof rt.stages === "object" ? rt.stages : rt) as Record<string, unknown>;
  return Object.entries(src).flatMap(([key, v]) => {
    if (!v || typeof v !== "object") return [];
    const s = v as StageTiming;
    const scale = key.endsWith("_s") ? 1000 : 1;
    const stage = key.replace(/_(s|ms)$/, "").replace(/_/g, " ");
    const p50 = num(s.p50_ms) ?? (num(s.p50) !== null ? (num(s.p50) as number) * scale : null);
    const p95 = num(s.p95_ms) ?? (num(s.p95) !== null ? (num(s.p95) as number) * scale : null);
    return p50 !== null || p95 !== null ? [{ stage, p50, p95 }] : [];
  });
}

/** Paired horizontal bars: p50 filled, p95 outlined. */
function ResponseTimePanel({ r }: { r: MetricsReport }) {
  const rt = r.response_time;
  if (isUnavailable(rt)) return <Section id="sec-rt" title="Per-stage response time"><NotMeasured reason={rt.unavailable} /></Section>;
  const rows = stageRows(rt as Record<string, unknown>);
  if (!rows.length) return <Section id="sec-rt" title="Per-stage response time"><NotMeasured reason="the report has no per-stage timings" /></Section>;
  const max = Math.max(...rows.map((x) => Math.max(x.p50 ?? 0, x.p95 ?? 0)), 1);
  const W = 880, L = 224, R = 216, rowH = 32;
  const sx = (v: number) => ((W - L - R) * v) / max;
  return (
    <Section id="sec-rt" title="Per-stage response time p50 / p95">
      <svg viewBox={`0 0 ${W} ${rows.length * rowH + 8}`} width="100%" style={{ maxWidth: W, display: "block" }} role="img" aria-label="Response time per stage">
        {rows.map((x, i) => (
          <g key={x.stage} transform={`translate(0 ${i * rowH + 4})`}>
            <text x={0} y={18} className="svg-text">{sentence(x.stage)}</text>
            {x.p95 !== null && <rect x={L + 0.5} y={6.5} width={Math.max(1, sx(x.p95))} height={15} fill="none" stroke="var(--ink-2)" strokeWidth={1} />}
            {x.p50 !== null && <rect x={L} y={10} width={Math.max(1, sx(x.p50))} height={8} fill="var(--ink-2)" />}
            <text x={W - R + 8} y={18} className="svg-mono">{fmtNum(x.p50, 0)} / {fmtNum(x.p95, 0)} ms</text>
          </g>
        ))}
      </svg>
      <p className="t-meta" style={{ marginTop: 8 }}>Filled bar: p50. Outlined bar: p95.</p>
    </Section>
  );
}

function OtherSection({ title, v }: { title: string; v: unknown }) {
  if (isUnavailable(v)) return <Section id={`sec-${title}`} title={title}><NotMeasured reason={v.unavailable} /></Section>;
  const entries = Object.entries((v ?? {}) as Record<string, unknown>).filter(([, x]) => typeof x === "number" || typeof x === "string" || typeof x === "boolean");
  return (
    <Section id={`sec-${title}`} title={title}>
      {entries.length === 0 ? <p className="t-meta">No scalar measurements in this section.</p> : (
        <table className="kv"><tbody>
          {entries.map(([k, x]) => <tr key={k}><th scope="row">{sentence(k)}</th><td className={typeof x === "number" || /^[0-9a-f-]{16,}$|^\d{4}-\d\d-\d\dT/.test(String(x)) ? "mono" : undefined}>{typeof x === "number" ? fmtNum(x, Number.isInteger(x) ? 0 : 3) : String(x)}</td></tr>)}
        </tbody></table>
      )}
    </Section>
  );
}

export function MetricsBody({ r }: { r: MetricsReport }) {
  const lead = leadTimeFigure(r.lead_time);
  return (
    <>
      {lead.measured && <LeadTimePanel lt={r.lead_time} />}
      <PrecisionPanel r={r} />
      {!lead.measured && <LeadTimePanel lt={r.lead_time} />}
      <ThresholdPanel r={r} />
      <ResponseTimePanel r={r} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 24 }}>
        <OtherSection title="Confirmation" v={r.confirmation} />
        <OtherSection title="Interdiction" v={r.interdiction} />
        <OtherSection title="Evidence and ledger" v={r.evidence_ledger} />
      </div>
    </>
  );
}

export function MetricsPage() {
  const q = useLiveQuery<MetricsReport>({ queryKey: ["metrics-report"], queryFn: api.metricsReport, isEmpty: () => false, staleTime: 60_000 });
  return (
    <div data-tour="metrics">
      <PageHeader title="Metrics" meta={<>Measured values only. {q.data && <>Report generated <span className="mono">{fmtDateTime(q.data.generated_at)}</span>.</>}</>} />
      <ViewStateView state={q.state} what="the metrics report" empty={null} onRetry={() => q.query.refetch()}
                     skeleton={<div className="panel" style={{ height: 320, background: "var(--sunken)" }} aria-busy="true" />}>
        {(r) => <MetricsBody r={r} />}
      </ViewStateView>
    </div>
  );
}
