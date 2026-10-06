import { throttleBuffer } from "../lib/sse";

it("emits at most 20 lines per second under 3000/sec input, and caps the buffer", () => {
  vi.useFakeTimers();
  const out: string[] = [];
  const t = throttleBuffer<string>((ls) => out.push(...ls), { maxPerSec: 20, cap: 200 });
  for (let i = 0; i < 3000; i++) t.push(String(i));
  vi.advanceTimersByTime(1000);
  expect(out.length).toBeLessThanOrEqual(20);
  expect(out.length).toBeGreaterThan(10);
  expect(t.pending()).toBeLessThanOrEqual(200);
  t.stop();
  vi.useRealTimers();
});

it("keeps the newest lines when the cap drops old ones", () => {
  vi.useFakeTimers();
  const out: string[] = [];
  const t = throttleBuffer<string>((ls) => out.push(...ls), { maxPerSec: 20, cap: 5 });
  for (let i = 0; i < 100; i++) t.push(String(i));
  vi.advanceTimersByTime(300);
  expect(out[0]).toBe("95");
  t.stop();
  vi.useRealTimers();
});

it("candidates are never dropped by the cap", () => {
  vi.useFakeTimers();
  const out: { name: string; is_candidate: boolean }[] = [];
  const t = throttleBuffer<{ name: string; is_candidate: boolean }>((ls) => out.push(...ls),
    { maxPerSec: 20, cap: 5, keep: (x) => x.is_candidate });
  t.push({ name: "sbi-kyc.example", is_candidate: true });
  for (let i = 0; i < 100; i++) t.push({ name: `n${i}`, is_candidate: false });
  vi.advanceTimersByTime(2000);
  expect(out.some((x) => x.name === "sbi-kyc.example")).toBe(true);
  t.stop();
  vi.useRealTimers();
});
