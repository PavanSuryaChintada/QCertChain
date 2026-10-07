import type { Severity, SysStatus } from "../lib/status";
import { SEVERITY_LABEL, SYS_LABEL } from "../lib/status";

/** Shape per severity, so status never depends on colour alone. */
export const SEVERITY_SHAPE: Record<Severity, "filled" | "outline" | "diamond" | "diamond-outline"> = {
  confirmed: "filled",
  candidate: "outline",
  benign: "diamond",
  unknown: "diamond-outline",
};

function Square({ shape, size = 6 }: { shape: string; size?: number }) {
  const s = size;
  const inner = s - 1;
  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden="true" data-shape={shape} style={{ flex: "none", overflow: "visible" }}>
      {shape === "filled" && <rect x={0} y={0} width={s} height={s} fill="currentColor" />}
      {shape === "outline" && <rect x={0.5} y={0.5} width={inner} height={inner} fill="none" stroke="currentColor" strokeWidth={1} />}
      {shape === "diamond" && <rect x={0.9} y={0.9} width={s - 1.8} height={s - 1.8} fill="currentColor" transform={`rotate(45 ${s / 2} ${s / 2})`} />}
      {shape === "diamond-outline" && (
        <rect x={1.2} y={1.2} width={s - 2.4} height={s - 2.4} fill="none" stroke="currentColor" strokeWidth={1} transform={`rotate(45 ${s / 2} ${s / 2})`} />
      )}
      {shape === "half" && (
        <>
          <rect x={0.5} y={0.5} width={inner} height={inner} fill="none" stroke="currentColor" strokeWidth={1} />
          <rect x={0} y={0} width={s / 2} height={s} fill="currentColor" />
        </>
      )}
      {shape === "cross" && (
        <>
          <rect x={0.5} y={0.5} width={inner} height={inner} fill="none" stroke="currentColor" strokeWidth={1} />
          <line x1={0.5} y1={s - 0.5} x2={s - 0.5} y2={0.5} stroke="currentColor" strokeWidth={1} />
        </>
      )}
    </svg>
  );
}

/** Threat status: a 6px square and a text label, in the severity colour. Never a pill. */
export function StatusIndicator({ severity, label }: { severity: Severity; label?: string }) {
  const text = label ?? SEVERITY_LABEL[severity];
  return (
    <span className={`si sev-${severity}`} data-severity={severity}>
      <Square shape={SEVERITY_SHAPE[severity]} />
      <span>{text}</span>
    </span>
  );
}

/** The 3px left bar of a row's threat status. Its cell must be `position: relative` (class has-bar). */
export function RowBar({ severity }: { severity: Severity }) {
  return <span className={`row-bar sev-${severity}`} aria-hidden="true" style={{ background: "currentColor" }} data-severity={severity} />;
}

export const SYS_SHAPE: Record<SysStatus, string> = { ok: "filled", degraded: "half", failed: "cross", none: "outline" };

/** System status: quiet. Failed is grey, never red. */
export function SystemIndicator({ status, label, size = 8 }: { status: SysStatus; label?: string; size?: number }) {
  return (
    <span className={`si sys-${status}`} data-status={status}>
      <Square shape={SYS_SHAPE[status]} size={size} />
      <span>{label ?? SYS_LABEL[status]}</span>
    </span>
  );
}
