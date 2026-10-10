import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { KeyGate } from "../layout/KeyGate";
import { getKey, setKey } from "../lib/auth";
import { CONTRASTS, TIMING_STEPS } from "../explain/landing";
import { CT_TO_CANDIDATE, MEASURED } from "../explain/measured";
import { json } from "./fixtures";

const ORGS = [
  { slug: "org1", name: "Bank One SOC", category: "banking", demo_key: "qcc_demo_bankone" },
  { slug: "org2", name: "Bank Two SOC", category: "banking", demo_key: null },
  { slug: "shopsafe-soc", name: "ShopSafe SOC", category: "ecommerce", demo_key: "qcc_demo_shopsafe" },
];

function home(route = "/") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
}

const FEED = {
  mode: "live", connection: "connected", certs_per_sec: 3100,
  recent: [{ name: "cdn.northwind.com", ts: "2026-10-10T00:00:00Z" }, { name: "mail.fabrikam.io", ts: "2026-10-10T00:00:00Z" }],
  candidates: [{ name: "sbi-k••••••.top", ts: "2026-10-10T00:00:00Z" }],
};

/** `feed`: what /certs/public answers; null = the API is unreachable (the hosted site with the laptop off). */
function mockApi(feed: object | null = null) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (u, init) => {
    if (String(u).endsWith("/certs/public")) {
      return feed ? json(feed) : json({ type: "about:blank", title: "Service Unavailable", status: 503, detail: "down" }, 503);
    }
    if (String(u).endsWith("/auth/superadmin/login")) {
      const body = JSON.parse(String((init as RequestInit).body));
      return body.password === "test1234" ? json({ token: "qcc_superadmin_abc", expires_at: "2026-10-10T00:00:00Z" })
        : json({ type: "about:blank", title: "Unauthorized", status: 401, detail: "Wrong email or password." }, 401);
    }
    return json(ORGS);
  });
}

afterEach(() => { setKey(null); vi.restoreAllMocks(); });

it("signed out, the home page says what the product does, before anything else", () => {
  mockApi();
  home();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/before the first email/i);
  expect(screen.getByRole("list", { name: "The life of a phishing domain" })).toBeInTheDocument();
  expect(screen.queryByText("console body")).toBeNull();
});

it("the sidebar lists every organisation by category, with its read-only key and a one-click sign-in", async () => {
  mockApi();
  home();
  const side = screen.getByRole("complementary", { name: "Try the console" });
  expect(await within(side).findByRole("heading", { name: "E-commerce" })).toBeInTheDocument();
  expect(within(side).getByRole("heading", { name: "Banking" })).toBeInTheDocument();
  expect(within(side).getByText("No read-only key yet")).toBeInTheDocument(); // Bank Two
  fireEvent.click(within(side).getByRole("button", { name: "Sign in to ShopSafe SOC (read-only)" }));
  expect(getKey()).toBe("qcc_demo_shopsafe");
  expect(await screen.findByText("console body")).toBeInTheDocument();
});

it("Sign in accepts the super admin only, and says so when the password is wrong", async () => {
  mockApi();
  home();
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  const form = screen.getByRole("dialog", { name: "Super admin sign-in" });
  fireEvent.change(within(form).getByLabelText("Email"), { target: { value: "super@gmail.com" } });
  fireEvent.change(within(form).getByLabelText("Password"), { target: { value: "wrong" } });
  fireEvent.click(within(form).getByRole("button", { name: "Sign in as super admin" }));
  expect(await within(form).findByText("Wrong email or password.")).toBeInTheDocument();
  expect(getKey()).toBeNull();
  fireEvent.change(within(form).getByLabelText("Password"), { target: { value: "test1234" } });
  fireEvent.click(within(form).getByRole("button", { name: "Sign in as super admin" }));
  await waitFor(() => expect(getKey()).toBe("qcc_superadmin_abc"));
});

it("Request access is a demo form: it sends nothing and says sign-up is by invitation", async () => {
  const f = mockApi();
  home();
  fireEvent.click(screen.getByRole("button", { name: "Request access" }));
  const form = screen.getByRole("dialog", { name: "Request access" });
  fireEvent.change(within(form).getByLabelText("Work email"), { target: { value: "soc@bank.example" } });
  fireEvent.change(within(form).getByLabelText("Organisation"), { target: { value: "Bank Three" } });
  const calls = f.mock.calls.length;
  fireEvent.click(within(form).getByRole("button", { name: "Request access" }));
  expect(await within(form).findByText(/by invitation/i)).toBeInTheDocument();
  expect(within(form).getByText(/nothing was sent or stored/i)).toBeInTheDocument();
  expect(f.mock.calls.length).toBe(calls);
});

