import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { screen } from "@testing-library/react";
import tailwind from "../../tailwind.config";
import { InterdictionWorkbench, SolversTable } from "../views/CampaignView";
import { MetricsBody } from "../views/Metrics";
import { Button } from "../components/Button";
import { Dropdown } from "../components/Dropdown";
import { SegmentedControl } from "../components/SegmentedControl";
import { HashDisplay } from "../components/HashDisplay";
import { Slider } from "../components/Slider";
import { NAV } from "../layout/LeftRail";
import { GRAPH, REPORT, SWEEP, renderWith } from "./fixtures";

const SRC = resolve(__dirname, "..");
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" ? [] : files(p);
    return /\.(tsx?|css)$/.test(f) ? [p] : [];
  });
}
const SOURCES = files(SRC).map((p) => ({ p, s: readFileSync(p, "utf8") }));

it("no source uses a non-zero border radius (Tailwind classes, inline styles or CSS)", () => {
  for (const { p, s } of SOURCES) {
    expect([p, s.match(/\brounded(?!-none)(-[a-z0-9]+)*\b/g)]).toEqual([p, null]);
    expect([p, s.match(/borderRadius:(?!\s*(0\b|"0"|'0'))[^,}]+/g)]).toEqual([p, null]);
    expect([p, s.match(/border-radius:(?!\s*0\s*(!important)?\s*;)[^;]+;/g)]).toEqual([p, null]);
    expect([p, s.match(/\brx=|\bry=/g)]).toEqual([p, null]);
  }
  expect(Object.values(tailwind.theme!.borderRadius as Record<string, string>).every((v) => v === "0")).toBe(true);
});

it("no gradients, glow, drop shadows on cards, or emoji anywhere in the source", () => {
  for (const { p, s } of SOURCES) {
    expect([p, s.match(/gradient|backdrop-filter|text-shadow|drop-shadow/gi)]).toEqual([p, null]);
    expect([p, s.match(/\p{Extended_Pictographic}/gu)]).toEqual([p, null]);
    expect([p, s.match(/outline:\s*none/g)]).toEqual([p, null]);
    // box-shadow is only the overlay token, applied only to things that float
    for (const m of s.match(/box-shadow:[^;]+;/g) ?? []) expect(m).toContain("var(--overlay-shadow)");
  }
});

it("colours are defined only in tokens.css", () => {
  for (const { p, s } of SOURCES) {
    if (p.endsWith("tokens.css")) continue;
    expect([p, s.match(/#[0-9a-fA-F]{3,8}\b(?![\w-])/g)?.filter((m) => !/^#\d+$/.test(m) || m.length > 4) ?? null]).toEqual([p, null]);
  }
});

it("spacing is only from 4/8/12/16/24/32/48 in inline styles", () => {
  const bad = /\b(?:padding|margin|gap|marginTop|marginBottom|marginLeft|marginRight|paddingLeft|paddingTop)\s*:\s*(\d+)\b/g;
  for (const { p, s } of SOURCES) {
    for (const m of s.matchAll(bad)) expect([p, m[0], [0, 4, 8, 12, 16, 24, 32, 48].includes(Number(m[1]))]).toEqual([p, m[0], true]);
  }
});

it("every rendered element computes border-radius 0 with the app stylesheet applied", () => {
  const css = readFileSync(join(SRC, "styles/app.css"), "utf8").replace(/@(import|tailwind)[^;]+;/g, "");
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  renderWith(
    <div>
      <Button>Act</Button><Button variant="primary">Go</Button>
      <Dropdown label="Pick" value="a" onChange={() => {}} options={[{ value: "a", label: "A" }]} />
      <SegmentedControl label="Seg" value="a" onChange={() => {}} segments={[{ value: "a", label: "A", count: 1 }]} />
      <HashDisplay value={"f".repeat(64)} />
      <Slider label="k" min={1} max={3} value={2} onChange={() => {}} />
      <input className="input" aria-label="x" /><textarea className="input" aria-label="y" />
      <InterdictionWorkbench graph={GRAPH} sweep={SWEEP} initialK={2} />
      <SolversTable rows={[]} />
      <MetricsBody r={REPORT} />
    </div>,
  );
  const all = document.body.querySelectorAll("*");
  expect(all.length).toBeGreaterThan(200);
  all.forEach((el) => expect(["", "0", "0px"]).toContain(getComputedStyle(el).borderRadius));
  style.remove();
});

it("no quantum wording in nav items, and labels are sentence case", () => {
  for (const n of NAV) {
    expect(n.label.toLowerCase()).not.toContain("quantum");
    expect(n.label[0]).toBe(n.label[0].toUpperCase());
    expect(n.label.slice(1)).toBe(n.label.slice(1).toLowerCase());
  }
  renderWith(<InterdictionWorkbench graph={GRAPH} sweep={SWEEP} initialK={2} />);
  screen.getAllByRole("heading").forEach((h) => {
    expect(h.textContent!.toLowerCase()).not.toContain("quantum");
    expect(h.textContent).not.toMatch(/[A-Z]{3,}\s+[A-Z]{3,}/);
  });
});
