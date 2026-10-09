import { type ReactNode, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { isSuperadminKey } from "../lib/api";
import { getKey, onKeyChange } from "../lib/auth";
import { prefetchDemoPath } from "../lib/prefetch";
import { HelpButton } from "../help/HelpPanel";
import { LandingPage } from "../views/Landing";
import { SuperAdminPage } from "../views/SuperAdmin";
import { TechnicalPage } from "../views/Technical";

/** Pages anyone may read without a key: they explain the system and hold no organisation data. */
export const PUBLIC_PATHS = ["/technical"];

function PublicShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="topbar" style={{ left: 0 }}>
        <Link to="/" className="link" style={{ textDecoration: "none", fontWeight: 500 }}>QCertChain</Link>
        <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
          <Link to="/" className="link">Home</Link>
          <HelpButton />
        </div>
      </header>
      <main className="main" style={{ marginLeft: 0 }}><div className="content">{children}</div></main>
    </>
  );
}

/** Nothing of the console renders without an API key: the key decides which organisation's data exists. */
export function KeyGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const [key, setLocal] = useState(getKey());
  useEffect(() => onKeyChange(() => { setLocal(getKey()); qc.clear(); }), [qc]);
  // warm the demo path once per signed-in organisation key, so each page opens from cache (best-effort)
  useEffect(() => { if (key && !isSuperadminKey(key)) void prefetchDemoPath(qc); }, [key, qc]);
  if (key) return isSuperadminKey(key) ? <SuperAdminPage /> : <>{children}</>;
  if (PUBLIC_PATHS.includes(pathname)) return <PublicShell><TechnicalPage /></PublicShell>;
  // signed out: the public home page (owner decision 2026-10-09); the super admin signs in from it
  return <LandingPage tourNote={pathname === "/tour"} />;
}
