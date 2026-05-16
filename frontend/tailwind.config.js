/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        uza: {
          // Brand purple
          "purple-h": "#6C5CE7",     // --p-h
          "purple-l": "#F0EEFF",     // --p-l
          // Status palette
          teal:   "#1D9E75",         // --green
          orange: "#D97706",         // --orange
          red:    "#EF4444",         // --red
          "teal-cyan": "#0891B2",    // --teal
          // Surfaces
          navy:   "#0C1230",         // --navy
          navy2:  "#0F172A",         // --navy2 / --t1
          // Text scale
          t1: "#0F172A",
          t2: "#334155",
          t3: "#64748B",
          // Severity (procurement / audit)
          "sev-critical": "#A32D2D",
          "sev-high":     "#E24B4A",
          "sev-mid":      "#BA7517",
          "sev-mid-bg":   "#EF9F27",
          "sev-low":      "#5F5E5A",
          "sev-good":     "#0F6E56",
          "sev-good-bg":  "#1D9E75",
          "sev-neutral":  "#888780",
          // Brand purple "afa" (sidebar active)
          "afa": "#AFA9EC",
        },
      },
      fontFamily: {
        sans: ["Geist", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        "uza-xtight":  "-0.04em",   // KPI value
        "uza-tight":   "-0.025em",
        "uza-snug":    "-0.01em",
        "uza-label":   "0.06em",
        "uza-label2":  "0.07em",
        "uza-label3":  "0.08em",
      },
      borderRadius: {
        "uza-pill": "11px",
        "uza-r":    "10px",
        "uza-r2":   "14px",
        "uza-r3":   "16px",
        "uza-r4":   "20px",
        "uza-r5":   "24px",
      },
      boxShadow: {
        "uza-sh":     "0 1px 2px rgba(15,23,60,.04), 0 4px 16px rgba(15,23,60,.06)",
        "uza-shm":    "0 4px 24px rgba(15,23,60,.10), 0 1px 4px rgba(15,23,60,.06)",
        "uza-shl":    "0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08)",
        "uza-glass":  "0 8px 32px rgba(15,23,60,.10), 0 2px 8px rgba(15,23,60,.06)",
        "uza-card":   "0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08)",
        "uza-topbar": "0 1px 0 rgba(255,255,255,.04) inset, 0 4px 20px rgba(0,0,0,.25)",
      },
      backgroundImage: {
        "uza-bg":      "linear-gradient(145deg, #EEF0FF 0%, #F4F2FF 40%, #EBF0FF 100%)",
        "uza-topbar":  "linear-gradient(135deg, #0C1230 0%, #111A3E 100%)",
        "uza-aside":   "linear-gradient(180deg, #0C1230 0%, #111A3E 100%)",
        "uza-btn-p":   "linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%)",
        "uza-btn-p-h": "linear-gradient(135deg, #7C6FF7 0%, #5B4BD5 100%)",
      },
      animation: {
        "uza-modal-in":    "uzaModalIn .45s cubic-bezier(.34,1.2,.64,1)",
        "uza-card-in":     "uzaCardIn .55s cubic-bezier(.34,1.2,.64,1)",
        "uza-fade-up":     "uzaFadeUp .45s ease",
        "uza-shimmer":     "uzaShimmer 6s ease-in-out infinite",
        "uza-breathe":     "uzaBreathe 2.8s ease-in-out infinite",
        "fin-kpi-num":     "finKpiNum .35s ease",
        "pa-rate-in":      "paRateIn .42s cubic-bezier(.34,1.2,.64,1)",
        "sb-item-slide":   "sbItemSlideIn .2s cubic-bezier(.4,0,.2,1)",
      },
      keyframes: {
        uzaModalIn: {
          "0%":   { opacity: "0", transform: "translateY(20px) scale(.96)"  },
          "60%":  { opacity: "1", transform: "translateY(-3px) scale(1.005)" },
          "100%": { opacity: "1", transform: "translateY(0)    scale(1)"     },
        },
        uzaCardIn: {
          "0%":   { opacity: "0", transform: "translateY(12px) scale(.985)"  },
          "60%":  { opacity: "1", transform: "translateY(-2px) scale(1.002)" },
          "100%": { opacity: "1", transform: "translateY(0)    scale(1)"     },
        },
        uzaFadeUp: {
          "from": { opacity: "0", transform: "translateY(8px)" },
          "to":   { opacity: "1", transform: "translateY(0)"   },
        },
        uzaShimmer: {
          "0%, 75%": { transform: "translateX(-120%)" },
          "85%":     { transform: "translateX(120%)"  },
          "100%":    { transform: "translateX(120%)"  },
        },
        uzaBreathe: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: ".4" },
        },
        finKpiNum: {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)"   },
        },
        paRateIn: {
          "from": { opacity: "0", transform: "translateY(6px)" },
          "to":   { opacity: "1", transform: "translateY(0)"   },
        },
        sbItemSlideIn: {
          "0%":   { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)"    },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
