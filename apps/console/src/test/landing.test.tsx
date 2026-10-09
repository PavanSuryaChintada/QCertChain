import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { KeyGate } from "../layout/KeyGate";
import { getKey, setKey } from "../lib/auth";
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

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (u, init) => {
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
