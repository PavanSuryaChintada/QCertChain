import { type ReactNode, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { Button } from "../components/Button";
import { HashDisplay } from "../components/HashDisplay";
import { api, CATEGORIES, isSuperadminKey, toApiError, type PublicOrg } from "../lib/api";
import { getKey, onKeyChange, setKey } from "../lib/auth";
import { prefetchDemoPath } from "../lib/prefetch";
import { HelpButton } from "../help/HelpPanel";
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
          <Link to="/" className="link">Sign in</Link>
          <HelpButton />
        </div>
      </header>
      <main className="main" style={{ marginLeft: 0 }}><div className="content">{children}</div></main>
    </>
  );
}

/** Every organisation with its read-only key, by category: one click signs in to look, never to change. */
function OrganisationsTab() {
  const orgs = useQuery({ queryKey: ["public-orgs"], queryFn: ({ signal }) => api.publicOrgs(signal), retry: false });
  const by = (c: string) => (orgs.data ?? []).filter((o) => o.category === c);
  return (
    <div style={{ marginTop: 16 }}>
      {orgs.isLoading && <p className="t-meta">Loading organisations</p>}
      {orgs.error && (
        <p className="t-meta">
          The organisation list is unavailable right now ({toApiError(orgs.error).problem.title}). You can still paste a key below.
        </p>
      )}
      {CATEGORIES.filter((c) => by(c.value).length > 0).map((c) => (
        <section key={c.value} style={{ marginTop: 16 }}>
          <h2 className="t-section">{c.label}</h2>
          {by(c.value).map((o: PublicOrg) => (
            <div key={o.slug} className="panel panel-body"
                 style={{ marginTop: 8, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <p style={{ fontWeight: 500 }}>{o.name}</p>
                {o.demo_key ? <HashDisplay value={o.demo_key} label={o.name + " read-only key"} />
                            : <p className="t-meta">No read-only key yet</p>}
              </div>
              {o.demo_key && (
                <Button size="sm" variant="primary" iconLabel={"Sign in to " + o.name + " (read-only)"}
                        onClick={() => setKey(o.demo_key)}>Sign in (read-only)</Button>
              )}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

function SuperAdminTab() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      setKey((await api.superLogin(email.trim(), password)).token);
    } catch (e) {
      const p = toApiError(e).problem;
      setError(p.detail ?? p.title);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form style={{ marginTop: 16, display: "grid", gap: 8, maxWidth: 400 }} onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <label htmlFor="sa-email" className="t-label">Email</label>
      <input id="sa-email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="sa-password" className="t-label">Password</label>
      <input id="sa-password" className="input" type="password" autoComplete="current-password" value={password}
             onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="prose" role="alert">{error}</p>}
      <div><button type="submit" className="btn btn-primary" disabled={busy || !email.trim() || !password}>Sign in as super admin</button></div>
    </form>
  );
}

/** Nothing of the console renders without an API key: the key decides which organisation's data exists. */
export function KeyGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const [key, setLocal] = useState(getKey());
  const [draft, setDraft] = useState("");
  const [tab, setTab] = useState<"orgs" | "super">("orgs");
  useEffect(() => onKeyChange(() => { setLocal(getKey()); qc.clear(); }), [qc]);
  // warm the demo path once per signed-in organisation key, so each page opens from cache (best-effort)
  useEffect(() => { if (key && !isSuperadminKey(key)) void prefetchDemoPath(qc); }, [key, qc]);
  if (key) return isSuperadminKey(key) ? <SuperAdminPage /> : <>{children}</>;
  if (PUBLIC_PATHS.includes(pathname)) return <PublicShell><TechnicalPage /></PublicShell>;
  const tabClass = (t: "orgs" | "super") => (tab === t ? "btn btn-sm btn-primary" : "btn btn-sm");
  return (
    <main style={{ padding: 48, maxWidth: 760 }}>
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
        One platform, many organisations. Each organisation signs in with its own key and sees only its own campaigns,
        evidence and analyses. The read-only keys below let anyone look without changing anything.
      </p>
      <div role="tablist" aria-label="Sign in as" style={{ display: "flex", gap: 8, marginTop: 24 }}>
        <button type="button" role="tab" aria-selected={tab === "orgs"} className={tabClass("orgs")} onClick={() => setTab("orgs")}>Organisations</button>
        <button type="button" role="tab" aria-selected={tab === "super"} className={tabClass("super")} onClick={() => setTab("super")}>Super admin</button>
      </div>
      {tab === "super" ? <SuperAdminTab /> : (
        <>
          <OrganisationsTab />
          <p className="ink-2 prose" style={{ marginTop: 24 }}>Have a full key? Paste it to sign in with every right your organisation has.</p>
          <form style={{ marginTop: 8, display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setKey(draft.trim()); }}>
            <label htmlFor="apikey" className="sr-only">API key</label>
            <input id="apikey" className="input mono" style={{ flex: 1 }} type="password" autoComplete="off" placeholder="qcc_org_..."
                   value={draft} onChange={(e) => setDraft(e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>Sign in</button>
          </form>
        </>
      )}
      <p className="prose ink-2" style={{ marginTop: 24 }}>
        New here? Read the <Link className="link" to="/technical">Technical approach</Link>, or sign in and take the guided
        tour: <Link className="link" to="/tour">How it works</Link>.
      </p>
    </main>
  );
}
