/** Every string inside a value, however deeply nested (help entries, sections, steps). */
export function strings(x: unknown): string[] {
  if (typeof x === "string") return [x];
  if (Array.isArray(x)) return x.flatMap(strings);
  if (x && typeof x === "object") return Object.values(x).flatMap(strings);
  return [];
}

// Names that contain digits but are not measurements.
const NOT_MEASUREMENTS = /Ed25519|SHA-256|404|RFC 2142/g;

/** Explainer text never types a measured number (spec §8b): live figures come from the API at run time. */
export function measuredNumber(s: string): boolean {
  return /\d/.test(s.replace(NOT_MEASUREMENTS, ""));
}
