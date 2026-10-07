import type { ReactNode } from "react";

export function PageHeader({ title, meta, actions }: { title: ReactNode; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
      <div style={{ minWidth: 0 }}>
        <h1 className="t-display">{title}</h1>
        {meta && <div className="t-meta" style={{ marginTop: 4 }}>{meta}</div>}
      </div>
      {actions && <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>{actions}</div>}
    </div>
  );
}

export function Section({ title, aside, children, id }: { title: ReactNode; aside?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="panel" aria-labelledby={id} style={{ marginBottom: 24 }}>
      <div className="panel-head">
        <h2 id={id} className="t-section">{title}</h2>
        {aside && <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{aside}</div>}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

/** Label over value: the standard fact block. */
export function Fact({ label, children, big = false }: { label: string; children: ReactNode; big?: boolean }) {
  return (
    <div>
      <p className="t-label">{label}</p>
      <p className={big ? "t-display mono" : "t-data"} style={{ marginTop: 4 }}>{children}</p>
    </div>
  );
}
