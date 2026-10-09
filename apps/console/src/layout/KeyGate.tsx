import { type ReactNode, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { getKey, onKeyChange, setKey } from "../lib/auth";
import { prefetchDemoPath } from "../lib/prefetch";
import { HelpButton } from "../help/HelpPanel";
import { TechnicalPage } from "../views/Technical";

/** Pages anyone may read without a key: they explain the system and hold no organisation data. */
export const PUBLIC_PATHS = ["/technical"];

function PublicShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="topbar" style={{ left: 0 }}>
        <Link to="/" className="link" style={{ textDecoration: "none", fontWeight: 500 }}>QCertChain</Link>
        <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
          <Link to="/" className="link">Sign in</Link>
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
  const [draft, setDraft] = useState("");
  useEffect(() => onKeyChange(() => { setLocal(getKey()); qc.clear(); }), [qc]);
  // warm the demo path once per signed-in key, so each page opens from cache (best-effort, never errors)
  useEffect(() => { if (key) void prefetchDemoPath(qc); }, [key, qc]);
  if (key) return <>{children}</>;
  if (PUBLIC_PATHS.includes(pathname)) return <PublicShell><TechnicalPage /></PublicShell>;
  return (
    <main style={{ padding: 48, maxWidth: 640 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <h1 className="t-display">QCertChain console</h1>
        <div style={{ marginLeft: "auto" }}><HelpButton entryKey="signin" /></div>
      </div>
      {pathname === "/tour" && (
        <p className="prose" style={{ marginTop: 16 }} data-testid="tour-note">
          The guided tour runs on live data, so it needs a key. Sign in with any organisation key, including the read-only demo key, and the tour starts.
        </p>
      )}
      <p className="ink-2 prose" style={{ marginTop: 8 }}>
        Enter your organisation's API key. The key decides which organisation you are: its campaigns, evidence and
        analyses are the only ones that exist for you. To switch organisation, sign out and use another key.
      </p>
      <form style={{ marginTop: 24, display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setKey(draft.trim()); }}>
        <label htmlFor="apikey" className="sr-only">API key</label>
        <input id="apikey" className="input mono" style={{ flex: 1 }} type="password" autoComplete="off" placeholder="qcc_org_..."
               value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>Sign in</button>
      </form>
      <p className="prose ink-2" style={{ marginTop: 24 }}>
        New here? Read the <Link className="link" to="/technical">Technical approach</Link>, or sign in and take the guided
        tour: <Link className="link" to="/tour">How it works</Link>.
      </p>
    </main>
  );
}
