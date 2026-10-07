import { useEffect, useState } from "react";
import { keepPreviousData, useQuery, type QueryKey } from "@tanstack/react-query";
import { ApiError, toApiError } from "./api";

/**
 * Every view's state is exactly one of these. A view renders by switching on `kind`, so an error panel and an
 * empty message can never be on screen together. A failed poll over good data stays `data`, with `staleSince`
 * set to when that data was fetched and `error` saying why the refresh failed.
 */
export type ViewState<T> =
  | { kind: "loading" }
  | { kind: "error"; error: ApiError }
  | { kind: "empty" }
  | { kind: "data"; data: T; staleSince: number | null; error: ApiError | null };

export interface QuerySnapshot<T> {
  data: T | undefined;
  error: unknown;
  dataUpdatedAt: number;
  errorUpdatedAt: number;
}

export function deriveViewState<T>(q: QuerySnapshot<T>, isEmpty: (d: T) => boolean = defaultIsEmpty): ViewState<T> {
  const err = q.error ? toApiError(q.error) : null;
  if (q.data === undefined) return err ? { kind: "error", error: err } : { kind: "loading" };
  if (isEmpty(q.data)) return { kind: "empty" };
  const stale = err !== null && q.errorUpdatedAt >= q.dataUpdatedAt;
  return { kind: "data", data: q.data, staleSince: stale ? q.dataUpdatedAt : null, error: stale ? err : null };
}

export function defaultIsEmpty(d: unknown): boolean {
  if (Array.isArray(d)) return d.length === 0;
  if (d && typeof d === "object" && Array.isArray((d as { items?: unknown }).items)) return (d as { items: unknown[] }).items.length === 0;
  return false;
}

/** Errors that a retry cannot fix. */
function permanent(e: unknown): boolean {
  return e instanceof ApiError && [400, 401, 403, 404, 405, 409, 422, 429].includes(e.status);
}

export const POLL_MS = 5000;

export interface LiveQueryOptions<T> {
  queryKey: QueryKey;
  queryFn: (signal: AbortSignal) => Promise<T>;
  /** Poll interval in ms, or false for fetch-once. Polling pauses while the tab is hidden. */
  poll?: number | false;
  isEmpty?: (d: T) => boolean;
  enabled?: boolean;
  keepPrevious?: boolean;
  staleTime?: number;
  retry?: number;
  /**
   * Hand TanStack's AbortSignal to fetch. Off by default: when the signal is consumed, TanStack aborts the request
   * as soon as the last observer unmounts (React StrictMode does this on every dev mount) and then fires a duplicate.
   * The browser drops the first request but the server still computes it, so a heavy call (evidence verify, ~5 s)
   * runs twice and queues everything behind it. Unconsumed, a remount reuses the in-flight promise. Explicit,
   * user-started runs (verify, tamper, benchmark) use their own AbortController.
   */
  abortable?: boolean;
}

const NEVER = new AbortController().signal;

/** TanStack Query with stale-while-revalidate, a 429-aware back-off, and one view-state union. */
export function useLiveQuery<T>(o: LiveQueryOptions<T>) {
  const poll = o.poll ?? false;
  const q = useQuery<T, Error>({
    queryKey: o.queryKey,
    queryFn: o.abortable ? ({ signal }) => o.queryFn(signal) : () => o.queryFn(NEVER),
    enabled: o.enabled ?? true,
    staleTime: o.staleTime ?? 2000,
    placeholderData: o.keepPrevious ? keepPreviousData : undefined,
    retry: (n, e) => !permanent(e) && n < (o.retry ?? 1),
    retryDelay: (n) => Math.min(1000 * 2 ** n, 8000),
    refetchIntervalInBackground: false,
    refetchInterval: (query) => {
      if (poll === false) return false;
      const e = query.state.error;
      if (e instanceof ApiError && e.status === 429) return Math.max(1000, (e.retryAfter ?? 30) * 1000);
      if (e instanceof ApiError && (e.status === 401 || e.status === 404)) return false;
      return poll;
    },
  });
  const state = deriveViewState<T>(
    { data: q.data, error: q.error, dataUpdatedAt: q.dataUpdatedAt, errorUpdatedAt: q.errorUpdatedAt },
    o.isEmpty,
  );
  return { state, data: q.data, staleSince: state.kind === "data" ? state.staleSince : null, query: q };
}

/** A clock for "N seconds ago" copy. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
