import { useId } from "react";

/** A native range input (full keyboard support for free), squared off and labelled, with its value in mono. */
export function Slider({ label, min, max, value, onChange, valueText }: {
  label: string;
  min: number;
  max: number;
  value: number;
  onChange: (v: number) => void;
  valueText?: string;
}) {
  const id = useId();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", alignItems: "center", gap: 12 }}>
      <label htmlFor={id} className="t-meta">{label}</label>
      <input
        id={id}
        className="slider"
        type="range"
        min={min}
        max={max}
        step={1}
        value={value}
        aria-valuetext={valueText}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <output htmlFor={id} className="t-data" style={{ minWidth: 32, textAlign: "right" }}>{value}</output>
    </div>
  );
}
