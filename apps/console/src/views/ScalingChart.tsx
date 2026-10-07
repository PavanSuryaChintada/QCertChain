// Section A1(c): how each solver's time grows with campaign size. Log scale on time, because exhaustive search grows
// exponentially and nothing else would fit on the same axis. Measured points are solid; the exhaustive-search points
// beyond the measured range are extrapolated from the fitted ns-per-subset rate and drawn dashed, and say so.
import type { ReactNode } from "react";
import type { Scaling, ScalingPoint } from "../lib/api";
import { fmtDateTime, fmtInt, fmtNum } from "../lib/format";
import { logScale, SeriesLegend, spreadLabels, type Series } from "../components/charts";

export const MS = { second: 1_000, hour: 3_600_000, year: 365 * 86_400_000 } as const;
export const REFERENCES: { id: "1s" | "1h" | "1yr"; ms: number; label: string; threshold: keyof Scaling["thresholds"] }[] = [
  { id: "1s", ms: MS.second, label: "1 second", threshold: "one_second" },
  { id: "1h", ms: MS.hour, label: "1 hour", threshold: "one_hour" },
  { id: "1yr", ms: MS.year, label: "1 year", threshold: "one_year" },
];

const last = <T,>(a: T[]): T | undefined => a[a.length - 1];

type Key = "bruteforce_ms" | "cpsat_ms" | "greedy_ms" | "qaoa_ms";
const STYLE: Record<Key, { name: string; stroke: string; dash?: string }> = {
  bruteforce_ms: { name: "Exhaustive search", stroke: "var(--ink)" },
  cpsat_ms: { name: "CP-SAT", stroke: "var(--ink-2)" },
  greedy_ms: { name: "Greedy", stroke: "var(--ink-3)", dash: "1 3" },
  qaoa_ms: { name: "QAOA", stroke: "var(--ink-2)", dash: "8 3 2 3" },
};
const EXTRAPOLATED_DASH = "6 4";

/** The k rule as the caption should say it: "k = n/4". */
export function kRuleText(s: Scaling): string {
  if (s.k_rule) return `k = ${s.k_rule}`;
  return s.k === null || s.k === undefined ? "k as recorded per point" : `k = ${s.k}`;
}

