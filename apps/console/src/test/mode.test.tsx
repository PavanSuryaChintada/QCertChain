import { render } from "@testing-library/react";
import { ModeIndicator } from "../components/ModeIndicator";

it("replay differs from live in colour token and label", () => {
  const live = render(<ModeIndicator mode="live" connection="connected" certsPerSec={3204} />).container.innerHTML;
  const rep = render(<ModeIndicator mode="replay" connection="replay" certsPerSec={10} replayFile="data/capture.jsonl" />).container.innerHTML;
  expect(live).toContain("--state-live");
  expect(rep).toContain("--state-replay");
  expect(rep).toContain("REPLAY");
  expect(rep).toContain("capture.jsonl");
  expect(live).not.toContain("REPLAY");
  expect(live).toContain("3,204/s");
});

it("a dead or reconnecting stream never reads as live", () => {
  for (const c of ["down", "reconnecting"] as const) {
    const html = render(<ModeIndicator mode="live" connection={c} certsPerSec={0} />).container.innerHTML;
    expect(html).toContain("--state-down");
    expect(html).not.toContain("LIVE");
  }
});
