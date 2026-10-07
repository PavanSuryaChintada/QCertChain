import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button";

/** Detail opens in a right drawer (520px), not a modal, so the list stays visible. Esc closes; focus returns. */
export function Drawer({ open, title, onClose, children }: { open: boolean; title: ReactNode; onClose: () => void; children: ReactNode }) {
  const id = useId();
  const closeBtn = useRef<HTMLButtonElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    returnTo.current = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); closeRef.current(); } };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const el = returnTo.current;
      if (el && document.contains(el)) el.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <aside className="drawer overlay" role="dialog" aria-modal="false" aria-labelledby={`${id}-title`}>
      <div className="drawer-head">
        <h2 id={`${id}-title`} className="t-section" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</h2>
        <Button ref={closeBtn} size="sm" onClick={onClose} title="Close (Esc)">Close</Button>
      </div>
      <div className="drawer-body">{children}</div>
    </aside>
  );
}
