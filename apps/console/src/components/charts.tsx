// Hand-drawn SVG charts. Flat: 1-1.25px strokes, solid fills, no shadows, no animation. Series are told apart by
// ink tone and dash pattern, not by colour, because colour is reserved for severity and system status.
import type { ReactNode } from "react";

export interface Series { name: string; points: { x: number; y: number | null }[]; dash?: string; stroke?: string }

export function niceTicks(min: number, max: number, n = 5): number[] {
  if (!(max > min)) return [min];
  const raw = (max - min) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-6; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

/** Log10 scale from a positive domain [d0, d1] onto a pixel range [r0, r1]. */
export function logScale(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const a = Math.log10(d0), b = Math.log10(d1);
  return (v) => r0 + ((Math.log10(v) - a) / (b - a || 1)) * (r1 - r0);
}

/** Push direct labels apart vertically so none is closer than `gap` px to its neighbour; keeps their order. */
export function spreadLabels<T extends { y: number }>(items: T[], gap = 13): T[] {
  const out = [...items].sort((p, q) => p.y - q.y).map((i) => ({ ...i }));
  for (let i = 1; i < out.length; i++) if (out[i].y - out[i - 1].y < gap) out[i].y = out[i - 1].y + gap;
  return out;
}

export function LineChart({ series, width = 560, height = 240, xLabel, yLabel, xFmt = String, yFmt = String, yMin, yMax,
  marker, label, extra }: {
  series: Series[]; width?: number; height?: number; xLabel: string; yLabel: string;
  xFmt?: (v: number) => string; yFmt?: (v: number) => string; yMin?: number; yMax?: number;
  marker?: { x: number; label: string }; label: string; extra?: (sx: (x: number) => number, sy: (y: number) => number) => ReactNode;
}) {
  const m = { l: 56, r: 16, t: 16, b: 40 };
  const xs = series.flatMap((s) => s.points.map((p) => p.x));
  const ys = series.flatMap((s) => s.points.map((p) => p.y).filter((y): y is number => y !== null));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = yMin ?? Math.min(0, ...ys), y1 = yMax ?? (Math.max(...ys, 0) || 1);
  const sx = (x: number) => m.l + ((x - x0) / (x1 - x0 || 1)) * (width - m.l - m.r);
  const sy = (y: number) => height - m.b - ((y - y0) / (y1 - y0 || 1)) * (height - m.t - m.b);
  const yt = niceTicks(y0, y1, 4);
  const xt = [...new Set(xs)].sort((a, b) => a - b);
  const xtShown = xt.length > 8 ? xt.filter((_, i) => i % Math.ceil(xt.length / 8) === 0) : xt;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ maxWidth: width, display: "block" }} role="img" aria-label={label}>
      {yt.map((v) => (
        <g key={`y${v}`}>
          <line x1={m.l} x2={width - m.r} y1={sy(v)} y2={sy(v)} stroke="var(--hairline)" strokeWidth={1} />
          <text x={m.l - 8} y={sy(v) + 4} textAnchor="end" className="svg-mono">{yFmt(v)}</text>
        </g>
      ))}
      {xtShown.map((v) => (
        <text key={`x${v}`} x={sx(v)} y={height - m.b + 16} textAnchor="middle" className="svg-mono">{xFmt(v)}</text>
      ))}
      <line x1={m.l} x2={width - m.r} y1={height - m.b} y2={height - m.b} stroke="var(--hairline-firm)" strokeWidth={1} />
      <text x={(m.l + width - m.r) / 2} y={height - 6} textAnchor="middle" className="svg-text">{xLabel}</text>
      <text x={12} y={(m.t + height - m.b) / 2} textAnchor="middle" className="svg-text" transform={`rotate(-90 12 ${(m.t + height - m.b) / 2})`}>{yLabel}</text>
      {marker && (
        <g>
          <line x1={sx(marker.x)} x2={sx(marker.x)} y1={m.t} y2={height - m.b} stroke="var(--ink-3)" strokeWidth={1} strokeDasharray="2 3" />
          <text x={sx(marker.x) + 4} y={m.t + 12} className="svg-text">{marker.label}</text>
        </g>
      )}
      {series.map((s) => {
        const pts = s.points.filter((p): p is { x: number; y: number } => p.y !== null);
        return (
          <g key={s.name}>
            <polyline fill="none" stroke={s.stroke ?? "var(--ink)"} strokeWidth={1.25} strokeDasharray={s.dash}
                      points={pts.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")} />
            {pts.map((p) => <rect key={p.x} x={sx(p.x) - 2} y={sy(p.y) - 2} width={4} height={4} fill={s.stroke ?? "var(--ink)"} />)}
          </g>
        );
      })}
      {extra?.(sx, sy)}
    </svg>
  );
}

export function SeriesLegend({ series }: { series: Series[] }) {
  return (
    <ul style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }} className="t-meta">
      {series.map((s) => (
        <li key={s.name} style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
          <svg width="24" height="8" aria-hidden="true"><line x1="0" x2="24" y1="4" y2="4" stroke={s.stroke ?? "var(--ink)"} strokeWidth="1.25" strokeDasharray={s.dash} /></svg>
          {s.name}
        </li>
      ))}
    </ul>
  );
}
