import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { type LiveCert, createThrottledStream } from "../lib/sse";
import { StreamLine } from "../components/StreamLine";

// The signature element (DESIGN.md §1): a live monospace ticker. Never collapsible.
export function StreamRail() {
  const [lines, setLines] = useState<(LiveCert & { key: number })[]>([]);
  const navigate = useNavigate();
  useEffect(() => {
    let n = 0;
    const close = createThrottledStream("/certs/live", (batch) => {
      setLines((prev) => [...batch.map((b) => ({ ...b, key: n++ })).reverse(), ...prev].slice(0, 200));
    });
    return close;
  }, []);
  return (
    <aside className="stream rule-l flex flex-col" aria-label="Certificate stream">
      <div className="rule-b px-3 py-2 eyebrow">Certificate stream</div>
      <ol className="flex-1 overflow-hidden px-3 py-1" aria-live="off">
        {lines.length === 0 && (
          <li className="secondary py-2">Waiting for certificates. If this stays empty, check the mode indicator above.</li>
        )}
        {lines.map((l) => (
          <StreamLine key={l.key} cert={l} onOpen={l.domain_id ? () => navigate(`/?domain=${l.domain_id}`) : undefined} />
        ))}
      </ol>
    </aside>
  );
}
