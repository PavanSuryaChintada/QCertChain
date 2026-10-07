import { useEffect, useState, type ReactNode } from "react";
import { API_URL, ApiError } from "../lib/api";
import { fmtAgo } from "../lib/format";
import { type ViewState, useNow } from "../lib/viewState";
import { Button } from "./Button";

/** What failed and what to do, in grey. Red means a confirmed threat and nothing else. */
export function errorCopy(e: ApiError, what: string): string {
  switch (e.status) {
    case 0: return `Could not reach the API at ${API_URL} while loading ${what}. Check that the API is running and reachable, then retry.`;
    case 401: return "Your API key was rejected. Sign in again with a valid key.";
    case 403: case 405: return "The demo key is read-only. Sign in with an organisation key to do this.";
    case 404: return `${what[0].toUpperCase()}${what.slice(1)} was not found for your organisation. Check the link, or open it from its list.`;
    case 429: return `Rate limit reached, retrying in ${e.retryAfter ?? 30}s.`;
    case 503: return `The service behind ${what} is unavailable right now${e.problem.detail ? ` (${e.problem.detail})` : ""}. It retries automatically; see System health for details.`;
    default:
      return e.status >= 500
        ? `The API failed while loading ${what} (HTTP ${e.status}). Retry in a moment; if it keeps failing, check the ops log.`
        : `The request for ${what} was refused (HTTP ${e.status}${e.problem.detail ? `: ${e.problem.detail}` : ""}).`;
  }
}

export function ErrorState({ error, what, onRetry }: { error: ApiError; what: string; onRetry?: () => void }) {
  return (
    <div className="state-box" role="alert" data-state="error">
      <p className="prose">{errorCopy(error, what)}</p>
      {onRetry && error.status !== 429 && error.status !== 401 && (
        <div style={{ marginTop: 12 }}><Button size="sm" onClick={onRetry}>Retry</Button></div>
      )}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="state-box" data-state="empty"><p className="prose">{children}</p></div>;
}

/** A thin bar over data kept on screen after a refresh failed. */
export function StaleBar({ since, error, what }: { since: number; error: ApiError | null; what: string }) {
  const now = useNow();
  const why = error?.status === 429 ? `Rate limit reached, retrying in ${error.retryAfter ?? 30}s.` : "The last refresh failed; retrying.";
  return (
    <div className="stale-bar" role="status" data-testid="stale-bar">
      <span>Showing {what} from {fmtAgo(now - since)} ago.</span>
      <span>{why}</span>
    </div>
  );
}

/** Skeleton rows matching the table geometry exactly. Static (no shimmer), and skipped if data lands within 200ms. */
export function SkeletonRows({ columns, rows = 10, density = "default", delayMs = 200 }: {
  columns: (number | string | undefined)[];
  rows?: number;
  density?: "default" | "compact";
  delayMs?: number;
}) {
  const [show, setShow] = useState(delayMs === 0);
  useEffect(() => {
    if (delayMs === 0) return;
    const t = setTimeout(() => setShow(true), delayMs);
    return () => clearTimeout(t);
  }, [delayMs]);
  if (!show) return null;
  return (
    <div className="panel" aria-busy="true" aria-label="Loading" data-state="loading">
      <table className={`tbl${density === "compact" ? " compact" : ""}`}>
        <colgroup>{columns.map((w, i) => <col key={i} style={{ width: w }} />)}</colgroup>
        <thead><tr>{columns.map((_, i) => <th key={i}><span className="skel" style={{ width: 48 }} /></th>)}</tr></thead>
        <tbody>
          {Array.from({ length: rows }, (_, r) => (
            <tr key={r}>{columns.map((_, i) => <td key={i}><span className="skel" style={{ width: `${48 + ((r * 7 + i * 13) % 4) * 12}%` }} /></td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Renders exactly one of the four states. */
export function ViewStateView<T>({ state, what, skeleton, empty, onRetry, children }: {
  state: ViewState<T>;
  what: string;
  skeleton: ReactNode;
  empty: ReactNode;
  onRetry?: () => void;
  children: (data: T) => ReactNode;
}) {
  switch (state.kind) {
    case "loading": return <>{skeleton}</>;
    case "error": return <ErrorState error={state.error} what={what} onRetry={onRetry} />;
    case "empty": return <EmptyState>{empty}</EmptyState>;
    case "data":
      return (
        <>
          {state.staleSince !== null && <StaleBar since={state.staleSince} error={state.error} what={what} />}
          {children(state.data)}
        </>
      );
  }
}
