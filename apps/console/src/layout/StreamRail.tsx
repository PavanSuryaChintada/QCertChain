import { useEffect, useId, useState } from "react";
import { type LiveCert, createThrottledStream } from "../lib/sse";
import { fmtNum, fmtTime } from "../lib/format";
import { Button } from "../components/Button";

function Line({ c, onOpen }: { c: LiveCert; onOpen?: (id: number) => void }) {
  const cells = (
    <>
      <span className="ink-3">{fmtTime(c.ts)}</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", color: c.is_candidate ? "var(--ink)" : "var(--ink-3)" }} title={c.name}>{c.name}</span>
      <span style={{ textAlign: "right", color: c.is_candidate ? "var(--candidate)" : "var(--ink-3)" }}>{fmtNum(c.score, 2)}</span>
      <span className="ink-3">{c.source === "email" ? "email" : "ct"}</span>
    </>
  );
  const grid = { display: "grid", gridTemplateColumns: "72px minmax(0,1fr) 48px 48px", gap: 12, height: 24, alignItems: "center", width: "100%" } as const;
  return (
    <li className="mono" style={{ fontSize: 12 }}>
      {onOpen && c.domain_id ? (
        <button type="button" onClick={() => onOpen(c.domain_id!)} style={{ ...grid, border: 0, background: "transparent", padding: 0, textAlign: "left", cursor: "pointer" }}
                title={`Open ${c.name}`}>{cells}</button>
      ) : (
        <span style={grid}>{cells}</span>
      )}
    </li>
  );
}

/** The live certificate ticker as a collapsible strip. Throttled to 20 lines/s; candidates are never dropped. */
export function StreamRail({ onOpen, defaultOpen = false }: { onOpen?: (domainId: number) => void; defaultOpen?: boolean }) {
  const [lines, setLines] = useState<(LiveCert & { key: number })[]>([]);
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  useEffect(() => {
    let n = 0;
    return createThrottledStream("/certs/live", (batch) => {
      setLines((prev) => [...batch.map((b) => ({ ...b, key: n++ })).reverse(), ...prev].slice(0, 100));
    });
  }, []);
  const latest = lines[0];
  return (
    <section className="panel" aria-label="Live certificate stream" style={{ marginTop: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, height: 32, padding: "0 12px" }}>
        <Button size="sm" variant="ghost" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
          {open ? "Hide certificate stream" : "Show certificate stream"}
        </Button>
        {!open && (
          <span className="mono t-meta" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
            {latest ? `${fmtTime(latest.ts)}  ${latest.name}  ${fmtNum(latest.score, 2)}` : "Waiting for certificates"}
          </span>
        )}
      </div>
      {open && (
        <ol id={id} aria-live="off" style={{ height: 192, overflow: "hidden", padding: "0 12px 8px", borderTop: "1px solid var(--hairline)" }}>
          {lines.length === 0 && <li className="t-meta" style={{ paddingTop: 8 }}>Waiting for certificates. If this stays empty, check the stream status on System health.</li>}
          {lines.map((l) => <Line key={l.key} c={l} onOpen={onOpen} />)}
        </ol>
      )}
    </section>
  );
}
