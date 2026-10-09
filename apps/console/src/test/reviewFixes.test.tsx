// The deferred minors of the Plan 1 review (docs/AI_USAGE_LOG.md), fixed 2026-10-10 at the owner's request.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";
import { KeyGate } from "../layout/KeyGate";
import type { Campaign, DomainDetail, Page } from "../lib/api";
import { getKey, setKey } from "../lib/auth";
import { STEPS, type TourReads } from "../tour/steps";
import { TourOverlay } from "../tour/TourOverlay";
import { TourProvider, useTour } from "../tour/TourProvider";
import { TourStartPage } from "../tour/TourStart";
import { LedgerPage } from "../views/Ledger";
import { GRAPH, SWEEP, json } from "./fixtures";

const reads = (): TourReads => ({
  campaigns: vi.fn().mockResolvedValue({ items: [] as Campaign[], limit: 50, next_cursor: null } as Page<Campaign>),
  graph: vi.fn().mockResolvedValue(GRAPH),
  sweep: vi.fn().mockResolvedValue(SWEEP),
  domain: vi.fn().mockResolvedValue({ evidence_bundle_id: null } as DomainDetail),
});
const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

afterEach(() => { window.sessionStorage.clear(); setKey(null); vi.restoreAllMocks(); });

it("browser Back from the tour's first step leaves the tour page instead of starting the tour again", async () => {
  let nav: NavigateFunction = () => {};
  function Probe() {
    nav = useNavigate();
    return <p data-testid="at">{useLocation().pathname}</p>;
  }
  render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={["/before", "/tour"]} initialIndex={1}>
        <TourProvider reads={reads()}>
          <Routes><Route path="/tour" element={<TourStartPage />} /><Route path="*" element={null} /></Routes>
          <Probe />
        </TourProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const first = STEPS[0].route({}).split("?")[0];
  await waitFor(() => expect(screen.getByTestId("at")).toHaveTextContent(first));
  act(() => nav(-1));
  await waitFor(() => expect(screen.getByTestId("at")).toHaveTextContent("/before"));
});

it("a saved tour position that no longer exists starts idle instead of breaking the page", () => {
  window.sessionStorage.setItem("qcertchain.tour", JSON.stringify({ active: true, index: STEPS.length + 5, ctx: {} }));
  const { result } = renderHook(() => useTour(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <MemoryRouter><TourProvider reads={reads()}>{children}</TourProvider></MemoryRouter>
    ),
  });
  expect(result.current.state.active).toBe(false);
  expect(result.current.steps[result.current.state.index]).toBeDefined();
});

it("the highlight finds its element again when the page re-renders it", async () => {
  let swap = () => {};
  function Swapping() {
    const [k, setK] = useState(0);
    swap = () => setK((x) => x + 1);
    return <div key={k} data-tour={STEPS[0].target}>diagram {k}</div>;
  }
  function Start() {
    const t = useTour();
    return <button onClick={() => void t.start()}>start</button>;
  }
  render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter>
        <TourProvider reads={reads()}>
          <Routes><Route path="*" element={<Swapping />} /></Routes><Start /><TourOverlay waitMs={50} />
        </TourProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const at = (top: number) => ({ top, left: 10, width: 200, height: 50, right: 210, bottom: top + 50, x: 10, y: top,
                                  toJSON: () => ({}) }) as DOMRect;
  vi.spyOn(document.querySelector(`[data-tour="${STEPS[0].target}"]`)!, "getBoundingClientRect").mockReturnValue(at(100));
  fireEvent.click(screen.getByText("start"));
  const box = await screen.findByTestId("tour-highlight");
  expect(box.style.top).toBe("96px");
  act(() => swap());
  vi.spyOn(document.querySelector(`[data-tour="${STEPS[0].target}"]`)!, "getBoundingClientRect").mockReturnValue(at(300));
  act(() => { window.dispatchEvent(new Event("scroll")); });
  expect(box.style.top).toBe("296px");
});

it("the Ledger follows a new kit hash in the address while it stays open", async () => {
  const [a, b] = ["ab".repeat(32), "cd".repeat(32)];
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/ledger/by-kit/")) return json({ kit_hash: u.split("/").pop(), campaigns: [], local_telemetry_received: false });
    if (u.includes("/ledger/status")) return json({ available: true, queue_depth: 0, orgs: {}, you: "org1", reason: null });
    if (u.includes("/ledger/events")) return json({ items: [], limit: 50, next_cursor: null });
    return json({}, 404);
  });
  let nav: NavigateFunction = () => {};
  function Nav() { nav = useNavigate(); return null; }
  render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={[`/ledger?kit=${a}`]}><Nav /><LedgerPage /></MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes(`/ledger/by-kit/${a}`))).toBe(true));
  act(() => nav(`/ledger?kit=${b}`));
  await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes(`/ledger/by-kit/${b}`))).toBe(true));
  expect(screen.getByPlaceholderText("Kit hash (64 hex characters)")).toHaveValue(b);
});

function gate(route: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => json({}, 503));
  return render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={[route]}><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
}

it("the Technical approach page is public with a trailing slash too", () => {
  gate("/technical/");
  expect(screen.getByRole("heading", { level: 1, name: "Technical approach" })).toBeInTheDocument();
});

it("signed out, a console link says why the home page opened instead", () => {
  gate("/campaigns");
  expect(screen.getByTestId("signin-note")).toHaveTextContent(/open an organisation under Try the console/i);
  expect(screen.queryByText("console body")).toBeNull();
});

it("signed out, the home page itself carries no such note", () => {
  gate("/");
  expect(screen.queryByTestId("signin-note")).toBeNull();
});

it("a re-check that rejects an old key never signs out the key chosen since", async () => {
  const { apiFetch } = await import("../lib/api");
  setKey("qcc_org_old");
  let rejectOld: (r: Response) => void = () => {};
  vi.spyOn(globalThis, "fetch").mockImplementation(async (u) =>
    String(u).endsWith("/status") ? new Promise<Response>((res) => { rejectOld = res; }) : new Response("{}", { status: 401 }));
  const pending = apiFetch("/campaigns");
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2)); // the request, then its re-check
  setKey("qcc_org_new"); // the analyst signs in again while the old key is being checked
  rejectOld(new Response("{}", { status: 401 }));
  await pending;
  expect(getKey()).toBe("qcc_org_new");
});

it("parallel 401s with different keys are re-checked with their own key", async () => {
  const { apiFetch } = await import("../lib/api");
  const { KEY_HEADER } = await import("../lib/auth");
  const checked: string[] = [];
  let release: () => void = () => {};
  const gate = new Promise<void>((res) => { release = res; });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (u, init) => {
    if (!String(u).endsWith("/status")) return new Response("{}", { status: 401 });
    checked.push(String((init?.headers as Record<string, string>)[KEY_HEADER]));
    await gate;
    return new Response("{}", { status: 200 });
  });
  setKey("qcc_org_a");
  const a = apiFetch("/campaigns");
  await waitFor(() => expect(checked).toEqual(["qcc_org_a"]));
  setKey("qcc_org_b");
  const b = apiFetch("/campaigns");
  await waitFor(() => expect(checked).toEqual(["qcc_org_a", "qcc_org_b"]));
  release();
  await Promise.all([a, b]);
});
