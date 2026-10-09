import { fireEvent, screen, waitFor } from "@testing-library/react";
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
