import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { HashDisplay } from "../components/HashDisplay";
import { StatusIndicator, SystemIndicator } from "../components/StatusIndicator";
import { SegmentedControl } from "../components/SegmentedControl";
import { Dropdown } from "../components/Dropdown";
import { truncateHash } from "../lib/format";
import { renderWith } from "./fixtures";

const FULL = "a4f2c9d1e7b3" + "0".repeat(46) + "9f8e7d";

it("HashDisplay truncates to 8 + ellipsis + 6, keeps the full value in the title, copies on click", async () => {
  const write = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText: write } });
  renderWith(<HashDisplay value={FULL} label="root" />);
  const el = screen.getByRole("button");
  expect(el.textContent).toBe("a4f2c9d1…9f8e7d");
  expect(el.getAttribute("title")).toBe(FULL);
  expect(el.className).toContain("hash");
  fireEvent.click(el);
  expect(write).toHaveBeenCalledWith(FULL);
  expect(await screen.findByText("Copied root to the clipboard.")).toBeInTheDocument();
  expect(truncateHash("short")).toBe("short");
});

it("StatusIndicator pairs a shape with a text label, and a candidate never reads as confirmed", () => {
  const cases = [
    ["confirmed", "Confirmed", "filled"], ["candidate", "Suspicious - not verified", "outline"],
    ["benign", "Benign", "diamond"], ["unknown", "Unknown", "diamond-outline"],
  ] as const;
  const shapes = new Set<string>();
  for (const [sev, text, shape] of cases) {
    const { container, unmount } = render(<StatusIndicator severity={sev} />);
    expect(container.textContent).toBe(text);
    const svg = container.querySelector("svg[data-shape]")!;
    expect(svg.getAttribute("data-shape")).toBe(shape);
    expect(svg.getAttribute("width")).toBe("6");
    expect(container.firstElementChild!.className).toContain(`sev-${sev}`);
    shapes.add(shape);
    unmount();
  }
  expect(shapes.size).toBe(4);
  const { container } = render(<StatusIndicator severity="candidate" />);
  expect(container.innerHTML).not.toContain("confirmed");
  expect(container.innerHTML).not.toMatch(/pill|rounded/);
});

it("SystemIndicator: failed is grey and crossed, with text", () => {
  const { container } = render(<SystemIndicator status="failed" />);
  expect(container.textContent).toBe("Failed");
  expect(container.firstElementChild!.className).toContain("sys-failed");
  expect(container.querySelector("svg")!.getAttribute("data-shape")).toBe("cross");
});

function Seg() {
  const [v, setV] = useState("all");
  return <SegmentedControl label="Filter" value={v} onChange={setV}
    segments={[{ value: "all", label: "All", count: 12 }, { value: "candidate", label: "Candidates", count: 7 }, { value: "confirmed", label: "Confirmed", count: 5 }]} />;
}

it("SegmentedControl: one tab stop, arrows / Home / End move and select, counts inside segments", () => {
  render(<Seg />);
  const radios = screen.getAllByRole("radio");
  expect(radios.map((r) => r.tabIndex)).toEqual([0, -1, -1]);
  expect(radios[1].textContent).toContain("7");
  radios[0].focus();
  fireEvent.keyDown(radios[0], { key: "ArrowRight" });
  expect(screen.getByRole("radio", { name: /Candidates/ })).toHaveAttribute("aria-checked", "true");
  expect(document.activeElement).toBe(screen.getByRole("radio", { name: /Candidates/ }));
  fireEvent.keyDown(document.activeElement!, { key: "End" });
  expect(screen.getByRole("radio", { name: /Confirmed/ })).toHaveAttribute("aria-checked", "true");
  fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" }); // wraps
  expect(screen.getByRole("radio", { name: /All/ })).toHaveAttribute("aria-checked", "true");
  fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" }); // wraps back
  expect(screen.getByRole("radio", { name: /Confirmed/ })).toHaveAttribute("aria-checked", "true");
  fireEvent.keyDown(document.activeElement!, { key: "Home" });
  expect(screen.getByRole("radio", { name: /All/ })).toHaveAttribute("aria-checked", "true");
  expect(screen.getAllByRole("radio").filter((r) => r.tabIndex === 0)).toHaveLength(1);
});

const OPTS = ["All channels", "Triage", "Confirm", "Enrich", "Evidence", "Email"].map((l) => ({ value: l.toLowerCase(), label: l }));
function Dd({ onChange }: { onChange?: (v: string) => void }) {
  const [v, setV] = useState("all channels");
  return <Dropdown label="Channel" value={v} options={OPTS} onChange={(x) => { setV(x); onChange?.(x); }} />;
}
const active = () => screen.getByRole("listbox").getAttribute("aria-activedescendant")!;
const activeLabel = () => document.getElementById(active())!.textContent;

it("Dropdown is a custom listbox with arrows, Home, End, Enter, Esc and type-ahead", () => {
  const onChange = vi.fn();
  render(<Dd onChange={onChange} />);
  expect(document.querySelector("select")).toBeNull();
  const button = screen.getByRole("button");
  expect(button).toHaveAttribute("aria-haspopup", "listbox");
  fireEvent.keyDown(button, { key: "ArrowDown" });
  const list = screen.getByRole("listbox");
  expect(document.activeElement).toBe(list);
  expect(activeLabel()).toBe("All channels");
  fireEvent.keyDown(list, { key: "ArrowDown" });
  expect(activeLabel()).toBe("Triage");
  fireEvent.keyDown(list, { key: "End" });
  expect(activeLabel()).toBe("Email");
  fireEvent.keyDown(list, { key: "Home" });
  expect(activeLabel()).toBe("All channels");
  fireEvent.keyDown(list, { key: "e" });
  expect(activeLabel()).toBe("Enrich");
  fireEvent.keyDown(list, { key: "v" }); // "ev"
  expect(activeLabel()).toBe("Evidence");
  fireEvent.keyDown(list, { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(onChange).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(button);
  fireEvent.keyDown(button, { key: "Enter" });
  fireEvent.keyDown(screen.getByRole("listbox"), { key: "c" });
  fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("confirm");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(button.textContent).toContain("Confirm");
});
