import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { KeyGate } from "../layout/KeyGate";
import { getKey, setKey } from "../lib/auth";
import { json } from "./fixtures";

const ORGS = [
  { slug: "org1", name: "Bank One SOC", category: "banking", demo_key: "qcc_demo_bankone" },
  { slug: "org2", name: "Bank Two SOC", category: "banking", demo_key: null },
  { slug: "shopsafe-soc", name: "ShopSafe SOC", category: "ecommerce", demo_key: "qcc_demo_shopsafe" },
];

function gate() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => { setKey(null); vi.restoreAllMocks(); });

it("the Organisations tab lists every organisation by category, with its read-only key and a one-click sign-in", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(json(ORGS));
  gate();
  expect(await screen.findByRole("heading", { name: "E-commerce" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Banking" })).toBeInTheDocument();
  expect(screen.getByText("ShopSafe SOC")).toBeInTheDocument();
  expect(screen.getByText("No read-only key yet")).toBeInTheDocument(); // Bank Two
  fireEvent.click(screen.getByRole("button", { name: "Sign in to ShopSafe SOC (read-only)" }));
  expect(getKey()).toBe("qcc_demo_shopsafe");
  expect(await screen.findByText("console body")).toBeInTheDocument();
});

it("the Super admin tab signs in with email and password and keeps the session key", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (u, init) => {
    if (String(u).endsWith("/auth/superadmin/login")) {
      const body = JSON.parse(String((init as RequestInit).body));
      return body.password === "test1234" ? json({ token: "qcc_superadmin_abc", expires_at: "2026-10-10T00:00:00Z" })
        : json({ type: "about:blank", title: "Unauthorized", status: 401, detail: "Wrong email or password." }, 401);
    }
    return json(ORGS);
  });
  gate();
  fireEvent.click(screen.getByRole("tab", { name: "Super admin" }));
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "super@gmail.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in as super admin" }));
  expect(await screen.findByText("Wrong email or password.")).toBeInTheDocument();
  expect(getKey()).toBeNull();
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test1234" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in as super admin" }));
  await waitFor(() => expect(getKey()).toBe("qcc_superadmin_abc"));
  expect(f.mock.calls.some(([u]) => String(u).endsWith("/auth/superadmin/login"))).toBe(true);
});
