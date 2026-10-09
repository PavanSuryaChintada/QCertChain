import { Link } from "react-router-dom";
import { PageHeader, Section } from "../components/Page";
import { TECHNICAL } from "../explain/technical";
import { PipelineDiagram } from "../components/PipelineDiagram";

/** How the system works and why. Open without a key; measured figures live on the Metrics page, not here. */
export function TechnicalPage() {
  return (
    <div>
      <PageHeader title="Technical approach" meta="How QCertChain works and why it is built this way. Measured results are on the Metrics page." />
      <section className="panel" style={{ padding: 16, marginBottom: 24 }} aria-label="Pipeline diagram">
        <PipelineDiagram />
      </section>
      {TECHNICAL.map((s) => (
        <Section key={s.id} id={`tech-${s.id}`} title={s.title}
                 aside={s.live && <Link className="btn btn-sm" to={s.live.to}>{s.live.label}</Link>}>
          {s.paragraphs.map((p, i) => <p key={i} className="prose" style={{ marginTop: i === 0 ? 0 : 12 }}>{p}</p>)}
        </Section>
      ))}
      <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <Link className="btn btn-primary" to="/tour">Start the guided tour</Link>
        <span className="prose ink-2">Each step opens the real page and highlights the part that matters.</span>
      </div>
    </div>
  );
}
