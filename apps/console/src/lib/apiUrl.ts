/**
 * Where the API is (spec 2026-10-09 §10). The API runs on a laptop behind a Cloudflare quick tunnel whose URL changes
 * on every start; the laptop publishes the current URL in one Supabase row, which the console reads with the
 * publishable key. Only https://<words>.trycloudflare.com is accepted, so an altered row cannot send visitors' keys
 * elsewhere. Not configured, refused, failed or slow means: keep VITE_API_URL.
 */
export interface Discovery { url: string; key: string }

export const DISCOVERY: Discovery = {
  url: (import.meta.env.VITE_SUPABASE_URL as string | undefined) ?? "",
  key: (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined) ?? "",
};

const ACCEPT = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/;

export async function discoverApiUrl(cfg: Discovery = DISCOVERY, fetchImpl: typeof fetch = fetch, timeoutMs = 3000): Promise<string | null> {
  if (!cfg.url || !cfg.key) return null;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetchImpl(`${cfg.url.replace(/\/$/, "")}/rest/v1/public_endpoints?name=eq.api&select=url`,
                              { headers: { apikey: cfg.key }, signal: ctl.signal });
    if (!r.ok) return null;
    const rows = (await r.json()) as { url?: unknown }[];
    const u = Array.isArray(rows) ? rows[0]?.url : null;
    return typeof u === "string" && ACCEPT.test(u) ? u : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
