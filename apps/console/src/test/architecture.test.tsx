// Owner request 2026-10-10: below the Architecture diagram, how it works step by step in plain words, with the code
// behind each step and the tech stack.
import { screen, within } from "@testing-library/react";
import { ARCH_STEPS, STACK } from "../explain/architecture";
import { FRAMING } from "../explain/framing";
import { MEASURED } from "../explain/measured";
import { ArchitecturePage } from "../views/Architecture";
import { json, renderWith } from "./fixtures";
import { measuredNumber, strings } from "./textRules";

beforeEach(() => { vi.spyOn(globalThis, "fetch").mockImplementation(async () => json({}, 503)); });
afterEach(() => vi.restoreAllMocks());

it("below the diagram, every step says what it does, which code does it, and where to see it live", () => {
  renderWith(<ArchitecturePage />);
  const how = screen.getByRole("region", { name: "How it works, step by step" });
  for (const s of ARCH_STEPS) {
    const step = within(how).getByTestId(`arch-step-${s.id}`);
    expect(step).toHaveTextContent(s.title);
    expect(step).toHaveTextContent(s.text);
    for (const f of s.code) expect(within(step).getByText(f)).toBeInTheDocument();
    if (s.live) expect(within(step).getByRole("link", { name: s.live.label })).toHaveAttribute("href", s.live.to);
  }
  expect(within(how).getByTestId("arch-step-takedown")).toHaveTextContent(FRAMING);
});

it("a step with a measurement shows it, as generated from reports/metrics.json", () => {
  renderWith(<ArchitecturePage />);
  for (const s of ARCH_STEPS.filter((x) => x.measured)) {
    const m = MEASURED.find((x) => x.id === s.measured);
    const step = screen.getByTestId(`arch-step-${s.id}`);
    if (m) expect(step).toHaveTextContent(m.value);
    else expect(within(step).queryByTestId("arch-measured")).toBeNull();
  }
});

it("the tech stack is a table with a row for every part", () => {
  renderWith(<ArchitecturePage />);
  const table = screen.getByRole("table", { name: "Tech stack" });
  expect(within(table).getAllByRole("row")).toHaveLength(STACK.length + 1);
  for (const r of STACK) expect(table).toHaveTextContent(r.part);
});

it("the step-by-step types no measured number, and no title says quantum", () => {
  for (const s of strings({ ARCH_STEPS, STACK })) expect([s, measuredNumber(s)]).toEqual([s, false]);
  for (const s of ARCH_STEPS) expect(s.title.toLowerCase()).not.toContain("quantum");
});
