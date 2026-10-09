import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type TriageReasons } from "../lib/api";
import { fmtNum } from "../lib/format";

export const FEATURE_TEXT: Record<string, string> = {
  brand_token_exact: "Brand name in the domain",
  lookalike: "Spelled like a brand",
  homoglyph_hit: "Look-alike characters",
  tld_risk: "High-risk top-level domain",
  keyword_count: "Phishing keywords",
  shape: "Long or hyphen-heavy name",
  allowlisted: "On the allowlist",
  public_suffix: "A public suffix",
  cap: "Capped at 1.0",
};
export const featureText = (f: string) => FEATURE_TEXT[f] ?? f.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === true) return "";
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k.replace(/_/g, " ")} ${String(x)}`).join(", ");
  return String(v);
}

export function ReasonsTable({ reasons }: { reasons: TriageReasons }) {
  return (
    <table className="kv">
      <tbody>
        {reasons.reasons.map((r, i) => (
          <tr key={i}>
            <th scope="row">{featureText(r.feature)}{fmtValue(r.value) && <span className="mono ink-3"> {fmtValue(r.value)}</span>}</th>
            <td className="mono" style={{ textAlign: "right" }}>{r.contribution >= 0 ? "+" : ""}{fmtNum(r.contribution, 2)}</td>
          </tr>
        ))}
        <tr>
          <th scope="row">Score / threshold</th>
          <td className="mono" style={{ textAlign: "right" }}>{fmtNum(reasons.score, 2)} / {fmtNum(reasons.threshold, 2)}</td>
        </tr>
      </tbody>
    </table>
  );
}

function popoverPos(el: HTMLElement | null): React.CSSProperties {
  if (!el) return { position: "fixed", top: 0, right: 0 };
  const r = el.getBoundingClientRect();
  const below = r.bottom + 240 < window.innerHeight;
  return { position: "fixed", right: Math.max(8, window.innerWidth - r.right), ...(below ? { top: r.bottom + 4 } : { bottom: window.innerHeight - r.top + 4 }) };
}

/** The triage score, with its signal-by-signal breakdown on hover or keyboard focus. */
export function ScoreBreakdown({ score, reasons: given, domainId }: { score: number | null; reasons: TriageReasons | null | undefined; domainId?: number }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const anchor = useRef<HTMLButtonElement>(null);
  // The list endpoint may omit triage_reasons; then the breakdown is fetched on demand (one cached request per row).
  const lazy = useQuery({ queryKey: ["domain", domainId], queryFn: () => api.domain(domainId!), staleTime: 60_000,
                          enabled: open && !given && domainId !== undefined });
  const reasons = given ?? lazy.data?.triage ?? null;
  if (!given && domainId === undefined) return <span className="mono">{fmtNum(score, 2)}</span>;
  return (
    <span data-tour="score" style={{ position: "relative", display: "inline-block" }}
          onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        ref={anchor}
        type="button"
        className="hash"
        style={{ cursor: "help" }}
        aria-describedby={open ? id : undefined}
        aria-label={`Triage score ${fmtNum(score, 2)}, show breakdown`}
        title="Hover or focus for the breakdown"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); setOpen(false); } }}
      >
        {fmtNum(score, 2)}
      </button>
      {open && createPortal(
        // Portalled with fixed positioning: table cells clip overflow, so an in-cell popover would be cut off.
        <div id={id} role="tooltip" className="popover overlay t-body" style={popoverPos(anchor.current)}>
          <p className="t-label" style={{ marginBottom: 8 }}>Score breakdown{reasons && ` (${reasons.provenance === "rules" ? "hand-set rule weights" : "trained model"})`}</p>
          {reasons ? <ReasonsTable reasons={reasons} />
            : lazy.isError ? <p className="t-meta">The breakdown could not be loaded. Open the row for its detail.</p>
            : <p className="t-meta">Loading the breakdown</p>}
        </div>,
        document.body,
      )}
    </span>
  );
}
