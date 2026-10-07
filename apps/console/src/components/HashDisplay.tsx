import { truncateHash } from "../lib/format";
import { useToast } from "./Toast";

/** A hash, signature, root or tx: 8 + ellipsis + 6 in mono, full value in the title, click copies. Never wraps. */
export function HashDisplay({ value, label = "value" }: { value: string | null | undefined; label?: string }) {
  const toast = useToast();
  if (!value) return <span className="mono ink-3">{"–"}</span>;
  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(value);
      toast(`Copied ${label} to the clipboard.`);
    } catch {
      toast(`Could not copy: the browser blocked clipboard access. Select the ${label} from the tooltip instead.`);
    }
  };
  return (
    <button type="button" className="hash" title={value} aria-label={`Copy ${label} ${value}`} onClick={copy}>
      {truncateHash(value)}
    </button>
  );
}
