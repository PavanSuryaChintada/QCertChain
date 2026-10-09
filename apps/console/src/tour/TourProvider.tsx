import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { STEPS, resolveCtx, type TourCtx, type TourReads, type TourStep } from "./steps";

const STORAGE = "qcertchain.tour";

export interface TourState { active: boolean; index: number; ctx: TourCtx }
const IDLE: TourState = { active: false, index: 0, ctx: {} };

// Per tab: a reload (or signing in) resumes the tour where it was. Blocked storage means memory only.
function load(): TourState {
  try {
    const raw = window.sessionStorage.getItem(STORAGE);
    if (raw) return { ...IDLE, ...(JSON.parse(raw) as Partial<TourState>) };
  } catch {
    /* blocked or corrupt: start idle */
  }
  return IDLE;
}

function save(s: TourState): void {
  try {
    if (s.active) window.sessionStorage.setItem(STORAGE, JSON.stringify(s));
    else window.sessionStorage.removeItem(STORAGE);
  } catch {
    /* blocked: memory only */
  }
}

export interface Tour {
  state: TourState;
  steps: TourStep[];
  starting: boolean;
  start: () => Promise<void>;
  next: () => void;
  back: () => void;
  exit: () => void;
}

const TourContext = createContext<Tour | null>(null);

/** Sits above the sign-in gate so the tour survives signing in. Navigation happens in the actions, never in effects. */
export function TourProvider({ children, reads = api }: { children: ReactNode; reads?: TourReads }) {
  const nav = useNavigate();
  const [state, setState] = useState<TourState>(load);
  const [starting, setStarting] = useState(false);
  // Refs keep every action's identity stable across navigation (useNavigate's function changes with the location).
  const cur = useRef(state);
  cur.current = state;
  const navRef = useRef(nav);
  navRef.current = nav;
  const readsRef = useRef(reads);
  readsRef.current = reads;
  const busy = useRef(false);

  const go = useCallback((s: TourState) => {
    setState(s);
    save(s);
    if (s.active) navRef.current(STEPS[s.index].route(s.ctx));
  }, []);

  const start = useCallback(async () => {
    if (busy.current) return; // StrictMode runs effects twice; one tour at a time
    busy.current = true;
    setStarting(true);
    try {
      go({ active: true, index: 0, ctx: await resolveCtx(readsRef.current) });
    } finally {
      busy.current = false;
      setStarting(false);
    }
  }, [go]);

  const exit = useCallback(() => go(IDLE), [go]);
  const next = useCallback(() => {
    const s = cur.current;
    if (!s.active) return;
    if (s.index >= STEPS.length - 1) exit();
    else go({ ...s, index: s.index + 1 });
  }, [go, exit]);
  const back = useCallback(() => {
    const s = cur.current;
    if (s.active && s.index > 0) go({ ...s, index: s.index - 1 });
  }, [go]);

  const value = useMemo<Tour>(() => ({ state, steps: STEPS, starting, start, next, back, exit }),
    [state, starting, start, next, back, exit]);
  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

export function useTour(): Tour {
  const t = useContext(TourContext);
  if (!t) throw new Error("useTour must be used inside TourProvider");
  return t;
}
