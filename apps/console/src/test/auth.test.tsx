import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { apiFetch } from "../lib/api";
import { KEY_HEADER, getKey, setKey } from "../lib/auth";
import { parseSse } from "../lib/sse";
import { KeyGate } from "../layout/KeyGate";
import { MemoryRouter } from "react-router-dom";

afterEach(() => {
  setKey(null);
  vi.restoreAllMocks();
});

it("sends the API key on every request", async () => {
  setKey("qcc_org_test");
  const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
  await apiFetch("/campaigns");
  const headers = f.mock.calls[0][1]!.headers as Record<string, string>;
  expect(headers[KEY_HEADER]).toBe("qcc_org_test");
});

it("a 401 drops the key so the sign-in gate shows", async () => {
  setKey("qcc_org_revoked");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));
  await apiFetch("/campaigns");
  expect(getKey()).toBeNull();
});

it("one 401 while the database is struggling does not sign you out: the key is re-checked first", async () => {
  setKey("qcc_org_valid");
  const f = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response("{}", { status: 401 })) // the stray rejection
    .mockResolvedValueOnce(new Response("{}", { status: 200 })); // the re-check: the key is fine
  await apiFetch("/campaigns");
  expect(getKey()).toBe("qcc_org_valid");
  expect(String(f.mock.calls[1][0])).toContain("/status");
  expect((f.mock.calls[1][1]!.headers as Record<string, string>)[KEY_HEADER]).toBe("qcc_org_valid");
});

it("a re-check that cannot reach the API keeps the key (an outage is not a bad key)", async () => {
  setKey("qcc_org_valid");
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response("{}", { status: 401 }))
    .mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await apiFetch("/campaigns");
  expect(getKey()).toBe("qcc_org_valid");
});

it("renders nothing of the console without a key, then the console once signed in", async () => {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.queryByText("console body")).toBeNull();
  fireEvent.change(screen.getByLabelText("API key"), { target: { value: "qcc_org_abc" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("console body")).toBeInTheDocument();
});

it("parses server-sent events split across chunks", () => {
  const a = parseSse('event: cert\ndata: {"name":"a.top"}\n\nevent: heart');
  expect(a.events).toEqual([{ event: "cert", data: '{"name":"a.top"}' }]);
  const b = parseSse(a.rest + 'beat\ndata: {}\n\n');
  expect(b.events).toEqual([{ event: "heartbeat", data: "{}" }]);
  expect(b.rest).toBe("");
});
