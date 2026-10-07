import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { EvidencePage, HashDiff, ONLY_HASHES } from "../views/EvidenceViewer";
import { BUNDLE, VERIFY_OK, VERIFY_TAMPERED, json, renderWith } from "./fixtures";
import { render } from "@testing-library/react";

afterEach(() => vi.restoreAllMocks());

function mount() {
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/verify?tamper=")) return json(VERIFY_TAMPERED);
    if (url.includes("/verify")) return json(VERIFY_OK);
    return json(BUNDLE);
  });
  renderWith(<Routes><Route path="/evidence/:id" element={<EvidencePage />} /></Routes>, { route: "/evidence/b1" });
  return f;
}

it("Tamper shows FAIL with expected and found side by side and the differing characters marked; Restore passes", async () => {
  const f = mount();
  await screen.findByText(ONLY_HASHES);
  fireEvent.click(await screen.findByRole("button", { name: "Tamper (demo)" }));
  await screen.findByText(/Fail: the bundle does not verify/);
  expect(f.mock.calls.some(([u]) => String(u).endsWith("/evidence/b1/verify?tamper=dom.html"))).toBe(true);
  const failure = screen.getByTestId("failure-dom.html");
  const exp = within(failure).getByTestId("diff-expected");
  const found = within(failure).getByTestId("diff-found");
  expect(exp.textContent).toBe("a4f2c9" + "0".repeat(58));
  expect(found.textContent).toBe("a4f2c8" + "0".repeat(57) + "7");
  expect([...exp.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["9", "0"]);
  expect([...found.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["8", "7"]);
  expect(screen.getByTestId("artifact-dom.html").textContent).toContain("Fail");
  expect(screen.getByTestId("artifact-screenshot.png").textContent).toContain("Pass");
  // grey, never red: the fail indicator is a system status
  expect(document.querySelector('[data-check="root"] .si')!.className).toContain("sys-failed");
  expect(document.querySelectorAll("[data-check] .sev-confirmed, [data-testid^=failure] .sev-confirmed")).toHaveLength(0);

  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  await screen.findByText(/Pass: the bundle verifies/);
  await waitFor(() => expect(screen.queryByTestId("failure-dom.html")).toBeNull());
  expect(screen.getAllByText("Disputed").length).toBeGreaterThan(0);
  expect(screen.getByText("Bank Two SOC")).toBeInTheDocument();
});

it("Verify shows the three checks in one click", async () => {
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Verify" }));
  const checks = await screen.findByTestId("checks");
  expect(checks.querySelectorAll("tr[data-check]")).toHaveLength(3);
  expect(within(checks).getByText("Recomputed Merkle root")).toBeInTheDocument();
  expect(within(checks).getByText("Ed25519 signature")).toBeInTheDocument();
  expect(within(checks).getByText("Anchored hash on chain")).toBeInTheDocument();
  expect(document.querySelector('svg [data-root="true"], g[data-root="true"]')).not.toBeNull();
});

it("HashDiff marks a missing found hash plainly", () => {
  render(<HashDiff expected="abc" found={null} />);
  expect(screen.getByTestId("diff-found").textContent).toBe("missing");
});
