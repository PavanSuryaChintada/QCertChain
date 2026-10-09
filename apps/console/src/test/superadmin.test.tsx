import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { KeyGate } from "../layout/KeyGate";
import { getKey, setKey } from "../lib/auth";
import { json } from "./fixtures";

const ORGS = [
  { slug: "org1", name: "Bank One SOC", category: "banking", active: true, created_at: null, live_keys: 3 },
  { slug: "telco-watch", name: "Telco Watch", category: "telecom", active: true, created_at: "2026-10-09T12:00:00Z", live_keys: 2 },
];

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (u, init) => {
    const url = String(u);
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    if (url.endsWith("/superadmin/orgs") && method === "POST")
      return json({ slug: "shopsafe-soc", name: "ShopSafe SOC", category: "ecommerce", org_key: "qcc_org_new", demo_key: "qcc_demo_new" }, 201);
    if (url.endsWith("/superadmin/orgs")) return json(ORGS);
    if (url.endsWith("/superadmin/orgs/telco-watch/keys")) return json({ org_key: "qcc_org_telco", demo_key: "qcc_demo_telco" });
    if (url.endsWith("/auth/logout")) return new Response(null, { status: 204 });
    return json({}, 404);
  });
}

function gate() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => setKey("qcc_superadmin_session"));
afterEach(() => { setKey(null); vi.restoreAllMocks(); });

it("a super admin session opens the platform panel, not an organisation's console", async () => {
  mockApi();
  gate();
  expect(await screen.findByText("Telco Watch")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Organisations", level: 1 })).toBeInTheDocument();
  expect(screen.queryByText("console body")).toBeNull();
  expect(screen.getByText("Telecom")).toBeInTheDocument();
});

it("creating an organisation by category shows its two keys", async () => {
  const f = mockApi();
  gate();
  await screen.findByText("Telco Watch");
  fireEvent.change(screen.getByLabelText("Organisation name"), { target: { value: "ShopSafe SOC" } });
  fireEvent.click(screen.getByRole("button", { name: /^Category/ }));
  fireEvent.click(await screen.findByRole("option", { name: "E-commerce" }));
  fireEvent.click(screen.getByRole("button", { name: "Create organisation" }));
  expect(await screen.findByText("qcc_org_new")).toBeInTheDocument();
  expect(screen.getByText("qcc_demo_new")).toBeInTheDocument();
  const post = f.mock.calls.find(([u, i]) => String(u).endsWith("/superadmin/orgs") && (i as RequestInit)?.method === "POST")!;
  expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ name: "ShopSafe SOC", category: "ecommerce" });
});

it("Open console as this organisation switches to its organisation key", async () => {
  mockApi();
  gate();
  fireEvent.click(await screen.findByRole("button", { name: "Open console as Telco Watch" }));
  await waitFor(() => expect(getKey()).toBe("qcc_org_telco"));
});

it("Sign out ends the session on the server too", async () => {
  const f = mockApi();
  gate();
  await screen.findByText("Telco Watch");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() => expect(getKey()).toBeNull());
  expect(f.mock.calls.some(([u, i]) => String(u).endsWith("/auth/logout") && (i as RequestInit)?.method === "POST")).toBe(true);
});
