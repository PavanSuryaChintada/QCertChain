import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export interface DropdownOption<V extends string> { value: V; label: string }

/**
 * A custom listbox (not a native select). Closed: Enter / Space / ArrowDown / ArrowUp open it.
 * Open: arrows move, Home / End jump, Enter selects, Esc closes, typing jumps to the next matching label.
 */
export function Dropdown<V extends string>({ label, options, value, onChange, hideLabel = false }: {
  label: string;
  options: DropdownOption<V>[];
  value: V;
  onChange: (v: V) => void;
  hideLabel?: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const selectedIdx = Math.max(0, options.findIndex((o) => o.value === value));
  const [active, setActive] = useState(selectedIdx);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const typed = useRef({ buf: "", at: 0 });

  useEffect(() => {
    if (open) {
      typed.current = { buf: "", at: 0 };
      setActive(selectedIdx);
      list.current?.focus();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (open) list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open]);

  const close = (focusButton = true) => {
    setOpen(false);
    if (focusButton) button.current?.focus();
  };
  const choose = (i: number) => {
    const o = options[i];
    if (o) onChange(o.value);
    close();
  };

  const typeAhead = (ch: string) => {
    const now = Date.now();
    const t = typed.current;
    t.buf = now - t.at > 600 ? ch : t.buf + ch;
    t.at = now;
    const q = t.buf.toLowerCase();
    const from = t.buf.length === 1 ? active + 1 : active;
    for (let n = 0; n < options.length; n++) {
      const i = (from + n) % options.length;
      if (options[i].label.toLowerCase().startsWith(q)) { setActive(i); return; }
    }
  };

  const onButtonKey = (e: KeyboardEvent) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      setOpen(true);
    }
  };

  const onListKey = (e: KeyboardEvent) => {
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); setActive((a) => Math.min(options.length - 1, a + 1)); break;
      case "ArrowUp": e.preventDefault(); setActive((a) => Math.max(0, a - 1)); break;
      case "Home": e.preventDefault(); setActive(0); break;
      case "End": e.preventDefault(); setActive(options.length - 1); break;
      case "Enter": case " ": e.preventDefault(); choose(active); break;
      case "Escape": e.preventDefault(); close(); break;
      case "Tab": close(false); break;
      default:
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); typeAhead(e.key); }
    }
  };

  return (
    <div className="dd" ref={wrap}>
      <span id={`${id}-label`} className={hideLabel ? "sr-only" : "t-meta"} style={hideLabel ? undefined : { marginRight: 8 }}>{label}</span>
      <button
        ref={button}
        type="button"
        className="btn dd-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={`${id}-label ${id}-value`}
        onClick={() => (open ? close() : setOpen(true))}
        onKeyDown={onButtonKey}
      >
        <span id={`${id}-value`}>{options[selectedIdx]?.label ?? ""}</span>
        <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true"><path d="M0 2 L4 6 L8 2" fill="none" stroke="currentColor" strokeWidth="1.25" /></svg>
      </button>
      {open && (
        <ul
          ref={list}
          role="listbox"
          tabIndex={-1}
          className="dd-menu overlay"
          aria-labelledby={`${id}-label`}
          aria-activedescendant={`${id}-opt-${active}`}
          onKeyDown={onListKey}
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${id}-opt-${i}`}
              data-index={i}
              role="option"
              aria-selected={o.value === value}
              data-active={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(i)}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
