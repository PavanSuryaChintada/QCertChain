import { screen } from "@testing-library/react";
import { MetricsBody, leadTimeFigure, stageRows } from "../views/Metrics";
import { REPORT, renderWith } from "./fixtures";

it("lead time unavailable renders 'Not measured yet' with the reason, never a number", () => {
  renderWith(<MetricsBody r={REPORT} />);
  const lt = screen.getByTestId("lead-time");
  expect(lt.textContent).toBe("Not measured yet");
  expect(screen.getByText(/OpenPhish feed not yet joined against CT timestamps/)).toBeInTheDocument();
});

it("lead time with no CT-first cases is also not measured", () => {
  expect(leadTimeFigure({ n_ct_first: 0, median_lead_s: 3600 })).toMatchObject({ measured: false });
  expect(leadTimeFigure({ n_ct_first: 4, median_lead_s: 5400 })).toEqual({ measured: true, seconds: 5400, n: 4 });
});

it("measured lead time becomes the largest figure on the page", () => {
  renderWith(<MetricsBody r={{ ...REPORT, lead_time: { n_ct_first: 4, n_matched: 9, median_lead_s: 5400 } }} />);
  const lt = screen.getByTestId("lead-time");
  expect(lt.textContent).toBe("1.5 h");
  const size = (el: HTMLElement) => parseInt(el.style.fontSize || "0", 10);
  expect(size(lt)).toBeGreaterThan(size(screen.getByTestId("precision")));
});

it("precision at the 1:1000 base rate is shown honestly with the balanced-set caveat", () => {
  renderWith(<MetricsBody r={REPORT} />);
  expect(screen.getByTestId("precision").textContent).toBe("0.0024");
  expect(screen.getByText(/NOT balanced-set precision/)).toBeInTheDocument();
  expect(screen.getByText(/two-strong-signal confirmation gate is what protects precision/)).toBeInTheDocument();
  expect(screen.getAllByTestId("not-measured")[0].textContent).toMatch(/^Not measured - /);
});

it("reads the lead-time shape scripts/evaluate.py actually writes, and says why it is not measured", () => {
  const real = { matched_domains: 11, ct_first: 0, listed_before_ct_seen: 11, lead_hours: { p50: null, p95: null, max: null },
                 caveat: "a 30-minute window" };
  const f = leadTimeFigure(real);
  expect(f.measured).toBe(false);
  if (!f.measured) expect(f.reason).toContain("11 phishing domains matched");
  expect(leadTimeFigure({ ...real, ct_first: 3, lead_hours: { p50: 2.5 } })).toEqual({ measured: true, seconds: 9000, n: 3 });
});

it("normalises stage timings from seconds, milliseconds and numeric strings", () => {
  const rows = stageRows({ ct_seen_to_candidate_s: { p50: 2.05, p95: 5.4 }, interdiction_cpsat_solve_ms_api: { p50: 131 },
                           evidence_created_to_anchored_s: { p50: "2044.7", p95: "2098.7" }, note: "x" });
  expect(rows).toEqual([
    { stage: "ct seen to candidate", p50: 2050, p95: 5400 },
    { stage: "interdiction cpsat solve ms api", p50: 131, p95: null },
    { stage: "evidence created to anchored", p50: 2044700, p95: 2098700 },
  ]);
});
