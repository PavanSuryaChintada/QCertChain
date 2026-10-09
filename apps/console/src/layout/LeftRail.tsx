import { NavLink } from "react-router-dom";
import { setKey } from "../lib/auth";
import { useStatus } from "../lib/status";
import { Button } from "../components/Button";

export const NAV = [
  { to: "/", label: "Architecture", end: true },
  { to: "/technical", label: "Technical approach" },
  { to: "/queue", label: "Live queue" },
  { to: "/campaigns", label: "Campaigns" },
  { to: "/evidence", label: "Evidence" },
  { to: "/email", label: "Email analyzer" },
  { to: "/ledger", label: "Ledger" },
  { to: "/metrics", label: "Metrics" },
  { to: "/health", label: "System health" },
  { to: "/ops", label: "Ops log" },
];

const KEY_KIND = { org: "Organisation key", demo: "Demo key (read-only)", admin: "Admin key" } as const;

/** The organisation is pinned at the top and always visible: tenant isolation is a core claim of the product. */
export function OrgIndicator() {
  const { data, state } = useStatus();
  return (
    <section aria-label="Current organisation" style={{ padding: 16, borderBottom: "1px solid var(--hairline-firm)", background: "var(--paper)" }}>
      <p className="t-label">Organisation</p>
      {data ? (
        <>
          <p className="t-section" data-testid="org-name" style={{ marginTop: 4, overflowWrap: "anywhere" }}>{data.org.name}</p>
          <p className="t-meta mono">{data.org.slug}</p>
          <p className="t-meta">{KEY_KIND[data.key_kind] ?? data.key_kind}</p>
        </>
      ) : (
        <p className="t-meta" style={{ marginTop: 4 }}>
          {state.kind === "error" ? "Organisation unavailable: the status request failed." : "Loading organisation"}
        </p>
      )}
      <div style={{ marginTop: 8 }}>
        <Button size="sm" onClick={() => setKey(null)} title="Sign out. To use another organisation, sign in with its key.">Sign out</Button>
      </div>
    </section>
  );
}

export function LeftRail() {
  return (
    <aside className="rail">
      <OrgIndicator />
      <nav aria-label="Pages" style={{ paddingTop: 8 }}>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className="nav-link">{n.label}</NavLink>
        ))}
      </nav>
      <p className="t-meta" style={{ marginTop: "auto", padding: 16 }}>QCertChain</p>
    </aside>
  );
}
