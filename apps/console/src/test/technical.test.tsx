import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FRAMING } from "../explain/framing";
import { TECHNICAL } from "../explain/technical";
import { KeyGate } from "../layout/KeyGate";
import { NAV } from "../layout/LeftRail";
import { setKey } from "../lib/auth";
import { TechnicalPage } from "../views/Technical";
import { renderWith } from "./fixtures";
import { measuredNumber, strings } from "./textRules";

afterEach(() => { setKey(null); vi.restoreAllMocks(); });

function gate(route: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[route]}><KeyGate><p>console body</p></KeyGate></MemoryRouter>
    </QueryClientProvider>,
  );
}

it("the Technical approach page opens without a key", () => {
  gate("/technical");
  expect(screen.getByRole("heading", { level: 1, name: "Technical approach" })).toBeInTheDocument();
  expect(screen.queryByLabelText("API key")).toBeNull();
  expect(screen.queryByText("console body")).toBeNull();
});

it("the home page links to both explainers and carries a ?", () => {
  gate("/");
  expect(screen.getByRole("link", { name: "Technical approach" })).toHaveAttribute("href", "/technical");
  expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/tour");
  expect(screen.getByRole("button", { name: "Help: Home" })).toBeInTheDocument();
});

it("opening the tour signed out says how to start it, next to the organisations to open", () => {
  gate("/tour");
  expect(screen.getByTestId("tour-note")).toHaveTextContent("Try the console");
  expect(screen.getByRole("complementary", { name: "Try the console" })).toBeInTheDocument();
});

it("the page states the takedown framing verbatim and no heading says quantum", () => {
  renderWith(<TechnicalPage />, { route: "/technical" });
  expect(screen.getByText(FRAMING)).toBeInTheDocument();
  screen.getAllByRole("heading").forEach((h) => expect(h.textContent!.toLowerCase()).not.toContain("quantum"));
});

it("sections offer a See it live button to the page where it happens, and the page ends with the tour", () => {
  renderWith(<TechnicalPage />, { route: "/technical" });
  expect(screen.getByRole("link", { name: "See the live queue" })).toHaveAttribute("href", "/queue?status=all");
  expect(screen.getByRole("link", { name: "See a takedown plan" })).toHaveAttribute("href", "/campaigns");
  expect(screen.getByRole("link", { name: "See confirmed domains" })).toHaveAttribute("href", "/queue?status=confirmed");
  expect(screen.getByRole("link", { name: "Open the ledger" })).toHaveAttribute("href", "/ledger");
  expect(screen.getByRole("link", { name: "See the metrics" })).toHaveAttribute("href", "/metrics");
  expect(screen.getByRole("link", { name: "Start the guided tour" })).toHaveAttribute("href", "/tour");
});

it("Technical approach text types no measured number", () => {
  for (const s of strings(TECHNICAL)) expect([s, measuredNumber(s)]).toEqual([s, false]);
});

it("the left rail offers the Technical approach", () => {
  expect(NAV.map((n) => n.label)).toContain("Technical approach");
});
