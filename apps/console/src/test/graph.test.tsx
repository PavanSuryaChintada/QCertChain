import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { GraphNotice } from "../views/CampaignGraph";
import { CY_OPTIONS, buildStyle, computePositions, runLayout, statusColor } from "../lib/cyto";
import GRAPH from "../fixtures/campaign_graph_400.json";

const TOKENS = readFileSync(resolve(__dirname, "../styles/tokens.css"), "utf8");
const TOKEN_HEX = new Set((TOKENS.match(/#[0-9A-Fa-f]{6}/g) ?? []).map((h) => h.toLowerCase()));

it("graph stylesheet uses only colours defined in tokens.css", () => {
  const css = JSON.stringify(buildStyle());
  const used = (css.match(/#[0-9A-Fa-f]{6}/g) ?? []).map((h) => h.toLowerCase());
  expect(used.length).toBeGreaterThan(3);
  used.forEach((h) => expect(TOKEN_HEX.has(h)).toBe(true));
  expect(css).not.toMatch(/gradient|shadow/i);
});

it("candidate nodes are grey, confirmed red", () => {
  expect(statusColor("candidate")).toBe("#67645e");
  expect(statusColor("confirmed")).toBe("#c0392b");
});

it("takedown targets get the 2px ink-000 ring — the only decorative stroke", () => {
  const target = buildStyle().find((s) => s.selector === "node[?is_target]");
  expect(target?.style["border-width"]).toBe(2);
  expect(String(target?.style["border-color"]).toLowerCase()).toBe("#efeae0");
});

it("dragging and continuous physics are off", () => {
  expect(CY_OPTIONS.autoungrabify).toBe(true);
  expect(CY_OPTIONS.boxSelectionEnabled).toBe(false);
});

it("layout settles once (400ms) from precomputed positions, then stops", () => {
  vi.useFakeTimers();
  const stop = vi.fn();
  const run = vi.fn();
  const cy = { layout: vi.fn(() => ({ run, stop })) };
  runLayout(cy as never, { "d:1": { x: 0, y: 0 } });
  expect(run).toHaveBeenCalledOnce();
  const opts = (cy.layout.mock.calls[0] as unknown[])[0] as { animationDuration: number; name: string };
  expect(opts.name).toBe("preset");
  expect(opts.animationDuration).toBe(400);
  vi.advanceTimersByTime(450);
  expect(stop).toHaveBeenCalledOnce();
  vi.useRealTimers();
});

it("positions for the real 400-domain campaign compute fast (force layouts took 17-22 s)", () => {
  const t = performance.now();
  const pos = computePositions(GRAPH.elements.nodes, GRAPH.elements.edges);
  const ms = performance.now() - t;
  expect(ms).toBeLessThan(1500);
  expect(Object.keys(pos)).toHaveLength(GRAPH.elements.nodes.length);
  Object.values(pos).forEach((p) => { expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true); });
});

it("each domain sits next to its hosting IP, not on top of another domain", () => {
  const pos = computePositions(GRAPH.elements.nodes, GRAPH.elements.edges);
  const ipOf = new Map<string, string>();
  const kind = new Map(GRAPH.elements.nodes.map((n) => [n.data.id, n.data.kind]));
  for (const e of GRAPH.elements.edges) if (kind.get(e.data.target) === "ip") ipOf.set(e.data.source, e.data.target);
  const dist = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);
  for (const [d, ip] of ipOf) {
    const own = dist(pos[d], pos[ip]);
    const others = [...new Set(ipOf.values())].filter((x) => x !== ip).map((x) => dist(pos[d], pos[x]));
    expect(own).toBeLessThanOrEqual(Math.min(...others));
  }
  const keys = new Set(Object.values(pos).map((p) => `${Math.round(p.x)},${Math.round(p.y)}`));
  expect(keys.size).toBe(Object.keys(pos).length);
});

it("positions are deterministic", () => {
  expect(computePositions(GRAPH.elements.nodes, GRAPH.elements.edges))
    .toEqual(computePositions(GRAPH.elements.nodes, GRAPH.elements.edges));
});

it("a truncated graph says so plainly", () => {
  const { getByText } = render(<GraphNotice truncated nodeCount={1200} />);
  getByText(/collapsed into per-infrastructure counts/);
});
