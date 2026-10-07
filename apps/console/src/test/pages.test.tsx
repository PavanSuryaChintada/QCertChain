import { act, fireEvent, renderHook, screen } from "@testing-library/react";
import type { CandidateItem, SystemStatus } from "../lib/api";
import { useHeldRows } from "../views/LiveQueue";
import { ArchitectureDiagram } from "../views/Architecture";
import { Table } from "../components/Table";
import { renderWith } from "./fixtures";
import { render } from "@testing-library/react";

const cand = (id: number, status: CandidateItem["status"] = "candidate"): CandidateItem => ({
  id, name: `d${id}.top`, etld1: `d${id}.top`, status, triage_score: 0.5, brand_matched: "sbi", confidence: null, campaign_id: null,
  first_seen: "2026-10-07T00:00:00Z", source: "certstream", triage_reasons: null,
});

it("queue rows never reorder while held; new rows wait behind the bar; in-place updates still apply", () => {
  const { result, rerender } = renderHook(({ rows, hold }) => useHeldRows(rows, hold, "all"), {
    initialProps: { rows: [cand(2), cand(1)], hold: false },
  });
  expect(result.current.shown.map((r) => r.id)).toEqual([2, 1]);
  rerender({ rows: [cand(3), cand(2), cand(1, "confirmed")], hold: true });
  expect(result.current.shown.map((r) => r.id)).toEqual([2, 1]);
  expect(result.current.shown[1].status).toBe("confirmed");
  expect(result.current.newCount).toBe(1);
  act(() => { result.current.applyPending(); });
  expect(result.current.shown.map((r) => r.id)).toEqual([3, 2, 1]);
  expect(result.current.newCount).toBe(0);
  expect(result.current.flash.has(3)).toBe(true);
});

it("table keyboard path: arrows move, Home/End jump, Enter opens", () => {
  const open = vi.fn();
  render(<Table label="T" rows={[1, 2, 3]} rowKey={(r) => r} onOpen={open}
                columns={[{ key: "n", header: "N", render: (r: number) => `row ${r}` }]} />);
  const rows = screen.getAllByRole("row").slice(1);
  expect(rows.map((r) => r.tabIndex)).toEqual([0, -1, -1]);
  rows[0].focus();
  fireEvent.keyDown(rows[0], { key: "ArrowDown" });
  expect(document.activeElement).toBe(rows[1]);
  fireEvent.keyDown(rows[1], { key: "End" });
  expect(document.activeElement).toBe(rows[2]);
  fireEvent.keyDown(rows[2], { key: "Home" });
  expect(document.activeElement).toBe(rows[0]);
  fireEvent.keyDown(rows[0], { key: "Enter" });
  expect(open).toHaveBeenCalledWith(1);
});

it("table virtualises above the threshold", () => {
  const rows = Array.from({ length: 1000 }, (_, i) => i);
  render(<Table label="T" rows={rows} rowKey={(r) => r} virtualizeAbove={200} maxHeight="600px" density="compact"
                columns={[{ key: "n", header: "N", render: (r: number) => String(r) }]} />);
  expect(screen.getAllByRole("row").length).toBeLessThan(200);
});

const STATUS = {
  org: { slug: "org1", name: "Bank One SOC" }, key_kind: "demo",
  stream: { mode: "live", connection: "connected", certs_per_sec: 1204, names_per_sec: 2000, candidates_per_min: 3, queue_depth: { certs_raw: 10, enrich: 2 }, replay_file: null, last_heartbeat: null },
  metrics: { campaigns_active: 1, domains_confirmed: 400, domains_candidate: 37, certs_per_sec: 1204, plans_today: 1, bundles_today: 1, anchor_queue_depth: 0, candidates_last_hour: 180, confirmations_last_hour: 12 },
  ledger: { available: true, queue_depth: 0 },
  components: { ct: { status: "ok", detail: null }, triage: { status: "ok", detail: null }, confirm: { status: "degraded", detail: "slow fetches" }, ledger: { status: "failed", detail: "chain down" } },
  health: { status: "ok", service: "api", regions: { api: "sin1", api_city: null, database: "ap-southeast-1", database_city: null, colocated: true }, database_round_trip_ms: 2, endpoints: {}, window_s: 300 },
} as unknown as SystemStatus;

it("architecture: every node is a link with status by shape and text, and edge counters are live", () => {
  renderWith(<ArchitectureDiagram status={STATUS} />);
  const links = screen.getAllByRole("link");
  expect(links).toHaveLength(10);
  expect(document.querySelector('[data-node="confirm"]')!.getAttribute("data-status")).toBe("degraded");
  expect(document.querySelector('[data-node="ledger"]')!.getAttribute("data-status")).toBe("failed");
  expect(document.querySelector('[data-node="enrich"]')!.getAttribute("data-status")).toBe("none");
  expect(screen.getByText("1,204")).toBeInTheDocument();
  expect(screen.getByText("180")).toBeInTheDocument();
  expect(screen.getByText("12")).toBeInTheDocument();
  expect(screen.getByText("Degraded")).toBeInTheDocument();
  // text 11.5px minimum: no smaller font size in the diagram
  document.querySelectorAll("text").forEach((t) => {
    const fs = parseFloat((t as SVGTextElement).style.fontSize || "11.5");
    expect(fs).toBeGreaterThanOrEqual(11.5);
  });
});
