import { apiFetch } from "./api";
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

/** Parse a text/event-stream body into events. Exported for tests. */
export function parseSse(chunk: string): { rest: string; events: { event: string; data: string }[] } {
  const events: { event: string; data: string }[] = [];
  const blocks = chunk.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  for (const b of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of b.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length) events.push({ event, data: data.join("\n") });
  }
  return { rest, events };
}

/** The live feed over fetch (EventSource cannot send the API key header). Reconnects with backoff. */
export function createThrottledStream(path: string, onLines: (lines: LiveCert[]) => void): () => void {
  const t = throttleBuffer<LiveCert>(onLines, { maxPerSec: 20, cap: 200, keep: (x) => x.is_candidate });
  const ctrl = new AbortController();
  let stopped = false;
  (async () => {
    let delay = 1000;
    while (!stopped) {
      try {
        const r = await apiFetch(path, { signal: ctrl.signal, headers: { accept: "text/event-stream" } });
        if (!r.ok || !r.body) throw new Error(String(r.status));
        delay = 1000;
        const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          const parsed = parseSse(buf + value);
          buf = parsed.rest;
          for (const ev of parsed.events) {
            if (ev.event !== "cert") continue;
            try {
              t.push(JSON.parse(ev.data));
            } catch {
              /* a malformed event is skipped, never fatal */
            }
          }
        }
      } catch {
        if (stopped) return;
      }
      await new Promise((res) => setTimeout(res, delay));
      delay = Math.min(delay * 2, 15000);
    }
  })();
  return () => {
    stopped = true;
    ctrl.abort();
    t.stop();
  };
}
