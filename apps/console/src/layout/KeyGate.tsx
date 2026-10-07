import { type ReactNode, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getKey, onKeyChange, setKey } from "../lib/auth";

/** Nothing renders without an API key: the key decides which organisation's data exists. */
export function KeyGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [key, setLocal] = useState(getKey());
  const [draft, setDraft] = useState("");
  useEffect(() => onKeyChange(() => { setLocal(getKey()); qc.clear(); }), [qc]);
  if (key) return <>{children}</>;
  return (
    <main style={{ padding: 48, maxWidth: 640 }}>
      <h1 className="t-display">QCertChain console</h1>
      <p className="ink-2 prose" style={{ marginTop: 8 }}>
        Enter your organisation's API key. The key decides which organisation you are: its campaigns, evidence and
        analyses are the only ones that exist for you. To switch organisation, sign out and use another key.
      </p>
      <form style={{ marginTop: 24, display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setKey(draft.trim()); }}>
        <label htmlFor="apikey" className="sr-only">API key</label>
        <input id="apikey" className="input mono" style={{ flex: 1 }} type="password" autoComplete="off" placeholder="qcc_org_..."
               value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>Sign in</button>
      </form>
    </main>
  );
}
