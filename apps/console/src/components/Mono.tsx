// Domain names and numerals are ALWAYS monospace: rn/m, 1/l and 0/O are the attack (DESIGN.md §4).
export function DomainName({ name, title }: { name: string; title?: string }) {
  return (
    <span className="mono block truncate" title={title ?? name} style={{ fontSize: 13, color: "var(--ink-000)" }}>
      {name}
    </span>
  );
}

export function Num({ v, digits = 0, suffix = "" }: { v: number | null | undefined; digits?: number; suffix?: string }) {
  if (v === null || v === undefined) return <span className="num">—</span>;
  return <span className="num">{v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })}{suffix}</span>;
}

export function Hash({ v, n = 12 }: { v: string | null | undefined; n?: number }) {
  if (!v) return <span className="mono">—</span>;
  return <span className="mono" title={v} style={{ fontSize: 12 }}>{v.length > n ? `${v.slice(0, n)}…` : v}</span>;
}
