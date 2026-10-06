// The most important component (apps/BUILD_SPEC.md §3). Square + word, always. A candidate is GREY.
type Status = "candidate" | "confirmed" | "dismissed" | "unreachable" | "malicious" | "suspicious" | "clean";

const SPEC: Record<Status, { token: string; word: string }> = {
  candidate: { token: "--v-candidate", word: "CANDIDATE" },
  confirmed: { token: "--v-confirmed", word: "CONFIRMED" },
  dismissed: { token: "--v-dismissed", word: "DISMISSED" },
  unreachable: { token: "--v-unreach", word: "UNREACHABLE" },
  // email verdicts reuse the same vocabulary: suspicious is grey, exactly like a candidate
  malicious: { token: "--v-confirmed", word: "MALICIOUS" },
  suspicious: { token: "--v-candidate", word: "SUSPICIOUS" },
  clean: { token: "--v-dismissed", word: "CLEAN" },
};

export function VerdictChip({ status, strongCount }: { status: Status; strongCount?: number }) {
  // API_CONTRACT §2: a confirmed verdict with fewer than two strong signals is a backend bug — show a candidate.
  const effective: Status = status === "confirmed" && strongCount !== undefined && strongCount < 2 ? "candidate" : status;
  const s = SPEC[effective];
  const ink = effective === "candidate" || effective === "suspicious" ? "var(--ink-200)" : `var(${s.token})`;
  return (
    <span className="inline-flex items-center gap-2" style={{ fontFamily: "var(--font-data)", fontSize: 12 }}>
      <span data-swatch aria-hidden style={{ width: 12, height: 12, display: "inline-block", background: `var(${s.token})` }} />
      <span style={{ color: ink, letterSpacing: "0.04em" }}>{s.word}</span>
    </span>
  );
}
