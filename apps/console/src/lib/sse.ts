// Live certificate feed. Throttled server-side (~20/s) AND client-side: rendering 3,000/s freezes the browser,
// and nobody can read it (apps/BUILD_SPEC.md §2).
export interface LiveCert {
  ts: string; name: string; etld1: string; score: number; is_candidate: boolean;
  domain_id: number | null; issuer: string | null; source: string;
}

type Options<T> = { maxPerSec: number; cap: number; keep?: (x: T) => boolean };

/** Buffer items and flush at most maxPerSec per second. When the buffer exceeds `cap`, the oldest items are
 *  dropped — except items `keep` protects (candidates), which always get through. */
export function throttleBuffer<T>(onFlush: (items: T[]) => void, { maxPerSec, cap, keep }: Options<T>) {
  let buf: T[] = [];
  const tickMs = 100;
  const perTick = Math.max(1, Math.floor((maxPerSec * tickMs) / 1000));
  const timer = setInterval(() => {
    if (!buf.length) return;
    const out = buf.slice(0, perTick);
    buf = buf.slice(perTick);
    onFlush(out);
  }, tickMs);
  return {
    push(x: T) {
      buf.push(x);
      if (buf.length > cap) {
        const protectedItems = keep ? buf.filter(keep) : [];
        const rest = keep ? buf.filter((y) => !keep(y)) : buf;
        buf = [...protectedItems, ...rest.slice(rest.length - Math.max(0, cap - protectedItems.length))];
      }
    },
    pending: () => buf.length,
    stop: () => clearInterval(timer),
  };
}

export function createThrottledStream(url: string, onLines: (lines: LiveCert[]) => void): () => void {
  const t = throttleBuffer<LiveCert>(onLines, { maxPerSec: 20, cap: 200, keep: (x) => x.is_candidate });
  const es = new EventSource(url);
  es.addEventListener("cert", (ev) => {
    try {
      t.push(JSON.parse((ev as MessageEvent).data));
    } catch {
      /* a malformed event is skipped, never fatal */
    }
  });
  return () => {
    es.close();
    t.stop();
  };
}
