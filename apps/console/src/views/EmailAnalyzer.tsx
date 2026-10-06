import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type EmailAnalysis } from "../lib/api";
import { VerdictChip } from "../components/VerdictChip";
import { SignalList } from "./DomainDetail";

const VERDICT_TEXT = {
  malicious: "Malicious: at least two independent strong signals.",
  suspicious: "Suspicious — not verified. Fewer than two strong signals; nothing here is an accusation yet.",
  clean: "No signals found in the headers.",
};

function Result({ a }: { a: EmailAnalysis }) {
  return (
    <section className="mt-4 rule-t pt-4">
      <VerdictChip status={a.verdict} />
      <p className="mt-2">{VERDICT_TEXT[a.verdict]}</p>
      <p className="secondary mt-1">
        From <span className="mono">{a.from_addr ?? "absent"}</span>
        {a.reply_to_etld1 && <> · Reply-To <span className="mono">{a.reply_to_etld1}</span></>}
        {" "}· SPF {a.auth.spf} · DKIM {a.auth.dkim} · DMARC {a.auth.dmarc}
      </p>
      {a.absent && a.absent.length > 0 && <p className="secondary">Not in the message: {a.absent.join(", ")}.</p>}
      <SignalList signals={a.signals} />
      {a.linked_campaigns && a.linked_campaigns.length > 0 && (
        <p className="mt-2">Links to {a.linked_campaigns.map((c) => (
          <Link key={c.id} className="mono underline" to={`/?campaign=${c.id}`}>{c.label ?? c.id}</Link>))}.</p>
      )}
      {a.new_candidate_ids && a.new_candidate_ids.length > 0 && (
        <p className="secondary mt-1">
          {a.new_candidate_ids.length} domain{a.new_candidate_ids.length > 1 ? "s" : ""} from this email became
          candidates and are queued for the same page check as certificate-stream candidates.
        </p>
      )}
    </section>
  );
}

export function EmailAnalyzer() {
  const qc = useQueryClient();
  const [raw, setRaw] = useState("");
  const done = (a: EmailAnalysis) => { qc.invalidateQueries({ queryKey: ["email-analyses"] }); return a; };
  const paste = useMutation({ mutationFn: () => api.analyzeEmail(raw).then(done) });
  const upload = useMutation({ mutationFn: (f: File) => api.analyzeEmailFile(f).then(done) });
  const recent = useQuery({ queryKey: ["email-analyses"], queryFn: api.emailAnalyses });
  const result = upload.data ?? paste.data;
  const err = (upload.error ?? paste.error) as Error | null;
  return (
    <div className="p-6 max-w-[960px]">
      <p className="panel-title" style={{ fontSize: 22 }}>Email headers</p>
      <p className="secondary">
        Paste raw headers or a whole message, or drop a .eml file. Nothing connects to a mailbox. Message bodies are
        read only to collect links and are not stored.
      </p>
      <textarea className="mt-3 w-full" rows={10} value={raw} onChange={(e) => setRaw(e.target.value)}
                aria-label="Raw email headers"
                placeholder={"From: \"State Bank of India\" <alerts@sbi-kyc-update.example>\nAuthentication-Results: …"}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) upload.mutate(f); }} />
      <div className="mt-2 flex gap-2 items-center">
        <button onClick={() => paste.mutate()} disabled={!raw.trim() || paste.isPending}>Analyse headers</button>
        <label className="secondary">or choose a file
          <input type="file" accept=".eml,message/rfc822,text/plain" className="ml-2" style={{ border: 0, background: "transparent" }}
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); }} />
        </label>
      </div>
      {err && <p className="mt-3">{err instanceof ApiError && err.problem.status === 413
        ? "That message is larger than 2 MB. Paste just the headers." : `Analysis failed: ${err.message}`}</p>}
      {result && <Result a={result} />}
      <p className="panel-title mt-8">Recent analyses</p>
      <ul className="mt-2">
        {recent.data?.items.length === 0 && <li className="secondary">No emails analysed yet.</li>}
        {recent.data?.items.map((a) => (
          <li key={a.id} className="flex items-center gap-4 py-1 rule-b">
            <VerdictChip status={a.verdict} />
            <span className="mono truncate">{a.from_addr ?? "sender absent"}</span>
            <span className="secondary ml-auto">{a.source}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
