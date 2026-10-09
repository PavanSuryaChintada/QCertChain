import { apiFetch, apiUrl, setApiUrl } from "../lib/api";
import { discoverApiUrl } from "../lib/apiUrl";

const CFG = { url: "https://ref.supabase.co", key: "sb_publishable_x" };
const row = (url: string) => new Response(JSON.stringify([{ url }]), { status: 200, headers: { "content-type": "application/json" } });

afterEach(() => { vi.restoreAllMocks(); setApiUrl("http://127.0.0.1:8000"); });

it("uses the URL the laptop published for the quick tunnel", async () => {
  const f = vi.fn().mockResolvedValue(row("https://scenic-css-bedroom-minor.trycloudflare.com"));
  expect(await discoverApiUrl(CFG, f)).toBe("https://scenic-css-bedroom-minor.trycloudflare.com");
  const [url, init] = f.mock.calls[0];
  expect(url).toBe("https://ref.supabase.co/rest/v1/public_endpoints?name=eq.api&select=url");
  expect((init as RequestInit).headers).toEqual({ apikey: "sb_publishable_x" });
});

it("refuses anything that is not a trycloudflare URL, so an altered row cannot send keys elsewhere", async () => {
  for (const u of ["https://evil.example", "http://abc.trycloudflare.com", "https://abc.trycloudflare.com.evil.example", "https://abc.trycloudflare.com/x"])
    expect(await discoverApiUrl(CFG, vi.fn().mockResolvedValue(row(u)))).toBeNull();
});

it("falls back when the lookup is not configured, fails or is slow", async () => {
  expect(await discoverApiUrl({ url: "", key: "" }, vi.fn())).toBeNull();
  expect(await discoverApiUrl(CFG, vi.fn().mockRejectedValue(new TypeError("offline")))).toBeNull();
  const never = vi.fn((_u: string, init?: RequestInit) => new Promise<Response>((_, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }));
  expect(await discoverApiUrl(CFG, never, 50)).toBeNull();
});

it("a request that cannot reach the API re-reads the published URL once and retries there", async () => {
  setApiUrl("https://old-tunnel.trycloudflare.com");
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (u) => {
    const url = String(u);
    if (url.startsWith("https://old-tunnel")) throw new TypeError("Failed to fetch");
    if (url.includes("/rest/v1/public_endpoints")) return row("https://new-tunnel.trycloudflare.com");
    return new Response("{}", { status: 200 });
  });
  const r = await apiFetch("/campaigns", undefined, CFG);
  expect(r.status).toBe(200);
  expect(apiUrl()).toBe("https://new-tunnel.trycloudflare.com");
  expect(f.mock.calls.map(([u]) => String(u))).toEqual([
    "https://old-tunnel.trycloudflare.com/campaigns",
    "https://ref.supabase.co/rest/v1/public_endpoints?name=eq.api&select=url",
    "https://new-tunnel.trycloudflare.com/campaigns",
  ]);
});
