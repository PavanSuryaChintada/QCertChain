import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Drawer } from "../components/Drawer";
import type { Campaign, DomainDetail, Page } from "../lib/api";
import { STEPS, type TourReads } from "../tour/steps";
import { TourOverlay } from "../tour/TourOverlay";
import { TourProvider, useTour } from "../tour/TourProvider";
import { LedgerPage } from "../views/Ledger";
import { GRAPH, SWEEP, json, renderWith } from "./fixtures";

const N = STEPS.length;
const stub = (): TourReads => ({
  campaigns: vi.fn().mockResolvedValue({ items: [] as Campaign[], limit: 50, next_cursor: null } as Page<Campaign>),
  graph: vi.fn().mockResolvedValue(GRAPH),
  sweep: vi.fn().mockResolvedValue(SWEEP),
  domain: vi.fn().mockResolvedValue({ evidence_bundle_id: null } as DomainDetail),
});

function Start() {
  const t = useTour();
  return <button onClick={() => void t.start()}>start</button>;
}

function Pages() {
  return (
    <Routes>
      <Route path="/" element={<div data-tour="architecture">diagram</div>} />
      <Route path="/queue" element={
        <div>
          <div data-tour="status-filter" role="radiogroup" aria-label="Filter"><button role="radio" aria-checked="true">All</button></div>
          <div data-tour="queue"><input aria-label="search" /></div>
        </div>
      } />
      <Route path="*" element={<p>other</p>} />
    </Routes>
  );
}

function setup(waitMs = 50, extra: ReactNode = null) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <TourProvider reads={stub()}><Pages />{extra}<Start /><TourOverlay waitMs={waitMs} /></TourProvider>
    </MemoryRouter>,
  );
}

afterEach(() => { window.sessionStorage.clear(); vi.restoreAllMocks(); });

it("shows the step card, highlights the step's element and moves focus to the card", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  expect(await screen.findByText(`Step 1 of ${N}`)).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "The pipeline" })).toBeInTheDocument();
  expect(await screen.findByTestId("tour-highlight")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "The pipeline" })).toHaveFocus();
});

it("Next step, the arrow keys and Esc drive it", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  fireEvent.click(screen.getByRole("button", { name: "Next step" }));
  expect(await screen.findByText(`Step 2 of ${N}`)).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "ArrowRight" });
  expect(await screen.findByText(`Step 3 of ${N}`)).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "ArrowLeft" });
  expect(await screen.findByText(`Step 2 of ${N}`)).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("arrow keys inside a field or a radio group act on the control, not the tour", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  fireEvent.click(screen.getByRole("button", { name: "Next step" }));
  await screen.findByText(`Step 2 of ${N}`);
  fireEvent.keyDown(screen.getByLabelText("search"), { key: "ArrowRight" });
  fireEvent.keyDown(screen.getByRole("radio", { name: "All" }), { key: "ArrowRight" });
  expect(screen.getByText(`Step 2 of ${N}`)).toBeInTheDocument();
});

it("Esc with a drawer open closes the drawer, not the tour", async () => {
  function OpenDrawer() {
    const [open, setOpen] = useState(true);
    return <Drawer open={open} title="Help" onClose={() => setOpen(false)}><p>help text</p></Drawer>;
  }
  setup(50, <OpenDrawer />);
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  fireEvent.keyDown(document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByText("help text")).toBeNull());
  expect(screen.getByText(`Step 1 of ${N}`)).toBeInTheDocument();
});

it("a step whose element is not there yet says what would be there, then highlights it when it arrives", async () => {
  function Late() {
    const [on, setOn] = useState(false);
    useEffect(() => { const t = setTimeout(() => setOn(true), 300); return () => clearTimeout(t); }, []);
    return on ? <div data-tour="architecture">late diagram</div> : null;
  }
  render(
    <MemoryRouter><TourProvider reads={stub()}><Late /><Start /><TourOverlay waitMs={50} /></TourProvider></MemoryRouter>,
  );
  fireEvent.click(screen.getByText("start"));
  expect(await screen.findByTestId("tour-missing")).toHaveTextContent("pipeline diagram");
  expect(await screen.findByTestId("tour-highlight", {}, { timeout: 2000 })).toBeInTheDocument();
  expect(screen.queryByTestId("tour-missing")).toBeNull();
});

it("the highlight follows its element when the page scrolls", async () => {
  setup();
  const el = document.querySelector('[data-tour="architecture"]')!;
  let top = 100;
  vi.spyOn(el, "getBoundingClientRect").mockImplementation(() =>
    ({ top, left: 10, width: 200, height: 50, right: 210, bottom: top + 50, x: 10, y: top, toJSON: () => ({}) }) as DOMRect);
  fireEvent.click(screen.getByText("start"));
  const box = await screen.findByTestId("tour-highlight");
  expect(box.style.top).toBe("96px");
  top = 40;
  act(() => { window.dispatchEvent(new Event("scroll")); });
  expect(box.style.top).toBe("36px");
});

it("the last step offers Finish, which ends the tour", async () => {
  setup();
  fireEvent.click(screen.getByText("start"));
  await screen.findByText(`Step 1 of ${N}`);
  for (let i = 2; i <= N; i++) {
    fireEvent.click(screen.getByRole("button", { name: "Next step" }));
    await screen.findByText(`Step ${i} of ${N}`);
  }
  fireEvent.click(screen.getByRole("button", { name: "Finish" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("the ledger runs a kit-hash lookup passed in the address", async () => {
  const kit = "ab".repeat(32);
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/ledger/by-kit/")) return json({ kit_hash: kit, campaigns: [], local_telemetry_received: false });
    if (u.includes("/ledger/status")) return json({ available: true, queue_depth: 0, orgs: {}, you: "org1", reason: null });
    if (u.includes("/ledger/events")) return json({ items: [], limit: 50, next_cursor: null });
    return json({}, 404);
  });
  renderWith(<LedgerPage />, { route: `/ledger?kit=${kit}` });
  await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes(`/ledger/by-kit/${kit}`))).toBe(true));
  expect(screen.getByPlaceholderText("Kit hash (64 hex characters)")).toHaveValue(kit);
});