it("what is not built yet is only under On the roadmap, and nothing is ever sent automatically", () => {
  mockApi();
  home();
  const roadmap = screen.getByRole("region", { name: "On the roadmap" });
  for (const t of [/Slack/, /Safe Browsing/, /SSO/]) expect(within(roadmap).getByText(t)).toBeInTheDocument();
  const page = document.body.textContent ?? "";
  expect(page).toMatch(/never sent automatically/i);
  expect(page).not.toMatch(/honey/i);
  for (const built of screen.getAllByRole("region").filter((r) => r !== roadmap))
    expect(built.textContent ?? "").not.toMatch(/Slack|Safe Browsing|SmartScreen|PagerDuty|SSO/);
});

it("the pipeline diagram explains why Redis, the workers and the chain are there", () => {
  mockApi();
  home();
  const diagram = screen.getByRole("figure", { name: "How the pipeline works" });
  for (const t of [/Redis/, /workers/i, /Merkle root/, /row-level security/i]) expect(within(diagram).getAllByText(t).length).toBeGreaterThan(0);
});

it("the hero's certificate log is labelled an illustration, and a candidate is never shown as confirmed", () => {
  mockApi();
  home();
  const log = screen.getByRole("figure", { name: /^Illustration:/ });
  expect(within(log).getByText(/fictitious names/i)).toBeInTheDocument();
  const candidate = within(log).getByText("sbi-kyc-verify.example").closest("li")!;
  expect(within(candidate).getByText("candidate")).toHaveClass("ct-chip-candidate");
  expect(within(candidate).queryByText("confirmed")).toBeNull();
});

it("with the feed up, the hero shows real certificates labelled Live, candidates only as the server masked them", async () => {
  mockApi(FEED);
  home();
  const log = await screen.findByRole("figure", { name: /^Live:/ });
  expect(within(log).getByText("cdn.northwind.com")).toBeInTheDocument();
  const cand = within(log).getByText("sbi-k••••••.top").closest("li")!;
  expect(within(cand).getByText("candidate")).toHaveClass("ct-chip-candidate");
  expect(within(cand).getByText("suspicious, not verified")).toBeInTheDocument();
  expect(within(log).getByText(/partly hidden/i)).toBeInTheDocument();
  expect(screen.queryByRole("figure", { name: /^Illustration:/ })).toBeNull();
});

it("a replayed stream is labelled Replay, never Live", async () => {
  mockApi({ ...FEED, mode: "replay" });
  home();
  expect(await screen.findByRole("figure", { name: /^Replay:/ })).toBeInTheDocument();
  expect(screen.queryByRole("figure", { name: /^Live:/ })).toBeNull();
});

it("a dead stream falls back to the labelled illustration", async () => {
  const spy = mockApi({ ...FEED, connection: "down" });
  home();
  await waitFor(() => expect(spy.mock.calls.some(([u]) => String(u).endsWith("/certs/public"))).toBe(true));
  expect(screen.getByRole("figure", { name: /^Illustration:/ })).toBeInTheDocument();
});

it("the home page shows how long each step takes, only as measured (generated from reports/metrics.json)", () => {
  mockApi();
  home();
  const timing = screen.getByRole("region", { name: "How long each step takes" });
  expect(MEASURED.length).toBeGreaterThan(0);
  for (const m of MEASURED) {
    const row = within(timing).getByTestId(`timing-${m.id}`);
    expect(row).toHaveTextContent(TIMING_STEPS[m.id].title);
    expect(within(row).getByText(m.value)).toBeInTheDocument();
    if (m.n) expect(row).toHaveTextContent(`${m.n} ${m.unit}`);
    if (m.p95) expect(row).toHaveTextContent(`95% within ${m.p95}`);
  }
  expect(within(timing).getByTestId("timing-relay")).toHaveTextContent("Outside our code");
  if (CT_TO_CANDIDATE) expect(timing).toHaveTextContent(`${CT_TO_CANDIDATE.relay} of it before the certificate reaches us`);
  // a step without a measurement has no row: nothing is estimated
  for (const id of Object.keys(TIMING_STEPS)) {
    if (!MEASURED.some((m) => m.id === id)) expect(within(timing).queryByTestId(`timing-${id}`)).toBeNull();
  }
});

it("every section says how our approach differs from the usual one, and never races blocklists on speed", () => {
  mockApi();
  home();
  const sections: [string, keyof typeof CONTRASTS][] = [
    ["What your security team gets", "offer"], ["How long each step takes", "timing"], ["How we collect evidence", "evidence"],
    ["Pipeline", "pipeline"], ["After a phishing domain is confirmed", "after"], ["Security and isolation", "security"],
  ];
  for (const [name, id] of sections) {
    const group = within(screen.getByRole("region", { name })).getByRole("group", { name: "The usual approach and QCertChain" });
    expect(group).toHaveTextContent(CONTRASTS[id].usual);
    expect(group).toHaveTextContent(CONTRASTS[id].ours);
  }
  for (const c of Object.values(CONTRASTS)) {
    for (const s of [c.usual, c.ours]) expect(s).not.toMatch(/faster|sooner|quicker|ahead of|before (any |the )?blocklist/i);
  }
});
