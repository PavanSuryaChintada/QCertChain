// Formatting helpers. Everything a person compares down a column is rendered in mono by the caller.

/** First 8 characters, an ellipsis, then the last 6. Short values are returned unchanged. */
export function truncateHash(v: string): string {
  return v.length <= 16 ? v : `${v.slice(0, 8)}…${v.slice(-6)}`;
}

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "–";
  return Math.round(n).toLocaleString("en-US");
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "–";
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined || !Number.isFinite(n) ? "–" : `${fmtNum(n, digits)}%`;
}

export function fmtMs(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "–";
  return n >= 100 ? `${fmtInt(n)} ms` : `${fmtNum(n, n >= 10 ? 1 : 2)} ms`;
}

function valid(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** HH:MM:SS in UTC. */
export function fmtTime(iso: string | null | undefined): string {
  const d = valid(iso);
  return d ? d.toISOString().slice(11, 19) : "--:--:--";
}

/** YYYY-MM-DD HH:MM:SSZ in UTC. */
export function fmtDateTime(iso: string | null | undefined): string {
  const d = valid(iso);
  return d ? `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 19)}Z` : "–";
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "–";
  const s = Math.abs(seconds);
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${fmtNum(s / 60, 1)} min`;
  if (s < 86400) return `${fmtNum(s / 3600, 1)} h`;
  return `${fmtNum(s / 86400, 1)} days`;
}

export function fmtAgo(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 120 ? `${s}s` : `${Math.round(s / 60)} min`;
}

/** The exponent for "2^n candidate subsets", taken from the API's search_space_log2 and never hard-coded. */
export function searchSpaceExponent(log2: number): string {
  if (!Number.isFinite(log2)) return "?";
  return Number.isInteger(log2) ? String(log2) : log2.toFixed(1);
}

export function domainOfUrl(u: string): string {
  try { return new URL(u).hostname; } catch { return u.replace(/^[a-z]+:\/\//i, "").split(/[/?#]/)[0]; }
}

export function sentence(s: string): string {
  const t = s.replace(/_/g, " ").trim();
  return t ? t[0].toUpperCase() + t.slice(1) : t;
}
