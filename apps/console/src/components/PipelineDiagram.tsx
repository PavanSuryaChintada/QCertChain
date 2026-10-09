import { Fragment } from "react";
import { PIPELINE } from "../explain/landing";

/** The pipeline in three lanes, each stage with what it does and why it is there. Plain HTML so the words wrap and
 *  read at any width; arrows are decoration (aria-hidden), the order is the list order. */
export function PipelineDiagram() {
  return (
    <figure className="flow" aria-labelledby="flow-caption">
      <figcaption id="flow-caption" className="landing-h2">How the pipeline works</figcaption>
      {PIPELINE.map((lane) => (
        <div key={lane.lane} className="flow-lane">
          <p className="flow-lane-name">{lane.lane}</p>
          <ol className="flow-steps">
            {lane.stages.map((s, i) => (
              <Fragment key={s.name}>
                {i > 0 && <li className="flow-arrow" aria-hidden="true">→</li>}
                <li className="flow-step">
                  <p className="flow-name">{s.name}</p>
                  <p className="flow-what">{s.what}</p>
                  <p className="flow-why">{s.why}</p>
                </li>
              </Fragment>
            ))}
          </ol>
        </div>
      ))}
    </figure>
  );
}
