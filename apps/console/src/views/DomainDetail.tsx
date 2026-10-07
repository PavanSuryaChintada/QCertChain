import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type DomainDetail as D, type Signal } from "../lib/api";
import { VerdictChip } from "../components/VerdictChip";
import { Hash, Num } from "../components/Mono";
import { EvidenceViewer } from "./EvidenceViewer";

const FEATURE_TEXT: Record<string, string> = {
  brand_token_exact: "brand name in the domain", lookalike: "spelled like a brand", homoglyph_hit: "look-alike characters",
  tld_risk: "high-risk top-level domain", keyword_count: "phishing keywords", shape: "long or hyphen-heavy name",
  allowlisted: "on the allowlist", public_suffix: "a public suffix", cap: "capped at 1.0",
};

function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k.replace(/_/g, " ")} ${x}`).join(", ");
  return String(v);
}

export function SignalList({ signals }: { signals: Signal[] }) {
  if (!signals.length) return <p className="secondary">No signals.</p>;
  return (
    <ul className="mt-2">
      {signals.map((s, i) => (
        <li key={i} className="grid gap-3 py-1" style={{ gridTemplateColumns: "88px 1fr" }}>
          <span className="mono text-12" style={{ color: s.strength === "strong" ? "var(--ink-000)" : "var(--ink-200)" }}>
            {s.strength}
          </span>
          <span><span className="text-ink-0">{s.name.replace(/_/g, " ")}</span>
            <span className="secondary block mono" style={{ fontSize: 12 }}>{s.detail}</span></span>
        </li>
      ))}
    </ul>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-3 py-1 rule-b" style={{ gridTemplateColumns: "140px 1fr" }}>
      <span className="secondary">{k}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

function Verdict({ d }: { d: D }) {
  const c = d.confirmation;
  const sentence =
    d.status === "candidate" ? "Candidate — not yet verified. A name match is an observation, not an accusation."
    : d.status === "unreachable" ? "Could not reach — still a candidate."
    : d.status === "dismissed" ? "Dismissed — no evidence of phishing on the page."
    : "Confirmed on evidence: at least two independent strong signals.";
  return (
    <section className="p-4 rule-b">
      <div className="flex items-center gap-4">
        <VerdictChip status={d.status} strongCount={c?.strong_count} />
        {c?.confidence != null && c.signals.length > 0 && (
          <span className="secondary">confidence <Num v={c.confidence} digits={2} /> from {c.signals.length} signals below</span>
        )}
      </div>
      <p className="mt-2">{sentence}</p>
      {c && <SignalList signals={c.signals} />}
    </section>
  );
}

export function DomainDetail({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["domain", id], queryFn: () => api.domain(id), refetchInterval: 5000 });
  const reconfirm = useMutation({ mutationFn: () => api.reconfirm(id) });
  if (q.isError) return <p className="p-6">This domain could not be loaded: {(q.error as Error).message}</p>;
  if (!q.data) return <div className="solving" />;
  const d = q.data;
  const e = d.enrichment;
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)" }}>
      <div className="rule-r min-w-0">
        <header className="p-4 rule-b">
          {/* full name, wrapped — never truncated: the characters ARE the evidence in a look-alike */}
          <span className="mono block" style={{ fontSize: 22, color: "var(--ink-000)", wordBreak: "break-all" }}>{d.name}</span>
          <span className="secondary">registrable domain <span className="mono">{d.etld1}</span> · source {d.source}
            {d.source === "seed" && " (synthetic demo data)"} · first seen {new Date(d.first_seen).toISOString().slice(0, 19)}Z</span>
          <div className="mt-3 flex gap-2">
            <button onClick={() => reconfirm.mutate()} disabled={reconfirm.isPending || reconfirm.isSuccess}>
              {reconfirm.isSuccess ? "Re-check queued" : "Re-check the page"}
            </button>
            {d.campaign_id && <Link to={`/?campaign=${d.campaign_id}`}><button>Open campaign</button></Link>}
          </div>
        </header>
        <Verdict d={d} />
        <section className="p-4 rule-b">
          <p className="panel-title">Why it was flagged</p>
          <p className="secondary">
            Triage score <Num v={d.triage.score} digits={2} /> against threshold <Num v={d.triage.threshold} digits={2} /> ·{" "}
            {d.triage.provenance === "rules" ? "hand-set rule weights" : "trained model"}
          </p>
          <ul className="mt-2">
            {d.triage.reasons.map((r, i) => (
              <li key={i} className="flex justify-between py-1">
                <span>{FEATURE_TEXT[r.feature] ?? r.feature} <span className="mono secondary">{fmtValue(r.value)}</span></span>
                <Num v={r.contribution} digits={2} />
              </li>
            ))}
          </ul>
        </section>
        {e && (
          <section className="p-4">
            <p className="panel-title">Infrastructure</p>
            {e.partial && <p className="secondary">Partial: {Object.entries(e.errors ?? {}).map(([k, v]) => `${k} (${v})`).join("; ")}</p>}
            <div className="mt-2">
              <Row k="IP addresses"><span className="mono">{e.ip_addresses.join(", ") || "—"}</span></Row>
              <Row k="ASN"><span className="mono">{e.asn ? `AS${e.asn} ${e.asn_name ?? ""}` : "—"}</span></Row>
              <Row k="Nameservers"><span className="mono">{e.nameservers.join(", ") || "—"}</span></Row>
              <Row k="Registrar">{e.registrar ?? "—"}</Row>
              <Row k="Registered">{e.registered_at ? new Date(e.registered_at).toISOString().slice(0, 10) : "—"}</Row>
              <Row k="Certificate issuer">{e.cert_issuer ?? "—"}</Row>
              <Row k="Kit fingerprint"><Hash v={e.dom_hash} n={24} /></Row>
              <Row k="Favicon hash"><Hash v={e.favicon_hash} /></Row>
            </div>
          </section>
        )}
      </div>
      <div className="min-w-0">
        {d.confirmation?.screenshot_url && (
          <figure className="p-4 rule-b">
            <Screenshot path={d.confirmation.screenshot_url} alt={`Screenshot of ${d.name} as fetched`} />
            <figcaption className="secondary mt-1">Captured page. Fetched and observed only — no form was touched.</figcaption>
          </figure>
        )}
        {d.evidence_bundle_id ? <EvidenceViewer bundleId={d.evidence_bundle_id} />
          : <p className="p-4 secondary">No evidence bundle: bundles are built only for confirmed domains.</p>}
      </div>
    </div>
  );
}

/** The artifact endpoint needs the API key, so the image is fetched and shown from a blob URL. */
function Screenshot({ path, alt }: { path: string; alt: string }) {
  const q = useQuery({ queryKey: ["artifact", path], queryFn: () => api.artifactBlobUrl(path), staleTime: Infinity });
  if (q.isError) return <p className="secondary">Screenshot unavailable.</p>;
  if (!q.data) return <p className="secondary">Loading screenshot.</p>;
  return <img src={q.data} alt={alt} style={{ width: "100%", border: "1px solid var(--ground-300)" }} />;
}