export function ScalingChart({ scaling, campaignN, width = 1040, height = 400 }: {
  scaling: Scaling; campaignN: number | null; width?: number; height?: number;
}) {
  const pts = [...scaling.points].sort((a, b) => a.n - b.n);
  const m = { l: 64, r: 200, t: 20, b: 64 };
  const ns = [...pts.map((p) => p.n), ...(campaignN !== null ? [campaignN] : [])];
  const x0 = Math.min(...ns), x1 = Math.max(...ns);
  const sx = (x: number) => m.l + ((x - x0) / (x1 - x0 || 1)) * (width - m.l - m.r);

  const keys: Key[] = ["bruteforce_ms", "cpsat_ms", "greedy_ms", "qaoa_ms"];
  const values = pts.flatMap((p) => keys.map((k) => p[k])).filter((v): v is number => v !== null && v > 0);
  const lo = 10 ** Math.floor(Math.log10(Math.min(...values, MS.second)));
  const hi = 10 ** Math.ceil(Math.log10(Math.max(...values, MS.year)));
  const sy = logScale(lo, hi, height - m.b, m.t);
  const decades = Math.round(Math.log10(hi / lo));
  const step = Math.max(1, Math.ceil(decades / 8));
  const yTicks = Array.from({ length: Math.floor(decades / step) + 1 }, (_, i) => Math.round(Math.log10(lo)) + i * step);

  const line = (key: Key, keep: (p: ScalingPoint) => boolean) =>
    pts.filter((p) => keep(p) && p[key] !== null && (p[key] as number) > 0).map((p) => ({ x: p.n, y: p[key] as number }));
  const measuredBf = line("bruteforce_ms", (p) => !p.bruteforce_extrapolated);
  const extraBf = line("bruteforce_ms", (p) => p.bruteforce_extrapolated);
  // The dashed run starts at the last measured point, so the line is continuous where measurement stops.
  const extraRun = measuredBf.length && extraBf.length ? [measuredBf[measuredBf.length - 1], ...extraBf] : extraBf;
  const others = (["cpsat_ms", "greedy_ms", "qaoa_ms"] as Key[]).map((k) => ({ key: k, pts: line(k, () => true) }));
  const path = (ps: { x: number; y: number }[]) => ps.map((p) => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");

  const qaoaLast = last(others.find((o) => o.key === "qaoa_ms")!.pts);
  const qaoaStops = qaoaLast && qaoaLast.x < pts[pts.length - 1].n;
  const ends = spreadLabels([
    ...(extraRun.length || measuredBf.length ? [{ key: "bruteforce_ms" as Key, ...(last(extraRun) ?? last(measuredBf))!, text: "Exhaustive search" }] : []),
    ...others.filter((o) => o.pts.length).map((o) => ({ key: o.key, ...last(o.pts)!,
      text: o.key === "qaoa_ms" && qaoaStops ? `QAOA (stops at n = ${last(o.pts)!.x})` : STYLE[o.key].name })),
  ].map((e) => ({ ...e, px: sx(e.x), y: sy(e.y) })));

  const mid = extraRun.length >= 2 ? extraRun[Math.floor((extraRun.length - 1) / 2)] : null;
  const midNext = extraRun.length >= 2 ? extraRun[Math.floor((extraRun.length - 1) / 2) + 1] : null;
  const plotR = width - m.r;
  const exp = (e: number): ReactNode => <>10<tspan dy={-5} style={{ fontSize: 9 }}>{e}</tspan></>;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ display: "block" }} role="img" data-testid="scaling-chart"
         aria-label={`Solve time against targetable nodes n, log scale. Exhaustive search is measured up to n = ${last(measuredBf)?.x ?? "none"} and extrapolated beyond.`}>
      {yTicks.map((e) => (
        <g key={`y${e}`}>
          <line x1={m.l} x2={plotR} y1={sy(10 ** e)} y2={sy(10 ** e)} stroke="var(--hairline)" strokeWidth={1} />
          <text x={m.l - 8} y={sy(10 ** e) + 4} textAnchor="end" className="svg-mono">{exp(e)}</text>
        </g>
      ))}
      {pts.map((p) => (
        <g key={`x${p.n}`}>
          <text x={sx(p.n)} y={height - m.b + 16} textAnchor="middle" className="svg-mono">{p.n}</text>
          {p.k !== undefined && <text x={sx(p.n)} y={height - m.b + 30} textAnchor="middle" className="svg-mono" style={{ fill: "var(--ink-3)" }}>k={p.k}</text>}
        </g>
      ))}
      <line x1={m.l} x2={plotR} y1={height - m.b} y2={height - m.b} stroke="var(--hairline-firm)" strokeWidth={1} />
      <text x={(m.l + plotR) / 2} y={height - 6} textAnchor="middle" className="svg-text">Targetable nodes n (budget k beneath)</text>
      <text x={12} y={(m.t + height - m.b) / 2} textAnchor="middle" className="svg-text" transform={`rotate(-90 12 ${(m.t + height - m.b) / 2})`}>Solve time, ms (log scale)</text>

      {REFERENCES.map((r) => {
        const y = sy(r.ms);
        const tn = scaling.thresholds[r.threshold]?.n ?? null;
        return (
          <g key={r.id} data-testid={`ref-${r.id}`} data-y={y}>
            <line x1={m.l} x2={plotR} y1={y} y2={y} stroke="var(--hairline-firm)" strokeWidth={1} strokeDasharray="2 3" />
            <text x={m.l + 4} y={y + 13} className="svg-text">{r.label}</text>
            {tn !== null && tn >= x0 && tn <= x1 && (
              <g data-testid={`cross-${r.id}`}>
                <line x1={sx(tn)} x2={sx(tn)} y1={y - 5} y2={y + 5} stroke="var(--ink)" strokeWidth={1.25} />
                <text x={sx(tn) + 4} y={y + 14} className="svg-mono" style={{ fill: "var(--ink)" }}>exhaustive crosses at n = {fmtNum(tn, Number.isInteger(tn) ? 0 : 1)}</text>
              </g>
            )}
          </g>
        );
      })}

      {campaignN !== null && (
        <g data-testid="this-campaign">
          <line x1={sx(campaignN)} x2={sx(campaignN)} y1={m.t} y2={height - m.b} stroke="var(--action)" strokeWidth={1} strokeDasharray="2 3" />
          <text x={sx(campaignN) + 4} y={height - m.b - 6} className="svg-mono" style={{ fill: "var(--action)" }}>this campaign: n = {campaignN}</text>
        </g>
      )}

      {others.map((o) => o.pts.length > 0 && (
        <g key={o.key} data-series={o.key}>
          <polyline fill="none" stroke={STYLE[o.key].stroke} strokeWidth={1.25} strokeDasharray={STYLE[o.key].dash} points={path(o.pts)} />
          {o.pts.map((p) => <rect key={p.x} x={sx(p.x) - 2} y={sy(p.y) - 2} width={4} height={4} fill={STYLE[o.key].stroke} />)}
        </g>
      ))}
      <g data-series="bruteforce_ms">
        {measuredBf.length > 0 && (
          <polyline data-testid="bf-measured" fill="none" stroke="var(--ink)" strokeWidth={1.5} points={path(measuredBf)} />
        )}
        {extraRun.length > 1 && (
          <polyline data-testid="bf-extrapolated" data-extrapolated="true" fill="none" stroke="var(--ink)" strokeWidth={1.5}
                    strokeDasharray={EXTRAPOLATED_DASH} points={path(extraRun)} />
        )}
        {measuredBf.map((p) => <rect key={`m${p.x}`} x={sx(p.x) - 2.5} y={sy(p.y) - 2.5} width={5} height={5} fill="var(--ink)" />)}
        {extraBf.map((p) => <rect key={`e${p.x}`} data-extrapolated="true" x={sx(p.x) - 2.5} y={sy(p.y) - 2.5} width={5} height={5} fill="var(--paper)" stroke="var(--ink)" strokeWidth={1} />)}
        {mid && midNext && (
          <text data-testid="bf-extrapolated-label" x={(sx(mid.x) + sx(midNext.x)) / 2 - 8} y={(sy(mid.y) + sy(midNext.y)) / 2 - 8}
                textAnchor="end" className="svg-text" style={{ fill: "var(--ink)" }}>extrapolated</text>
        )}
      </g>
      {ends.map((e) => (
        <text key={e.key} x={Math.max(e.px, plotR) + 8} y={e.y + 4} className="svg-text" style={{ fill: STYLE[e.key].stroke === "var(--ink-3)" ? "var(--ink-2)" : STYLE[e.key].stroke }}>{e.text}</text>
      ))}
    </svg>
  );
}

