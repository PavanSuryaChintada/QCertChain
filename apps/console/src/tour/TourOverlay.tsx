import { useEffect, useId, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "../components/Button";
import { useTour } from "./TourProvider";

/** How long a step waits before saying its element is missing. It keeps looking after that: a cold campaign graph
 *  can take seconds, and the highlight appears whenever the element does. */
export const TARGET_WAIT_MS = 8000;
const PAD = 4;
// Above the rail and top bar (z 20), below drawers (z 30): an opened ? panel covers the card, closing it shows the card.
const Z_HIGHLIGHT = 24;
const Z_CARD = 25;
// Controls that use the arrow keys themselves: the tour leaves them alone.
const ARROW_OWNERS = 'input, textarea, select, [contenteditable="true"], [role="radiogroup"], [role="slider"], [role="grid"], table';

export function TourOverlay({ waitMs = TARGET_WAIT_MS }: { waitMs?: number }) {
  const t = useTour();
  const { pathname, search } = useLocation();
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [missing, setMissing] = useState(false);
  const { active, index } = t.state;
  const step = t.steps[index];

  // Find the step's element, waiting for the page's data; then follow it through scrolling, resizing and layout shifts.
  useEffect(() => {
    if (!active) return;
    setRect(null);
    setMissing(false);
    let el: Element | null = null;
    let timer = 0;
    const deadline = Date.now() + waitMs;
    const measure = () => { if (el) setRect(el.getBoundingClientRect()); };
    const find = () => {
      el = document.querySelector(`[data-tour="${step.target}"]`);
      if (el) {
        setMissing(false);
        el.scrollIntoView?.({ block: "center" });
        measure();
        return;
      }
      const late = Date.now() >= deadline;
      if (late) setMissing(true);
      timer = window.setTimeout(find, late ? 250 : 100);
    };
    find();
    const follow = window.setInterval(measure, 500);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(timer);
      window.clearInterval(follow);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [active, index, step.target, pathname, search, waitMs]);

  useEffect(() => { if (active) heading.current?.focus(); }, [active, index]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (document.querySelector(".drawer")) return; // Esc closes the open drawer first
        e.preventDefault();
        t.exit();
        return;
      }
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      if ((e.target as Element | null)?.closest?.(ARROW_OWNERS)) return;
      e.preventDefault();
      if (e.key === "ArrowRight") t.next();
      else t.back();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [active, t]);

  if (!active) return null;
  const last = index === t.steps.length - 1;
  const counter = `Step ${index + 1} of ${t.steps.length}`;
  return (
    <>
      {rect && (
        <div data-testid="tour-highlight" aria-hidden="true"
             style={{ position: "fixed", top: rect.top - PAD, left: rect.left - PAD, width: rect.width + 2 * PAD,
                      height: rect.height + 2 * PAD, outline: "2px solid var(--focus)", pointerEvents: "none", zIndex: Z_HIGHLIGHT }} />
      )}
      <section className="overlay panel" role="dialog" aria-modal="false" aria-labelledby={`${id}-title`}
               style={{ position: "fixed", right: 24, bottom: 24, width: 380, zIndex: Z_CARD }}>
        <div className="panel-body">
          <p className="sr-only" aria-live="polite">{`${counter}: ${step.title}`}</p>
          <p className="t-label">{counter}</p>
          <h2 id={`${id}-title`} ref={heading} tabIndex={-1} className="t-section" style={{ marginTop: 4 }}>{step.title}</h2>
          <p className="prose" style={{ marginTop: 8 }}>{step.body(t.state.ctx)}</p>
          {missing && <p className="prose ink-2" style={{ marginTop: 8 }} data-testid="tour-missing">{step.missing}</p>}
          <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
            <Button size="sm" variant="ghost" onClick={t.exit}>Exit</Button>
            <Button size="sm" onClick={t.back} disabled={index === 0} disabledReason="This is the first step">Back</Button>
            <Button size="sm" variant="primary" onClick={t.next}>{last ? "Finish" : "Next step"}</Button>
          </div>
        </div>
      </section>
    </>
  );
}
