import type { Config } from "tailwindcss";

// Tokens live in src/styles/tokens.css. Tailwind only maps them: no default palette, no radius, no shadow, and
// spacing only from the 4/8/12/16/24/32/48 scale.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      canvas: "var(--canvas)",
      paper: "var(--paper)",
      sunken: "var(--sunken)",
      hairline: "var(--hairline)",
      "hairline-firm": "var(--hairline-firm)",
      ink: "var(--ink)",
      "ink-2": "var(--ink-2)",
      "ink-3": "var(--ink-3)",
      action: "var(--action)",
      "action-weak": "var(--action-weak)",
    },
    spacing: { 0: "0", px: "1px", 1: "4px", 2: "8px", 3: "12px", 4: "16px", 6: "24px", 8: "32px", 12: "48px" },
    borderRadius: { none: "0", DEFAULT: "0" },
    boxShadow: { none: "none" },
    fontFamily: { sans: ["IBM Plex Sans", "sans-serif"], mono: ["IBM Plex Mono", "monospace"] },
    fontSize: {
      label: ["11px", "14px"],
      meta: ["12px", "16px"],
      body: ["13px", "18px"],
      section: ["15px", "20px"],
      display: ["22px", "28px"],
    },
    fontWeight: { normal: "400", medium: "500", semibold: "600" },
    extend: {},
  },
  plugins: [],
} satisfies Config;
