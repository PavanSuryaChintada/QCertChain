import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { Campaign, DomainDetail, Page } from "../lib/api";
import { STEPS, resolveCtx, type TourCtx, type TourReads } from "../tour/steps";
import { TourProvider, useTour } from "../tour/TourProvider";
import { GRAPH, SWEEP, json } from "./fixtures";
import { measuredNumber } from "./textRules";

const camp = (id: string, n: number, kit: string): Campaign => ({
  id, label: null, kit_hash: kit, domain_count: n, infra_count: 3, confidence: 80, brands: ["ICICI Bank"], status: "active",
  first_seen: "2026-10-07T00:00:00Z", published_tx: null,
});
const CAMPAIGNS: Page<Campaign> = { items: [camp("small", 50, "k-small"), camp("big", 470, "k-big")], limit: 50, next_cursor: null };

function reads(over: Partial<TourReads> = {}): TourReads {
  return {
    campaigns: vi.fn().mockResolvedValue(CAMPAIGNS),
    graph: vi.fn().mockResolvedValue(GRAPH),
    sweep: vi.fn().mockResolvedValue(SWEEP),
    domain: vi.fn().mockImplementation(async (id: number) => ({ evidence_bundle_id: id === 102 ? "b-102" : null }) as DomainDetail),
    ...over,
  };
}

function wrap(r: TourReads) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={["/tour"]}><TourProvider reads={r}>{children}</TourProvider></MemoryRouter>
  );
}

afterEach(() => { window.sessionStorage.clear(); vi.restoreAllMocks(); });

it("finds the largest campaign, its coverage at the tour budget, a bundle and the kit hash", async () => {
  const r = reads();
  const ctx = await resolveCtx(r);
  // SWEEP has k = 1..3, so the largest k within the tour budget is 3; domain 101 has no bundle, 102 has one
  expect(ctx).toEqual({ campaignId: "big", domainCount: "470", kitHash: "k-big", coverage: { k: "3", killed: "6", total: "6" }, bundleId: "b-102" });
  expect(r.graph).toHaveBeenCalledWith("big", undefined);
});

it("without data the tour still runs, with no live values", async () => {
  expect(await resolveCtx(reads({ campaigns: vi.fn().mockRejectedValue(new Error("offline")) }))).toEqual({});
});

it("every step's text types no measured number and no title says quantum", () => {
  const ph: TourCtx = { campaignId: "C", domainCount: "N", kitHash: "K", bundleId: "B", coverage: { k: "K", killed: "X", total: "T" } };
  for (const s of STEPS) {
    for (const text of [s.title, s.body(ph), s.body({}), s.missing(ph), s.missing({})]) expect([s.id, measuredNumber(text)]).toEqual([s.id, false]);
    expect(s.title.toLowerCase()).not.toContain("quantum");
  }
});

it("while a known campaign is still loading, the card says so instead of claiming there is none", () => {
  const by = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  expect(by.graph.missing({ campaignId: "big" })).toMatch(/still loading/);
  expect(by.graph.missing({})).toMatch(/no campaign yet/);
  expect(by.queue.missing({})).toMatch(/loading, or empty/);
});

it("a step without its item falls back to the list page", () => {
  const by = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  expect(by.graph.route({})).toBe("/campaigns");
  expect(by.evidence.route({})).toBe("/evidence");
  expect(by.ledger.route({})).toBe("/ledger");
  expect(by.ledger.route({ kitHash: "abc" })).toBe("/ledger?kit=abc");
});

it("the arriving-certificates steps ask the queue for All (its default is Confirmed)", () => {
  const by = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  expect(by.queue.route({})).toBe("/queue?status=all");
  expect(by.score.route({})).toBe("/queue?status=all");
  expect(by.confirmed.route({})).toBe("/queue?status=confirmed");
});

it("start opens step one; Next and Back move between pages; the last step ends the tour", async () => {
  const { result } = renderHook(() => ({ tour: useTour(), loc: useLocation() }), { wrapper: wrap(reads()) });
  await act(async () => { await result.current.tour.start(); });
  expect(result.current.tour.state).toMatchObject({ active: true, index: 0 });
  expect(result.current.loc.pathname).toBe("/");
  for (let i = 1; i <= 4; i++) act(() => result.current.tour.next());
  expect(result.current.loc.pathname).toBe("/campaigns/big");
  act(() => result.current.tour.back());
  expect(result.current.loc.pathname + result.current.loc.search).toBe("/queue?status=confirmed");
  for (let i = 0; i < STEPS.length && result.current.tour.state.active; i++) act(() => result.current.tour.next());
  expect(result.current.tour.state.active).toBe(false);
  expect(window.sessionStorage.getItem("qcertchain.tour")).toBeNull();
});

it("the tour survives a reload in the same tab", async () => {
  const first = renderHook(() => useTour(), { wrapper: wrap(reads()) });
  await act(async () => { await first.result.current.start(); });
  act(() => first.result.current.next());
  first.unmount();
  const again = renderHook(() => useTour(), { wrapper: wrap(reads()) });
  expect(again.result.current.state).toMatchObject({ active: true, index: 1 });
});

it("with storage blocked the tour still runs, in memory", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  const { result } = renderHook(() => useTour(), { wrapper: wrap(reads()) });
  await act(async () => { await result.current.start(); });
  act(() => result.current.next());
  expect(result.current.state).toMatchObject({ active: true, index: 1 });
});

it("starting the tour only reads (every request is a GET)", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ items: [], limit: 50, next_cursor: null }));
  const { result } = renderHook(() => useTour(), {
    wrapper: ({ children }: { children: ReactNode }) => <MemoryRouter><TourProvider>{children}</TourProvider></MemoryRouter>,
  });
  await act(async () => { await result.current.start(); });
  expect(f).toHaveBeenCalled();
  for (const [, init] of f.mock.calls) expect(((init as RequestInit | undefined)?.method ?? "GET").toUpperCase()).toBe("GET");
});
