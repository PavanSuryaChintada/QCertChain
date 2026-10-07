import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Severity } from "../lib/status";
import { RowBar } from "./StatusIndicator";

export interface Column<T> {
  key: string;
  header: ReactNode;
  width?: number | string;
  align?: "left" | "right";
  mono?: boolean;
  render: (row: T) => ReactNode;
  title?: (row: T) => string | undefined;
}

export interface TableProps<T> {
  label: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onOpen?: (row: T) => void;
  onHoverRow?: (row: T) => void;
  selectedKey?: string | number | null;
  density?: "default" | "compact";
  rowBar?: (row: T) => Severity | null;
  flashKeys?: ReadonlySet<string | number>;
  /** Virtualise when there are more rows than this. The scroll container then needs `maxHeight`. */
  virtualizeAbove?: number;
  maxHeight?: string;
  onPointerInside?: (inside: boolean) => void;
  caption?: ReactNode;
}

const OVERSCAN = 12;

/**
 * Keyboard path: Tab reaches the table (one roving tab stop), arrows/Home/End/PageUp/PageDown move through rows,
 * Enter opens. The opener (drawer or page) restores focus to the row when it closes.
 */
export function Table<T>(p: TableProps<T>) {
  const rowH = p.density === "compact" ? 24 : 40;
  const [active, setActive] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewH, setViewH] = useState(800);
  const scroller = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLTableSectionElement>(null);
  const pendingFocus = useRef<number | null>(null);
  const virtual = p.virtualizeAbove !== undefined && p.rows.length > p.virtualizeAbove;

  useEffect(() => {
    if (active > p.rows.length - 1) setActive(Math.max(0, p.rows.length - 1));
  }, [p.rows.length, active]);

  useLayoutEffect(() => {
    if (scroller.current && virtual) setViewH(scroller.current.clientHeight || 800);
  }, [virtual]);

  let start = 0;
  let end = p.rows.length;
  if (virtual) {
    start = Math.max(0, Math.floor(scrollTop / rowH) - OVERSCAN);
    end = Math.min(p.rows.length, Math.ceil((scrollTop + viewH) / rowH) + OVERSCAN);
  }

  useLayoutEffect(() => {
    const i = pendingFocus.current;
    if (i === null) return;
    const el = body.current?.querySelector<HTMLTableRowElement>(`tr[data-index="${i}"]`);
    if (el) {
      el.focus();
      pendingFocus.current = null;
    }
  });

  const move = (i: number) => {
    const n = Math.max(0, Math.min(p.rows.length - 1, i));
    setActive(n);
    pendingFocus.current = n;
    if (virtual && scroller.current) {
      const top = n * rowH;
      const s = scroller.current;
      if (top < s.scrollTop) s.scrollTop = top;
      else if (top + rowH > s.scrollTop + s.clientHeight - 32) s.scrollTop = top + rowH - s.clientHeight + 32;
      setScrollTop(s.scrollTop);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, i: number, row: T) => {
    const page = Math.max(1, Math.floor((viewH - 32) / rowH));
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); move(i + 1); break;
      case "ArrowUp": e.preventDefault(); move(i - 1); break;
      case "Home": e.preventDefault(); move(0); break;
      case "End": e.preventDefault(); move(p.rows.length - 1); break;
      case "PageDown": e.preventDefault(); move(i + page); break;
      case "PageUp": e.preventDefault(); move(i - page); break;
      case "Enter": e.preventDefault(); p.onOpen?.(row); break;
    }
  };

  const visible = p.rows.slice(start, end);
  const table = (
    <table className={`tbl${p.density === "compact" ? " compact" : ""}`} aria-label={p.label} aria-rowcount={p.rows.length + 1}>
      {p.caption && <caption className="sr-only">{p.caption}</caption>}
      <colgroup>
        {p.columns.map((c) => <col key={c.key} style={{ width: c.width }} />)}
      </colgroup>
      <thead>
        <tr>
          {p.columns.map((c) => (
            <th key={c.key} scope="col" className={c.align === "right" ? "num" : undefined}>{c.header}</th>
          ))}
        </tr>
      </thead>
      <tbody ref={body}>
        {virtual && start > 0 && <tr aria-hidden="true" style={{ height: start * rowH }} />}
        {visible.map((row, j) => {
          const i = start + j;
          const key = p.rowKey(row);
          const sev = p.rowBar?.(row) ?? null;
          return (
            <tr
              key={key}
              data-index={i}
              data-key={key}
              aria-rowindex={i + 2}
              aria-selected={p.selectedKey !== undefined ? p.selectedKey === key : undefined}
              data-interactive={p.onOpen ? "true" : undefined}
              tabIndex={i === active ? 0 : -1}
              className={p.flashKeys?.has(key) ? "row-flash" : undefined}
              onClick={() => { setActive(i); p.onOpen?.(row); }}
              onFocus={() => setActive(i)}
              onMouseEnter={() => p.onHoverRow?.(row)}
              onKeyDown={(e) => onKey(e, i, row)}
            >
              {p.columns.map((c, ci) => (
                <td
                  key={c.key}
                  className={[ci === 0 && sev ? "has-bar" : "", c.align === "right" ? "num" : "", c.mono ? "mono" : ""].filter(Boolean).join(" ") || undefined}
                  title={c.title?.(row)}
                  style={ci === 0 && sev ? { paddingLeft: p.density === "compact" ? 12 : 16 } : undefined}
                >
                  {ci === 0 && sev && <RowBar severity={sev} />}
                  {c.render(row)}
                </td>
              ))}
            </tr>
          );
        })}
        {virtual && end < p.rows.length && <tr aria-hidden="true" style={{ height: (p.rows.length - end) * rowH }} />}
      </tbody>
    </table>
  );

  return (
    <div
      ref={scroller}
      className="panel"
      style={virtual || p.maxHeight ? { maxHeight: p.maxHeight, overflowY: "auto" } : undefined}
      onScroll={virtual ? (e) => setScrollTop((e.target as HTMLDivElement).scrollTop) : undefined}
      onPointerEnter={() => p.onPointerInside?.(true)}
      onPointerLeave={() => p.onPointerInside?.(false)}
    >
      {table}
    </div>
  );
}
