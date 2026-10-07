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
    <div className="p-8 max-w-[560px]">
      <p className="panel-title" style={{ fontSize: 22 }}>QCertChain</p>
      <p className="secondary mt-2">
        Enter your organisation's API key. It decides which organisation's campaigns, evidence and analyses you see;
        another organisation's data does not exist for you.
      </p>
      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setKey(draft.trim()); }}>
        <label htmlFor="apikey" className="sr-only">API key</label>
        <input id="apikey" className="flex-1 mono" type="password" autoComplete="off" placeholder="qcc_org_…"
               value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button type="submit" disabled={!draft.trim()}>Sign in</button>
      </form>
    </div>
  );
}