export function ScalingLegend() {
  const s: Series[] = [
    { name: "Exhaustive search, measured", points: [], stroke: "var(--ink)" },
    { name: "Exhaustive search, extrapolated from the fit", points: [], stroke: "var(--ink)", dash: EXTRAPOLATED_DASH },
    { name: "CP-SAT", points: [], stroke: STYLE.cpsat_ms.stroke },
    { name: "Greedy", points: [], stroke: STYLE.greedy_ms.stroke, dash: STYLE.greedy_ms.dash },
    { name: "QAOA", points: [], stroke: STYLE.qaoa_ms.stroke, dash: STYLE.qaoa_ms.dash },
  ];
  return <SeriesLegend series={s} />;
}

export function ScalingCaption({ scaling }: { scaling: Scaling }) {
  const zeroGreedy = scaling.points.filter((p) => p.greedy_ms === 0).map((p) => p.n);
  const method = scaling.method.trim().replace(/\.+$/, "");
  const qaoaNote = scaling.points.find((p) => p.qaoa_ms === null && p.qaoa_note)?.qaoa_note ?? null;
  const measuredTo = [...scaling.points].filter((p) => !p.bruteforce_extrapolated).sort((a, b) => b.n - a.n)[0]?.n;
  return (
    <p className="t-meta" style={{ marginTop: 8, maxWidth: 880 }} data-testid="scaling-caption">
      Budget grows with the campaign ({kRuleText(scaling)}). Method: {method}. Machine: <span className="mono">{scaling.machine}</span>.
      {" "}Exhaustive search is measured{measuredTo !== undefined ? <> up to n = <span className="mono">{measuredTo}</span></> : null} and extrapolated beyond
      at the fitted <span className="mono">{fmtNum(scaling.fit.ns_per_subset, scaling.fit.ns_per_subset < 10 ? 2 : 1)}</span> ns per plan.
      {qaoaNote && <> QAOA line ends where the simulator stops: {qaoaNote}.</>}
      {zeroGreedy.length > 0 && <> Greedy read 0 ms (under the 1 ms timer resolution) at n = {zeroGreedy.join(", ")}; a log axis cannot draw zero, so those points are omitted.</>}
      {" "}Generated <span className="mono">{fmtDateTime(scaling.generated_at)}</span>; {fmtInt(scaling.points.length)} sizes.
    </p>
  );
}
