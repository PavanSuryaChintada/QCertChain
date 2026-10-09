import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { STEPS } from "../tour/steps";

const SRC = resolve(__dirname, "..");
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" ? [] : files(p);
    return /\.tsx?$/.test(f) ? [p] : [];
  });
}
const SOURCE = files(SRC).map((p) => readFileSync(p, "utf8")).join("\n");

it("every tour step points at an element some page marks", () => {
  for (const s of STEPS) {
    const marked = SOURCE.includes(`data-tour="${s.target}"`) || SOURCE.includes(`tour="${s.target}"`);
    expect([s.id, marked]).toEqual([s.id, true]);
  }
});
