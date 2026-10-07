import { QueryClient } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { ApiError } from "../lib/api";
import { type ViewState, deriveViewState, useLiveQuery } from "../lib/viewState";
import { ViewStateView } from "../components/States";
import { renderWith } from "./fixtures";

const err = (status: number, retryAfter: number | null = null) => new ApiError({ type: "x", title: "t", status, detail: null }, retryAfter);

function show(state: ViewState<string[]>) {
  return render(
    <ViewStateView state={state} what="the list" skeleton={<p>skeleton</p>} empty="Nothing here yet.">
      {(d) => <p>{d.join(",")}</p>}
    </ViewStateView>,
  );
}

it("derives exactly one state from any query snapshot", () => {
  expect(deriveViewState({ data: undefined, error: null, dataUpdatedAt: 0, errorUpdatedAt: 0 }).kind).toBe("loading");
  expect(deriveViewState({ data: undefined, error: err(500), dataUpdatedAt: 0, errorUpdatedAt: 1 }).kind).toBe("error");
  expect(deriveViewState({ data: { items: [] }, error: null, dataUpdatedAt: 1, errorUpdatedAt: 0 }).kind).toBe("empty");
  const stale = deriveViewState({ data: ["a"], error: err(503), dataUpdatedAt: 10, errorUpdatedAt: 20 });
  expect(stale).toMatchObject({ kind: "data", staleSince: 10 });
  const fresh = deriveViewState({ data: ["a"], error: err(503), dataUpdatedAt: 30, errorUpdatedAt: 20 });
  expect(fresh).toMatchObject({ kind: "data", staleSince: null, error: null });
});

it("an error panel and an empty message never render together", () => {
  const states: ViewState<string[]>[] = [
    { kind: "loading" }, { kind: "error", error: err(500) }, { kind: "empty" },
    { kind: "data", data: ["a"], staleSince: null, error: null }, { kind: "data", data: ["a"], staleSince: 1, error: err(500) },
  ];
  for (const s of states) {
    const { container, unmount } = show(s);
    const hasError = !!container.querySelector('[data-state="error"]');
    const hasEmpty = !!container.querySelector('[data-state="empty"]');
    expect(hasError && hasEmpty).toBe(false);
    expect(hasError).toBe(s.kind === "error");
    expect(hasEmpty).toBe(s.kind === "empty");
    unmount();
  }
  // even an error snapshot over empty data resolves to one state
  expect(deriveViewState({ data: [], error: err(500), dataUpdatedAt: 1, errorUpdatedAt: 2 }).kind).toBe("empty");
});

it("error copy is grey and says what to do; 404 never reads 'Error: not found'", () => {
  show({ kind: "error", error: err(404) });
  const t = screen.getByRole("alert").textContent ?? "";
  expect(t).toMatch(/was not found for your organisation/);
  expect(t).not.toMatch(/Error: not found/i);
});

it("429 says rate limit and the retry delay", () => {
  show({ kind: "error", error: err(429, 12) });
  expect(screen.getByRole("alert").textContent).toContain("Rate limit reached, retrying in 12s");
});

function Probe({ fn }: { fn: () => Promise<string[]> }) {
  const q = useLiveQuery<string[]>({ queryKey: ["probe"], queryFn: fn, retry: 0 });
  return <ViewStateView state={q.state} what="the probe" skeleton={null} empty="empty">{(d) => <p>rows {d.join(",")}</p>}</ViewStateView>;
}

it("a failed poll keeps the last good data with a stale bar", async () => {
  let fail = false;
  const fn = vi.fn(async () => { if (fail) throw err(503); return ["x", "y"]; });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  renderWith(<Probe fn={fn} />, { qc });
  await screen.findByText("rows x,y");
  fail = true;
  await act(async () => { await qc.refetchQueries({ queryKey: ["probe"] }); });
  await waitFor(() => expect(screen.getByTestId("stale-bar")).toBeInTheDocument());
  expect(screen.getByTestId("stale-bar").textContent).toMatch(/Showing the probe from \d+s ago/);
  expect(screen.getByText("rows x,y")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
});
