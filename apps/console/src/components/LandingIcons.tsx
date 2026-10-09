/** Line icons for the home page: one stroke weight, square caps, drawn on a 24 grid. Decorative (aria-hidden): the
 *  heading next to each says what it means. */
const PATHS: Record<string, string> = {
  // a log being read: lines with one picked out
  watch: "M4 6h16M4 10h10M4 14h16M4 18h8M17 12l3 3-3 3",
  // a shield with a tick: confirmed on evidence
  confirm: "M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6zM8.5 12l2.5 2.5 4.5-5",
  // linked nodes: a campaign
  campaign: "M6 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M18 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M12 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M7.5 7.5l3.5 9M16.5 7.5l-3.5 9M8 6h8",
  // a target: the fewest takedowns
  target: "M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0M12 12h.01",
  // a sealed document: evidence
  seal: "M6 3h9l3 3v15H6zM9 9h6M9 13h6M14 18l1.5-1.5L17 18",
  // two linked squares: shared with the network
  network: "M4 9h7v7H4zM13 8h7v7h-7zM11 12h2",
  // a lock: isolation
  lock: "M6 11h12v10H6zM9 11V8a3 3 0 0 1 6 0v3",
  // a key
  key: "M8 15m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0M11 12l8-8M16 7l2 2M14 9l2 2",
  // a chain link broken open: nothing personal on chain
  chain: "M9 15l-2 2a3 3 0 0 1-4-4l3-3a3 3 0 0 1 4 0M15 9l2-2a3 3 0 0 1 4 4l-3 3a3 3 0 0 1-4 0M9 12h6",
  // a hand stop: nothing happens on its own
  hold: "M5 12h14M12 5v14M5 5l14 14",
  // a gate: guarded administration
  gate: "M4 21V8l8-5 8 5v13M9 21v-6h6v6",
};

export function LandingIcon({ name }: { name: keyof typeof PATHS | string }) {
  return (
    <svg className="landing-icon" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
      <path d={PATHS[name] ?? PATHS.watch} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" strokeLinejoin="miter" />
    </svg>
  );
}
