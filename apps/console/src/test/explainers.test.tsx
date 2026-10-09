import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { FRAMING } from "../explain/framing";
import * as LANDING from "../explain/landing";
import { HELP, helpKeyFor } from "../help/content";
import { measuredNumber, strings } from "./textRules";

const APP = readFileSync(resolve(__dirname, "../App.tsx"), "utf8");

it("the takedown framing is the verbatim CLAUDE.md sentence", () => {
  expect(FRAMING).toBe(
    "Takedown-set selection is formulated as a QUBO. It runs on OR-Tools CP-SAT in production; the same formulation runs on QAOA. Quantum is not in the critical path.",
  );
});

it("every console route has a help entry", () => {
  const paths = [...APP.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((p) => p !== "*");
  expect(paths.length).toBeGreaterThanOrEqual(11);
  for (const p of paths) expect([p, helpKeyFor(p.replace(":id", "x"))]).not.toEqual([p, null]);
});

it("help keys follow the shape of the route", () => {
  expect(helpKeyFor("/")).toBe("/");
  expect(helpKeyFor("/queue")).toBe("/queue");
  expect(helpKeyFor("/campaigns/0b1c")).toBe("/campaigns/:id");
  expect(helpKeyFor("/evidence/d2eca4fc")).toBe("/evidence/:id");
  expect(helpKeyFor("/nowhere")).toBeNull();
});

it("help text types no measured number", () => {
  for (const s of strings(HELP)) expect([s, measuredNumber(s)]).toEqual([s, false]);
});

it("every entry has its four parts and no title mentions quantum", () => {
  for (const [k, e] of Object.entries(HELP)) {
    expect([k, e.title.toLowerCase().includes("quantum")]).toEqual([k, false]);
    expect([k, !!e.what && e.read.length > 0 && !!e.data && !!e.notClaimed]).toEqual([k, true]);
  }
});

it("the home page types no measured number, and nothing on it says quantum", () => {
  for (const s of strings(LANDING)) {
    expect([s, measuredNumber(s)]).toEqual([s, false]);
    expect(s.toLowerCase()).not.toContain("quantum");
  }
});
