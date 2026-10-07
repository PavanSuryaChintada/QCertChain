import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { CHAR_W, layoutGraph, shortLabel } from "../lib/graphLayout";
import { useLiveQuery } from "../lib/viewState";
import { signalNames } from "../views/LiveQueue";
import { MetricsBody } from "../views/Metrics";
import { CampaignGraphSvg } from "../views/CampaignGraph";
import { GRAPH, REPORT, renderWith } from "./fixtures";
import type { CampaignGraph, NodeKind } from "../lib/api";

it("signals column names the contributing features, strongest first", () => {
  expect(signalNames({ score: 0.6, provenance: "rules", threshold: 0.35, reasons: [
    { feature: "tld_risk", value: "top", contribution: 0.1 }, { feature: "brand_token_exact", value: "sbi", contribution: 0.35 },
    { feature: "keyword_count", value: 2, contribution: 0.15 }, { feature: "allowlisted", value: false, contribution: 0 },
  ] })).toBe("brand, keywords, tld risk");
  expect(signalNames(null)).toBe("");
});

// 4 nameservers + 3 registrars + many evidence nodes sharing one band, like the seeded campaign.
const CROWDED: CampaignGraph = {
  ...GRAPH,
  nodes: [
    [1, "ip", "203.0.113.10", 3, true], [2, "ip", "203.0.113.20", 3, true],
    ...[1, 2, 3, 4].map((i) => [10 + i, "nameserver", `ns${i}.titli-kit-dns.example`, 3, true] as [number, NodeKind, string, number, boolean]),
    ...["A", "B", "C"].map((x, i) => [20 + i, "registrar", `Registrar ${x} (seed)`, 3, true] as [number, NodeKind, string, number, boolean]),
    [30, "kit_hash", "c9c69097bd87d4386220b7fa449aa41de107113b93def97671fb14346883da73", 6, false], [31, "cert_issuer", "Let's Encrypt", 6, false],
  ],
  edges: [...GRAPH.edges.filter(([, n]) => n <= 2), ...[11, 12, 13, 14, 20, 21, 22, 30, 31].flatMap((n) => [[101, n, 1], [104, n, 1]] as [number, number, number][])],
};

it("graph band labels never overlap: staggered baselines and widths that fit", () => {
  const l = layoutGraph(CROWDED);
  const band = l.infra.filter((n) => !n.anchor);
  for (const a of band) for (const b of band) {
    if (a === b || a.y !== b.y || a.labelDy !== b.labelDy) continue;
    const wa = shortLabel(a.value, a.labelChars!).length * CHAR_W, wb = shortLabel(b.value, b.labelChars!).length * CHAR_W;
    expect(Math.abs(a.x - b.x)).toBeGreaterThanOrEqual((wa + wb) / 2);
  }
  // clusters are never narrower than their labels, so cluster labels do not collide either
  const cs = [...l.clusters].sort((p, q) => p.y - q.y || p.x - q.x);
  for (let i = 1; i < cs.length; i++) {
    if (cs[i].y !== cs[i - 1].y) continue;
    expect(cs[i].x - cs[i - 1].x).toBeGreaterThanOrEqual((cs[i].label.length + cs[i - 1].label.length) * CHAR_W / 2);
  }
});

it("graph edges are uniform hairlines even for selected targets; hashes are 8+6", () => {
  renderWith(<CampaignGraphSvg graph={CROWDED} selected={new Map([[11, 1], [20, 2]])} killed={new Set([101, 104])} />);
  const lines = [...document.querySelectorAll('g[data-layer="links"] line')];
  expect(lines.length).toBeGreaterThan(0);
  lines.forEach((ln) => { expect(ln.getAttribute("stroke")).toBe("var(--hairline)"); expect(ln.getAttribute("stroke-width")).toBe("1"); });
  expect(document.querySelector('[data-label="30"]')!.textContent).toBe("c9c69097…83da73");
});

it("lead-time title is source-neutral and shows the dataset caption", () => {
  renderWith(<MetricsBody r={{ ...REPORT, lead_time: { matched_domains: 11, ct_first: 0, dataset: "PhishTank verified-online x 30-min CT capture" } as never }} />);
  expect(screen.getByText("Lead time: CT certificate vs phishing-feed listing")).toBeInTheDocument();
  expect(screen.queryByText(/OpenPhish listing/)).toBeNull();
  expect(screen.getByTestId("lead-dataset").textContent).toContain("PhishTank");
  expect(screen.getByTestId("lead-time").textContent).toBe("Not measured yet");
});

function Probe({ fn }: { fn: (s: AbortSignal) => Promise<string> }) {
  const q = useLiveQuery<string>({ queryKey: ["strict"], queryFn: fn, isEmpty: () => false });
  return <p>{q.data ?? "loading"}</p>;
}

it("a StrictMode remount reuses the in-flight request instead of aborting it and firing a duplicate", async () => {
  const seen: AbortSignal[] = [];
  const fn = vi.fn((s: AbortSignal) => { seen.push(s); return new Promise<string>((r) => setTimeout(() => r("done"), 50)); });
  renderWith(<StrictMode><Probe fn={fn} /></StrictMode>, { qc: new QueryClient() });
  await waitFor(() => expect(screen.getByText("done")).toBeInTheDocument());
  expect(fn).toHaveBeenCalledTimes(1);
  expect(seen.every((s) => !s.aborted)).toBe(true);
});
