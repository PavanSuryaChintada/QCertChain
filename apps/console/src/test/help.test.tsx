import { fireEvent, screen } from "@testing-library/react";
import { Link } from "react-router-dom";
import { HelpButton } from "../help/HelpPanel";
import { Header } from "../layout/Header";
import { json, renderWith } from "./fixtures";

afterEach(() => vi.restoreAllMocks());

it("the ? opens the current page's explanation with its four parts, and Esc closes it", () => {
  renderWith(<HelpButton />, { route: "/queue" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Live queue" }));
  expect(screen.getByRole("dialog", { name: "About this page: Live queue" })).toBeInTheDocument();
  for (const h of ["What this page is", "How to read it", "Where the data comes from", "What it does not claim"])
    expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("a detail page gets its own entry", () => {
  renderWith(<HelpButton />, { route: "/campaigns/c1" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Campaign" }));
  expect(screen.getByText(/Filled squares are takedown targets/)).toBeInTheDocument();
});

it("the panel closes when the page changes, and the ? then explains the new page", () => {
  renderWith(<><HelpButton /><Link to="/ledger">go</Link></>, { route: "/queue" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Live queue" }));
  fireEvent.click(screen.getByText("go"));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button", { name: "Help: Ledger" })).toBeInTheDocument();
});

it("a page without an entry shows no ?", () => {
  renderWith(<HelpButton />, { route: "/nowhere" });
  expect(screen.queryByTestId("help-button")).toBeNull();
});

it("the top bar carries the ?", () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}, 500));
  renderWith(<Header />, { route: "/metrics" });
  expect(screen.getByRole("button", { name: "Help: Metrics" })).toBeInTheDocument();
});
