import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "../components/Button";
import { Drawer } from "../components/Drawer";
import { HashDisplay } from "../components/HashDisplay";
import { PipelineDiagram } from "../components/PipelineDiagram";
import { AFTER, EVIDENCE, HERO, LIFELINE, OFFER, POSITIONING, ROADMAP, SECURITY, type Item } from "../explain/landing";
import { HelpButton } from "../help/HelpPanel";
import { api, CATEGORIES, toApiError, type PublicOrg } from "../lib/api";
import { setKey } from "../lib/auth";

function Block({ id, title, intro, children }: { id: string; title: string; intro?: string; children: ReactNode }) {
  return (
    <section className="landing-block" aria-labelledby={id}>
      <h2 id={id} className="landing-h2">{title}</h2>
      {intro && <p className="prose ink-2 landing-intro">{intro}</p>}
      {children}
    </section>
  );
}

/** Unordered capabilities: no numbers, because they are not a sequence. */
function Items({ items }: { items: Item[] }) {
  return (
    <dl className="landing-items">
      {items.map((i) => (
        <div key={i.title}>
          <dt>{i.title}</dt>
          <dd className="ink-2">{i.text}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A real sequence: numbered. */
function Steps({ items }: { items: Item[] }) {
  return (
    <ol className="landing-steps">
      {items.map((i) => (
        <li key={i.title}>
          <p className="landing-step-title">{i.title}</p>
          <p className="ink-2">{i.text}</p>
        </li>
      ))}
    </ol>
  );
}

/** Every organisation with its read-only key: one click to look, never to change. New ones appear as soon as the
 *  super admin creates them (GET /orgs/public). */
function TryTheConsole() {
  const orgs = useQuery({ queryKey: ["public-orgs"], queryFn: ({ signal }) => api.publicOrgs(signal), retry: false });
  const by = (c: string) => (orgs.data ?? []).filter((o) => o.category === c);
  return (
    <aside className="landing-side panel panel-body" aria-labelledby="try-title" id="try">
      <h2 id="try-title" className="t-section">Try the console</h2>
      <p className="prose ink-2" style={{ marginTop: 4 }}>
        Every organisation on the platform, with its read-only key. Open one to see its console: you can look, never change.
      </p>
      {orgs.isLoading && <p className="t-meta" style={{ marginTop: 12 }}>Loading organisations</p>}
      {orgs.error && <p className="t-meta" style={{ marginTop: 12 }}>The list is unavailable right now ({toApiError(orgs.error).problem.title}).</p>}
      {CATEGORIES.filter((c) => by(c.value).length > 0).map((c) => (
        <section key={c.value} style={{ marginTop: 16 }}>
          <h3 className="t-label">{c.label}</h3>
          {by(c.value).map((o: PublicOrg) => (
            <div key={o.slug} className="landing-org">
              <div style={{ minWidth: 0 }}>
                <p style={{ fontWeight: 500 }}>{o.name}</p>
                {o.demo_key ? <HashDisplay value={o.demo_key} label={o.name + " read-only key"} /> : <p className="t-meta">No read-only key yet</p>}
              </div>
              {o.demo_key && (
                <Button size="sm" variant="primary" iconLabel={"Sign in to " + o.name + " (read-only)"} onClick={() => setKey(o.demo_key)}>Open</Button>
              )}
            </div>
          ))}
        </section>
      ))}
      <p className="t-meta" style={{ marginTop: 16 }}>New organisations appear here as soon as the platform's super admin creates them.</p>
    </aside>
  );
}

function SuperAdminSignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setKey((await api.superLogin(email.trim(), password)).token);
    } catch (err) {
      const p = toApiError(err).problem;
      setError(p.detail ?? p.title);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="landing-form" onSubmit={submit}>
      <p className="prose ink-2">For the platform's operator. Organisations open their console from Try the console.</p>
      <label htmlFor="sa-email" className="t-label">Email</label>
      <input id="sa-email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="sa-password" className="t-label">Password</label>
      <input id="sa-password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="prose" role="alert">{error}</p>}
      <div><button type="submit" className="btn btn-primary" disabled={busy || !email.trim() || !password}>Sign in as super admin</button></div>
    </form>
  );
}

/** A demo form: sign-up is by invitation during the pilot. It sends and stores nothing, and says so. */
function RequestAccess() {
  const [done, setDone] = useState(false);
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  if (done) {
    return (
      <div className="landing-form">
        <p className="prose">Sign-up is by invitation during the pilot: the platform's super admin creates each organisation and its keys.</p>
        <p className="prose ink-2">Nothing was sent or stored: this is a demo form.</p>
      </div>
    );
  }
  return (
    <form className="landing-form" onSubmit={(e) => { e.preventDefault(); setDone(true); }}>
      <label htmlFor="ra-email" className="t-label">Work email</label>
      <input id="ra-email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="ra-org" className="t-label">Organisation</label>
      <input id="ra-org" className="input" value={org} onChange={(e) => setOrg(e.target.value)} />
      <div><button type="submit" className="btn btn-primary" disabled={!email.trim() || !org.trim()}>Request access</button></div>
    </form>
  );
}

/** The public home page for anyone without a key (spec 2026-10-09; owner request: a SaaS page, not AI slop). */
export function LandingPage({ tourNote = false }: { tourNote?: boolean }) {
  const [open, setOpen] = useState<"signin" | "access" | null>(null);
  const side = useRef<HTMLDivElement>(null);
  return (
    <>
      <header className="topbar" style={{ left: 0 }}>
        <span className="landing-brand">QCertChain</span>
        <nav aria-label="Explainers" style={{ display: "flex", gap: 16 }}>
          <Link to="/tour" className="link">How it works</Link>
          <Link to="/technical" className="link">Technical approach</Link>
        </nav>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <Button size="sm" onClick={() => setOpen("access")}>Request access</Button>
          <Button size="sm" variant="primary" onClick={() => setOpen("signin")}>Sign in</Button>
          <HelpButton entryKey="signin" />
        </div>
      </header>
      <main className="main" style={{ marginLeft: 0 }}>
        <div className="landing">
          <div className="landing-main">
            {tourNote && (
              <p className="stale-bar" data-testid="tour-note">
                The guided tour runs on live data: open an organisation under Try the console and the tour starts.
              </p>
            )}
            <h1 className="landing-title">{HERO.title}</h1>
            <p className="landing-lead">{HERO.lead}</p>
            <ol className="lifeline" aria-label="The life of a phishing domain">
              {LIFELINE.map((s) => (
                <li key={s.step} className={s.ours ? "ours" : undefined}>
                  <p className="lifeline-step">{s.step}</p>
                  <p className={s.ours ? "lifeline-note ours-note" : "lifeline-note"}>{s.note}</p>
                </li>
              ))}
            </ol>
            <div style={{ display: "flex", gap: 12, marginTop: 24, flexWrap: "wrap", alignItems: "center" }}>
              <Button variant="primary" onClick={() => side.current?.querySelector("button")?.focus()}>Open a sample console</Button>
              <Link to="/technical" className="link">Read the technical approach</Link>
              <Link to="/tour" className="link">Take the guided tour</Link>
            </div>

            <Block id="offer" title="What your security team gets"><Items items={OFFER} /></Block>
            <Block id="evidence" title="How we collect evidence"
                   intro="Every confirmed domain comes with a bundle anyone can check, in six steps."><Steps items={EVIDENCE} /></Block>
            <section className="landing-block" aria-label="Pipeline"><PipelineDiagram /></section>
            <Block id="after" title="After a phishing domain is confirmed"><Steps items={AFTER} /></Block>
            <Block id="security" title="Security and isolation"><Items items={SECURITY} /></Block>
            <Block id="roadmap" title="On the roadmap" intro="Not built yet. Listed so you can see where the product is going.">
              <Items items={ROADMAP} />
            </Block>
            <p className="prose ink-2 landing-intro" style={{ marginTop: 48 }}>{POSITIONING}</p>
          </div>
          <div ref={side}><TryTheConsole /></div>
        </div>
      </main>
      <Drawer open={open === "signin"} title="Super admin sign-in" onClose={() => setOpen(null)}><SuperAdminSignIn /></Drawer>
      <Drawer open={open === "access"} title="Request access" onClose={() => setOpen(null)}><RequestAccess /></Drawer>
    </>
  );
}
