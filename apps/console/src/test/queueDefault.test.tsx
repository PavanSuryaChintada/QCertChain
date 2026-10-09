import { fireEvent, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { HELP } from "../help/content";
import { ARCH_NODES } from "../views/Architecture";
import { LiveQueuePage } from "../views/LiveQueue";
import { json, renderWith } from "./fixtures";

afterEach(() => vi.restoreAllMocks());

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/candidates/counts")) return json({ all: 10, candidate: 6, confirmed: 4, dismissed: 0, unreachable: 0 });
    if (u.includes("/candidates")) return json({ items: [], limit: 200, next_cursor: null });
    return json({}, 404);
  });
}
const candidateCalls = (f: ReturnType<typeof mockApi>) =>
  f.mock.calls.map(([u]) => String(u)).filter((u) => /\/candidates\?/.test(u));

it("the live queue opens on confirmed domains (owner decision 2026-10-09)", async () => {
  const f = mockApi();
  renderWith(<LiveQueuePage />, { route: "/queue" });
  await waitFor(() => expect(candidateCalls(f).some((u) => u.includes("status=confirmed"))).toBe(true));
  expect(screen.getByRole("radio", { name: /Confirmed/ })).toHaveAttribute("aria-checked", "true");
});

it("clicking All from the default selects All (it is written to the address, not dropped)", async () => {
  mockApi();
  renderWith(<LiveQueuePage />, { route: "/queue" });
  fireEvent.click(screen.getByRole("radio", { name: /^All/ }));
  await waitFor(() => expect(screen.getByRole("radio", { name: /^All/ })).toHaveAttribute("aria-checked", "true"));
});

it("All is still one click away, in the address, and lists every row", async () => {
  const f = mockApi();
  renderWith(<LiveQueuePage />, { route: "/queue?status=all" });
  await waitFor(() => expect(candidateCalls(f).length).toBeGreaterThan(0));
  expect(candidateCalls(f).every((u) => !u.includes("status="))).toBe(true);
  expect(screen.getByRole("radio", { name: /^All/ })).toHaveAttribute("aria-checked", "true");
});

it("links into the live candidates ask for All, since the queue opens on Confirmed", () => {
  const to = Object.fromEntries(ARCH_NODES.map((n) => [n.id, n.to]));
  expect(to.ct).toBe("/queue?status=all");
  expect(to.triage).toBe("/queue?status=all");
  expect(readFileSync(resolve(__dirname, "../views/EmailAnalyzer.tsx"), "utf8")).toContain("/queue?status=all&domain=");
  expect(HELP["/queue"].what).toMatch(/opens on confirmed/i);
});

it("the live queue shows the organisation's own sector first; All sectors is one choice away", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/status")) return json({ org: { slug: "shop", name: "ShopSafe SOC", category: "ecommerce" }, key_kind: "org" });
    if (u.includes("/candidates/counts")) return json({ all: 10, candidate: 6, confirmed: 4, dismissed: 0, unreachable: 0 });
    if (u.includes("/candidates")) return json({ items: [], limit: 200, next_cursor: null });
    return json({}, 404);
  });
  renderWith(<LiveQueuePage />, { route: "/queue?status=all" });
  await waitFor(() => expect(candidateCalls(f).some((u) => u.includes("sector=ecommerce"))).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: /^Sector/ }));
  fireEvent.click(await screen.findByRole("option", { name: "All sectors" }));
  // the all-sectors list was fetched before the organisation's sector was known: it is shown from cache
  await waitFor(() => expect(screen.getByRole("button", { name: /^Sector/ })).toHaveTextContent("All sectors"));
  expect(candidateCalls(f).some((u) => !u.includes("sector="))).toBe(true);
});
