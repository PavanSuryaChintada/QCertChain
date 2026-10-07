import { api, type ComponentKey, type ComponentStatus, type DomainStatus, type EmailVerdict, type SystemStatus } from "./api";
import { POLL_MS, useLiveQuery } from "./viewState";

/** The ONE batched poll shared by the top bar, the rail, the architecture page and system health. */
export function useStatus() {
  return useLiveQuery<SystemStatus>({ queryKey: ["status"], queryFn: api.status, poll: POLL_MS, isEmpty: () => false });
}

export type Severity = "confirmed" | "candidate" | "benign" | "unknown";
/** "none" is the absence of a report, drawn hollow and grey. */
export type SysStatus = ComponentStatus | "none";

export const SEVERITY_LABEL: Record<Severity, string> = {
  confirmed: "Confirmed",
  candidate: "Suspicious - not verified",
  benign: "Benign",
  unknown: "Unknown",
};

export function domainSeverity(s: DomainStatus): { severity: Severity; label: string } {
  switch (s) {
    case "confirmed": return { severity: "confirmed", label: "Confirmed" };
    case "dismissed": return { severity: "benign", label: "Dismissed" };
    case "unreachable": return { severity: "unknown", label: "Unreachable" };
    default: return { severity: "candidate", label: SEVERITY_LABEL.candidate };
  }
}

export function emailSeverity(v: EmailVerdict): { severity: Severity; label: string } {
  switch (v) {
    case "malicious": return { severity: "confirmed", label: "Malicious" };
    case "clean": return { severity: "benign", label: "Clean" };
    default: return { severity: "candidate", label: SEVERITY_LABEL.candidate };
  }
}

export const SYS_LABEL: Record<SysStatus, string> = { ok: "Ok", degraded: "Degraded", failed: "Failed", none: "No data" };

export function worstStatus(s: SystemStatus | undefined): SysStatus {
  if (!s) return "none";
  const all = Object.values(s.components).map((c) => c?.status);
  if (all.includes("failed")) return "failed";
  if (all.includes("degraded")) return "degraded";
  return all.length ? "ok" : "none";
}

export function componentStatus(s: SystemStatus | undefined, key: ComponentKey): SysStatus {
  return s?.components[key]?.status ?? "none";
}
