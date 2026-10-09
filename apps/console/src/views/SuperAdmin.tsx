import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../components/Button";
import { Dropdown } from "../components/Dropdown";
import { PageHeader, Section } from "../components/Page";
import { HelpButton } from "../help/HelpPanel";
import { api, CATEGORIES, categoryLabel, toApiError, type Category, type NewOrg, type OrgKeys, type SuperOrg } from "../lib/api";
import { setKey } from "../lib/auth";
import { fmtDateTime } from "../lib/format";

/** The pipeline organisation: live candidates are confirmed on its behalf, so it cannot be deactivated. */
const PIPELINE_ORG = "org1";

function KeyLine({ label, value }: { label: string; value: string | null }) {
  return (
    <div style={{ marginTop: 8 }}>
      <p className="t-label">{label}</p>
      <p className="mono" style={{ marginTop: 4, overflowWrap: "anywhere", userSelect: "all" }}>
        {value ?? "Not stored. Rotate to issue a new one."}
      </p>
    </div>
  );
}

function OrgRow({ o, keys, onKeys, onOpen, onRotate, onDeactivate }: {
  o: SuperOrg; keys?: OrgKeys; onKeys: () => void; onOpen: () => void;
  onRotate: (kind: "org" | "demo") => void; onDeactivate: () => void;
}) {
  return (
    <section className="panel panel-body" style={{ marginTop: 8 }}>
      <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ minWidth: 220, flex: 1 }}>
          <p style={{ fontWeight: 500 }}>{o.name}</p>
          <p className="t-meta">
            <span>{categoryLabel(o.category)}</span> · <span className="mono">{o.slug}</span> · {o.active ? "active" : "deactivated"}
            {o.created_at && <> · created {fmtDateTime(o.created_at)}</>} · {o.live_keys} live keys
          </p>
        </div>
        {o.active && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button size="sm" variant="primary" iconLabel={`Open console as ${o.name}`} onClick={onOpen}>Open console</Button>
            <Button size="sm" iconLabel={`Show keys of ${o.name}`} onClick={onKeys}>Keys</Button>
            <Button size="sm" iconLabel={`Rotate the full key of ${o.name}`} onClick={() => onRotate("org")}>Rotate full key</Button>
            <Button size="sm" iconLabel={`Rotate the read-only key of ${o.name}`} onClick={() => onRotate("demo")}>Rotate read-only key</Button>
            <Button size="sm" variant="ghost" iconLabel={`Deactivate ${o.name}`} onClick={onDeactivate} disabled={o.slug === PIPELINE_ORG}
                    disabledReason="Live candidates are confirmed on its behalf, so it stays active.">Deactivate</Button>
          </div>
        )}
      </div>
      {keys && (
        <div style={{ marginTop: 8 }}>
          <KeyLine label="Full key (share privately)" value={keys.org_key} />
          <KeyLine label="Read-only key (shown on the sign-in page)" value={keys.demo_key} />
        </div>
      )}
    </section>
  );
}

/** The platform panel (spec 2026-10-09 §8): rendered instead of an organisation's console for a super admin session. */
export function SuperAdminPage() {
  const qc = useQueryClient();
  const orgs = useQuery({ queryKey: ["superadmin-orgs"], queryFn: ({ signal }) => api.superOrgs(signal), retry: 1 });
  const [name, setName] = useState("");
  const [category, setCategory] = useState<Category>("banking");
  const [made, setMade] = useState<NewOrg | null>(null);
  const [shown, setShown] = useState<Record<string, OrgKeys>>({});
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["superadmin-orgs"] });
  const fail = (e: unknown) => setError(toApiError(e).problem.detail ?? toApiError(e).problem.title);

  const create = useMutation({
    mutationFn: () => api.createOrg(name.trim(), category),
    onSuccess: (o) => { setMade(o); setName(""); setError(null); void refresh(); },
    onError: fail,
  });
  const showKeys = async (slug: string) => {
    try { setShown({ ...shown, [slug]: await api.orgKeys(slug) }); } catch (e) { fail(e); }
  };
  const openAs = async (o: SuperOrg) => {
    try {
      const k = await api.orgKeys(o.slug);
      if (k.org_key) setKey(k.org_key);
      else setError(`The full key of ${o.name} is not stored. Rotate it first.`);
    } catch (e) { fail(e); }
  };
  const rotate = async (o: SuperOrg, kind: "org" | "demo") => {
    try { await api.rotateKey(o.slug, kind); await showKeys(o.slug); void refresh(); } catch (e) { fail(e); }
  };
  const deactivate = async (o: SuperOrg) => {
    try { await api.deactivateOrg(o.slug); void refresh(); } catch (e) { fail(e); }
  };
  const signOut = async () => {
    try { await api.logout(); } catch { /* the session expires on its own in any case */ }
    setKey(null);
  };

  return (
    <>
      <header className="topbar" style={{ left: 0 }}>
        <span style={{ fontWeight: 500 }}>QCertChain platform</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
          <span className="t-meta">Super admin</span>
          <Button size="sm" onClick={signOut}>Sign out</Button>
          <HelpButton entryKey="superadmin" />
        </div>
      </header>
      <main className="main" style={{ marginLeft: 0 }}>
        <div className="content">
          <PageHeader title="Organisations" meta="Create an organisation for any sector. It signs in with its own key and sees only its own data." />
          {error && <p className="stale-bar" role="alert">{error}</p>}
          <Section id="sec-new-org" title="New organisation">
            <form style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}
                  onSubmit={(e) => { e.preventDefault(); if (name.trim().length >= 2) create.mutate(); }}>
              <div style={{ flex: 1, minWidth: 240 }}>
                <label htmlFor="org-name" className="t-label">Organisation name</label>
                <input id="org-name" className="input" style={{ width: "100%", marginTop: 4 }} value={name}
                       placeholder="ShopSafe SOC" onChange={(e) => setName(e.target.value)} />
              </div>
              <Dropdown<Category> label="Category" value={category} onChange={setCategory} options={CATEGORIES} />
              <Button type="submit" variant="primary" disabled={name.trim().length < 2 || create.isPending}
                      disabledReason="Type a name of at least two characters.">Create organisation</Button>
            </form>
            <p className="prose ink-2" style={{ marginTop: 12 }}>
              A new organisation sees the shared certificate feed now. Its own sector feed and a seeded demo campaign
              arrive with the next update.
            </p>
            {made && (
              <div className="panel panel-body" style={{ marginTop: 12 }} data-testid="new-org-keys">
                <p style={{ fontWeight: 500 }}>Keys for {made.name} ({categoryLabel(made.category)})</p>
                <KeyLine label="Full key (share privately)" value={made.org_key} />
                <KeyLine label="Read-only key (shown on the sign-in page)" value={made.demo_key} />
              </div>
            )}
          </Section>
          <Section id="sec-orgs" title="All organisations">
            {orgs.isLoading && <p className="t-meta">Loading organisations</p>}
            {orgs.error && <p className="t-meta">The organisation list is unavailable: {toApiError(orgs.error).problem.title}.</p>}
            {orgs.data?.map((o) => (
              <OrgRow key={o.slug} o={o} keys={shown[o.slug]} onKeys={() => showKeys(o.slug)} onOpen={() => openAs(o)}
                      onRotate={(k) => rotate(o, k)} onDeactivate={() => deactivate(o)} />
            ))}
          </Section>
        </div>
      </main>
    </>
  );
}
