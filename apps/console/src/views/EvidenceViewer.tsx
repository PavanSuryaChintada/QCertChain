import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type VerifyResult } from "../lib/api";
import { Bytes, Hash } from "../components/Mono";

// The tamper demo (apps/BUILD_SPEC.md §7): on failure the failing artifact row turns red and shows BOTH hashes.
export function EvidenceViewer({ bundleId }: { bundleId: string }) {
  const b = useQuery({ queryKey: ["evidence", bundleId], queryFn: () => api.evidence(bundleId) });
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [showReport, setShowReport] = useState(false);
  const verify = useMutation({ mutationFn: () => api.verify(bundleId), onSuccess: setResult });
  const report = useQuery({ queryKey: ["report", bundleId], queryFn: () => api.report(bundleId), enabled: showReport });
  if (!b.data) return <div className="solving" />;
  const failed = new Map((result?.failures ?? []).map((f) => [f.artifact, f]));
  return (
    <section className="p-4 rule-b">
      <div className="flex items-center justify-between">
        <p className="panel-title">Evidence bundle</p>
        <div className="flex gap-2">
          <button onClick={() => verify.mutate()} disabled={verify.isPending}>Verify bundle</button>
          <button onClick={() => setShowReport((v) => !v)}>{showReport ? "Hide report" : "Show abuse report"}</button>
        </div>
      </div>
      <p className="secondary mt-1">
        Each file is SHA-256 hashed; the hashes form a Merkle root signed with Ed25519.
        {b.data.partial && " Partial bundle: some artifacts could not be collected."}
        {b.data.anchored_tx ? <> Anchored on the ledger in <Hash v={b.data.anchored_tx} />.</> : " Not yet anchored on the ledger."}
      </p>
      <table className="w-full mt-3" style={{ borderCollapse: "collapse", fontSize: 12 }}>
        <tbody>
          {b.data.artifacts.map((a) => {
            const f = failed.get(a.name);
            return (
              <tr key={a.name} data-testid={`artifact-${a.name}`} className="rule-b"
                  style={f ? { color: "var(--v-confirmed)", background: "var(--ground-200)" } : undefined}>
                <td className="mono py-1 pr-3">{a.name}</td>
                <td className="mono py-1 pr-3">
                  {f ? (<><span className="block">{(f.expected ?? "—").slice(0, 12)}… expected</span>
                          <span className="block">{(f.found ?? "missing").slice(0, 12)}… found</span></>)
                     : <Hash v={a.sha256} />}
                </td>
                <td className="py-1 pr-3 text-right"><Bytes n={a.size_bytes} /></td>
                <td className="mono py-1 text-right">{f ? `✗ ${f.reason === "hash_mismatch" ? "TAMPERED" : f.reason.toUpperCase()}` : result ? "✓" : ""}</td>
              </tr>
            );
          })}
          <tr style={result && !result.root_matches ? { color: "var(--v-confirmed)" } : undefined}>
            <td className="mono py-1 pr-3">root</td>
            <td className="mono py-1" colSpan={2}>
              {result && !result.root_matches ? "root mismatch" : <Hash v={b.data.bundle_root} />}
            </td>
            <td className="mono py-1 text-right">
              {result ? (result.valid ? "✓ signature valid" : result.signature_valid ? "✗ signature valid, contents changed" : "✗ signature invalid") : ""}
            </td>
          </tr>
        </tbody>
      </table>
      {verify.isError && <p className="mt-2">Verification could not run: {(verify.error as Error).message}</p>}
      {showReport && report.data && (
        <div className="mt-4">
          <p className="secondary">Report generated — not sent. QCertChain never submits takedown requests.</p>
          <pre className="mono mt-2 p-3 overflow-auto" style={{ fontSize: 12, background: "var(--ground-000)",
                                                             border: "1px solid var(--ground-300)", maxHeight: 360,
                                                             whiteSpace: "pre-wrap" }}>{report.data.body}</pre>
        </div>
      )}
    </section>
  );
}
