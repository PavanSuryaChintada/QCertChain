import type { LiveCert } from "../lib/sse";

// 03:02:12  icici-verify-kyc.top   0.87  — a triage hit flares, then settles. A candidate flare is the stream's
// only accent: it marks "look here", and the chip in the detail view still says CANDIDATE (DESIGN §6).
export function StreamLine({ cert, onOpen }: { cert: LiveCert; onOpen?: () => void }) {
  const t = new Date(cert.ts);
  const time = isNaN(t.getTime()) ? "--:--:--" : t.toISOString().slice(11, 19);
  const content = (
    <>
      <span style={{ color: "var(--ink-300)" }}>{time}</span>
      <span className="truncate flex-1" title={cert.name}
            style={{ color: cert.is_candidate ? "var(--ink-000)" : "var(--ink-300)",
                     animation: cert.is_candidate ? "flare 1600ms ease-out" : undefined }}>
        {cert.name}
      </span>
      <span style={{ color: cert.is_candidate ? "var(--ink-100)" : "var(--ink-300)" }}>{cert.score.toFixed(2)}</span>
    </>
  );
  const style = { fontFamily: "var(--font-data)", fontSize: 11, lineHeight: 1.4 } as const;
  return (
    <li className="stream-line">
      {onOpen ? (
        <button onClick={onOpen} className="flex w-full gap-2 text-left"
                style={{ ...style, border: 0, background: "transparent", padding: 0, minHeight: 0, height: "auto" }}>
          {content}
        </button>
      ) : (
        <span className="flex gap-2" style={style}>{content}</span>
      )}
    </li>
  );
}
