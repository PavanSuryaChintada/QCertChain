import { useRef, type KeyboardEvent } from "react";
import { fmtInt } from "../lib/format";

export interface Segment<V extends string> { value: V; label: string; count?: number | null }

/** A radiogroup: one tab stop; arrows (wrapping), Home and End move AND select. Counts sit inside each segment. */
export function SegmentedControl<V extends string>({ label, segments, value, onChange }: {
  label: string;
  segments: Segment<V>[];
  value: V;
  onChange: (v: V) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const idx = Math.max(0, segments.findIndex((s) => s.value === value));
  const go = (i: number) => {
    const n = (i + segments.length) % segments.length;
    onChange(segments[n].value);
    refs.current[n]?.focus();
  };
  const onKey = (e: KeyboardEvent) => {
    switch (e.key) {
      case "ArrowRight": case "ArrowDown": e.preventDefault(); go(idx + 1); break;
      case "ArrowLeft": case "ArrowUp": e.preventDefault(); go(idx - 1); break;
      case "Home": e.preventDefault(); go(0); break;
      case "End": e.preventDefault(); go(segments.length - 1); break;
    }
  };
  return (
    <div className="seg" role="radiogroup" aria-label={label} onKeyDown={onKey}>
      {segments.map((s, i) => (
        <button
          key={s.value}
          ref={(el) => { refs.current[i] = el; }}
          type="button"
          role="radio"
          aria-checked={s.value === value}
          tabIndex={s.value === value ? 0 : -1}
          onClick={() => onChange(s.value)}
        >
          <span>{s.label}</span>
          {s.count !== undefined && <span className="mono" aria-label={`${s.count ?? 0} items`}>{s.count === null ? "–" : fmtInt(s.count)}</span>}
        </button>
      ))}
    </div>
  );
}
