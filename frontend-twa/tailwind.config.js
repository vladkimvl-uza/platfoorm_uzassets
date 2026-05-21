/** @type {import('tailwindcss').Config} */
// UzAssets TWA — Tailwind config, bound to Telegram theme variables.
export default {
  content: ["./index.html", "./src/**/*.{vue,ts,tsx,js}"],
  theme: {
    extend: {
      colors: {
        // Map to Telegram theme — falls back to UzAssets palette if vars empty
        "tg-bg":      "var(--tg-theme-bg-color, #FFFFFF)",
        "tg-text":    "var(--tg-theme-text-color, #1E2A4A)",
        "tg-hint":    "var(--tg-theme-hint-color, #888780)",
        "tg-link":    "var(--tg-theme-link-color, #7F77DD)",
        "tg-button":  "var(--tg-theme-button-color, #7F77DD)",
        "tg-button-text": "var(--tg-theme-button-text-color, #FFFFFF)",
        "tg-secondary-bg": "var(--tg-theme-secondary-bg-color, #FAFAFC)",
        // Brand
        "uza-purple": "#7F77DD",
        "uza-brand":  "#534AB7",
        "uza-navy":   "#1E2A4A",
        "uza-amber":  "#EF9F27",
        "uza-green":  "#1D9E75",
        "uza-red":    "#E24B4A",
        "uza-blue":   "#378ADD",
        "uza-muted":  "#888780",
        "uza-border": "#E5E7EB",
      },
      borderRadius: {
        DEFAULT: "8px",
        card: "12px",
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "'SF Mono'", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
