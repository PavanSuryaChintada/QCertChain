import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "../components/Button";
import { Drawer } from "../components/Drawer";
import { HELP, helpKeyFor, type HelpEntry, type HelpKey } from "./content";

export function HelpBody({ entry }: { entry: HelpEntry }) {
  return (
    <div className="prose">
      <h3 className="t-section">What this page is</h3>
      <p style={{ marginTop: 8 }}>{entry.what}</p>
      <h3 className="t-section" style={{ marginTop: 24 }}>How to read it</h3>
      <dl style={{ marginTop: 8 }}>
        {entry.read.map((r) => (
          <div key={r.label} style={{ marginTop: 12 }}>
            <dt style={{ fontWeight: 500 }}>{r.label}</dt>
            <dd className="ink-2" style={{ marginTop: 4 }}>{r.text}</dd>
          </div>
        ))}
      </dl>
      <h3 className="t-section" style={{ marginTop: 24 }}>Where the data comes from</h3>
      <p style={{ marginTop: 8 }}>{entry.data}</p>
      <h3 className="t-section" style={{ marginTop: 24 }}>What it does not claim</h3>
      <p style={{ marginTop: 8 }}>{entry.notClaimed}</p>
    </div>
  );
}

/** The ? that explains the current page. `entryKey` pins an entry for screens outside the routes (sign-in). */
export function HelpButton({ entryKey }: { entryKey?: HelpKey }) {
  const { pathname } = useLocation();
  const key = entryKey ?? helpKeyFor(pathname);
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [pathname]);
  if (!key) return null;
  const entry = HELP[key];
  return (
    <>
      <Button size="sm" iconLabel={`Help: ${entry.title}`} onClick={() => setOpen(true)} data-testid="help-button">?</Button>
      <Drawer open={open} title={`About this page: ${entry.title}`} onClose={() => setOpen(false)}>
        <HelpBody entry={entry} />
      </Drawer>
    </>
  );
}
