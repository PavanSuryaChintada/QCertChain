// Always visible. Live, replay and reconnecting/down are visually distinct at a glance (DESIGN.md §6).
type Props = {
  mode: "live" | "replay";
  connection: "connected" | "reconnecting" | "down" | "replay";
  certsPerSec: number;
  replayFile?: string;
};

export function ModeIndicator({ mode, connection, certsPerSec, replayFile }: Props) {
  let token = "--state-live";
  let label: string;
  if (mode === "replay") {
    token = "--state-replay";
    label = `REPLAY · ${(replayFile ?? "capture").split(/[\\/]/).pop()}`;
  } else if (connection === "connected") {
    label = `LIVE · ${Math.round(certsPerSec).toLocaleString("en-US")}/s`;
  } else {
    token = "--state-down";
    label = connection === "reconnecting" ? "RECONNECTING" : "STREAM DOWN";
  }
  return (
    <span className="inline-flex items-center gap-2" role="status" aria-label={label}
          style={{ fontFamily: "var(--font-data)", fontSize: 12, minWidth: 220 /* reserve space: no layout shift */ }}>
      <span aria-hidden style={{ color: `var(${token})` }}>●</span>
      <span style={{ color: `var(${token})`, fontWeight: 500 }}>{label}</span>
    </span>
  );
}
