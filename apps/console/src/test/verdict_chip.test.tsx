import { render } from "@testing-library/react";
import { VerdictChip } from "../components/VerdictChip";

// docs/DESIGN.md §2: colour on a candidate is a hard ban. These hexes are the chromatic verdict colours.
const VERDICT_HEX = ["#c0392b", "#4a5d52", "#9a760c"];

function swatch(container: HTMLElement) {
  return container.querySelector("[data-swatch]")!.getAttribute("style") ?? "";
}

it("candidate never renders a verdict colour", () => {
  const { container, getByText } = render(<VerdictChip status="candidate" />);
  getByText("CANDIDATE");
  const html = container.innerHTML.toLowerCase();
  VERDICT_HEX.forEach((c) => expect(html).not.toContain(c));
  expect(swatch(container)).toContain("var(--v-candidate)");
  ["--v-confirmed", "--v-dismissed", "--v-unreach"].forEach((t) => expect(html).not.toContain(t));
});

it("suspicious email renders grey exactly like a candidate", () => {
  const { container, getByText } = render(<VerdictChip status="suspicious" />);
  getByText("SUSPICIOUS");
  expect(swatch(container)).toContain("var(--v-candidate)");
});

it("confirmed shows the word and the red swatch", () => {
  const { container, getByText } = render(<VerdictChip status="confirmed" />);
  getByText("CONFIRMED");
  expect(swatch(container)).toContain("var(--v-confirmed)");
});

it("every status pairs the swatch with a word (never colour alone)", () => {
  for (const s of ["candidate", "confirmed", "dismissed", "unreachable", "malicious", "suspicious", "clean"] as const) {
    const { container, unmount } = render(<VerdictChip status={s} />);
    expect(container.textContent!.trim().length).toBeGreaterThan(3);
    unmount();
  }
});

it("a confirmed verdict with fewer than two strong signals is shown as a candidate", () => {
  const { container, getByText } = render(<VerdictChip status="confirmed" strongCount={1} />);
  getByText("CANDIDATE");
  expect(swatch(container)).toContain("var(--v-candidate)");
});
