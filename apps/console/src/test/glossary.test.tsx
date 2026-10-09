import { fireEvent, screen } from "@testing-library/react";
import { GLOSSARY } from "../explain/glossary";
import { HELP } from "../help/content";
import { HelpButton } from "../help/HelpPanel";
import { STEPS } from "../tour/steps";
import { renderWith } from "./fixtures";
import { measuredNumber, strings } from "./textRules";

it("every tour step explains at least two of the words on its page, and every word is defined", () => {
  for (const s of STEPS) {
    expect([s.id, s.terms.length >= 2]).toEqual([s.id, true]);
    for (const t of s.terms) expect([s.id, t, t in GLOSSARY]).toEqual([s.id, t, true]);
  }
});

it("help panels list the words of their page, all defined", () => {
  for (const [k, e] of Object.entries(HELP)) for (const t of e.terms ?? []) expect([k, t, t in GLOSSARY]).toEqual([k, t, true]);
  expect(HELP["/ledger"].terms).toEqual(expect.arrayContaining(["iocRoot", "corroborate", "dispute", "kitHash"]));
});

it("definitions type no measured number and no word is titled quantum", () => {
  for (const s of strings(GLOSSARY)) expect([s, measuredNumber(s)]).toEqual([s, false]);
  for (const [id, g] of Object.entries(GLOSSARY)) expect([id, g.term.toLowerCase().includes("quantum")]).toEqual([id, false]);
});

it("the ledger's ? explains what an IOC root and Corroborate are", () => {
  renderWith(<HelpButton />, { route: "/ledger" });
  fireEvent.click(screen.getByRole("button", { name: "Help: Ledger" }));
  expect(screen.getByRole("heading", { name: "Words on this page" })).toBeInTheDocument();
  expect(screen.getByText("IOC root")).toBeInTheDocument();
  expect(screen.getByText(GLOSSARY.iocRoot.meaning)).toBeInTheDocument();
  expect(screen.getByText("Corroborate")).toBeInTheDocument();
});
