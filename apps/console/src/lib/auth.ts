// The API key for this browser. Every request sends it in X-API-Key; the server derives the organisation from
// it. Stored per viewer (a convenience, not shared state); falls back to VITE_API_KEY for local development.
const STORAGE = "qcertchain.apiKey";
export const KEY_HEADER = "X-API-Key";

let memory: string | null = null;
const listeners = new Set<() => void>();

export function getKey(): string | null {
  if (memory) return memory;
  try {
    memory = window.localStorage.getItem(STORAGE);
  } catch {
    /* storage blocked: memory only */
  }
  return memory ?? ((import.meta.env.VITE_API_KEY as string | undefined) || null);
}

export function setKey(k: string | null): void {
  memory = k;
  try {
    if (k) window.localStorage.setItem(STORAGE, k);
    else window.localStorage.removeItem(STORAGE);
  } catch {
    /* storage blocked: memory only */
  }
  listeners.forEach((f) => f());
}

export function onKeyChange(f: () => void): () => void {
  listeners.add(f);
  return () => listeners.delete(f);
}

export function authHeaders(): Record<string, string> {
  const k = getKey();
  return k ? { [KEY_HEADER]: k } : {};
}
