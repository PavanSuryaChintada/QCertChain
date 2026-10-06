import type { Config } from "tailwindcss";

// docs/DESIGN.md §3–4: tokens are locked. Tailwind only maps them; no Tailwind default palette exists here.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      ground: { 0: "var(--ground-000)", 100: "var(--ground-100)", 200: "var(--ground-200)", 300: "var(--ground-300)", 400: "var(--ground-400)" },
      ink: { 0: "var(--ink-000)", 100: "var(--ink-100)", 200: "var(--ink-200)", 300: "var(--ink-300)" },
    },
    borderRadius: { none: "0", sm: "2px" },
    boxShadow: { none: "none" },
    fontFamily: {
      display: ["IBM Plex Sans Condensed", "sans-serif"],
      body: ["IBM Plex Sans", "sans-serif"],
      data: ["IBM Plex Mono", "monospace"],
    },
    fontSize: { 11: "11px", 12: "12px", 13: "13px", 14: "14px", 15: "15px", 18: "18px", 22: "22px", 28: "28px" },
    extend: {},
  },
  plugins: [],
} satisfies Config;
