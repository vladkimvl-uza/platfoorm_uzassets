// ============================================================================
// All rating-page components share these.
// ============================================================================

import type { AgencyRatingBrief } from "@/api/ratings";
import type { CompanyListItem, SectorBrief } from "@/api/companies";

// ─── Agencies ──────────────────────────────────────────────────────────────
export const CREDIT_AGENCIES = ["Fitch", "S&P", "Moody's"] as const;
export const ESG_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP"] as const;
export const ALL_AGENCIES = [...CREDIT_AGENCIES, ...ESG_AGENCIES] as const;

// ─── Rank ladder for credit ratings (low → high) ──────────────────────────
export const RANK_ORDER = [
  "D", "CCC-", "CCC", "CCC+",
  "B-", "B", "B+",
  "BB-", "BB", "BB+",
  "BBB-", "BBB", "BBB+",
  "A-", "A", "A+",
  "AA-", "AA", "AA+", "AAA",
];

export function ratingRank(rv: string | null | undefined): number {
  if (!rv) return -1;
  const idx = RANK_ORDER.indexOf(String(rv).toUpperCase());
  return idx >= 0 ? idx : -1;
}

// ─── Date helpers ──────────────────────────────────────────────────────────
export function isRecentlyUpdated(r: AgencyRatingBrief | null | undefined): boolean {
  if (!r) return false;
  const dateStr = r.rating_date || r.rating_date_text || "";
  if (!dateStr) return false;
  const cy = new Date().getFullYear();
  const d = String(dateStr);
  return d.indexOf(String(cy)) >= 0 || d.indexOf(String(cy - 1)) >= 0;
}

export function formatDate(d: string | null | undefined): string {
  if (!d) return "";
  // ISO YYYY-MM-DD → DD.MM.YYYY
  const s = String(d);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    return s.slice(0, 10).split("-").reverse().join(".");
  }
  return s;
}

const MON_MAP: Record<string, string> = {
  янв:"01",фев:"02",мар:"03",апр:"04",май:"05",июн:"06",
  июл:"07",авг:"08",сен:"09",окт:"10",ноя:"11",дек:"12",
  jan:"01",feb:"02",mar:"03",apr:"04",may:"05",jun:"06",
  jul:"07",aug:"08",sep:"09",oct:"10",nov:"11",dec:"12",
};

/** Build a sortable YYYY-MM-DD key from various date string forms. */
export function dateSortKey(d: string | null | undefined): string {
  if (!d) return "0000-00-00";
  const s = String(d).trim().toLowerCase();
  // ISO already
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  const p = s.split(/[\s\/.\-]+/);
  if (p.length === 3) {
    const y = p[2] && p[2].length === 4 ? p[2] : p[0];
    const m = MON_MAP[p[1]] || MON_MAP[p[0]] || p[1];
    const day = p[0].length <= 2 ? p[0] : p[2];
    return `${y}-${("0" + m).slice(-2)}-${("0" + day).slice(-2)}`;
  }
  if (p.length === 2) {
    const mm = MON_MAP[p[0]] || p[0];
    const yy = p[1] && p[1].length === 4 ? p[1] : p[0];
    return `${yy}-${("0" + mm).slice(-2)}-01`;
  }
  if (p.length === 1 && p[0].length === 4) return `${p[0]}-01-01`;
  return s;
}

export interface BadgeStyle { bg: string; fg: string; }

export function badgeStyle(agency: string, rating: string | null | undefined): BadgeStyle {
  const rv = String(rating || "").toUpperCase();
  if (agency === "Fitch" || agency === "S&P" || agency === "Moody's") {
    if (rv.startsWith("BBB")) return { bg: "rgba(55,138,221,.10)", fg: "#378ADD" };
    if (rv.startsWith("BB"))  return { bg: "#FEF9C3",              fg: "#D97706" };
    if (rv.startsWith("AA") || rv.startsWith("A")) return { bg: "#DCFCE7", fg: "#1D9E75" };
    if (rv.startsWith("B"))   return { bg: "#FEF9C3",              fg: "#D97706" };
    if (rv.startsWith("CCC") || rv === "D") return { bg: "#FEE2E2", fg: "#EF4444" };
    return { bg: "#F1F5F9", fg: "#64748B" };
  }
  if (agency === "Sustainable Fitch" || agency === "S&P ESG") {
    const n = parseInt(rv);
    if (n >= 1 && n <= 5) {            // tier scale 1=best..5=worst
      if (n <= 2) return { bg: "#DCFCE7", fg: "#1D9E75" };
      if (n === 3) return { bg: "#FEF9C3", fg: "#D97706" };
      return { bg: "#FEE2E2", fg: "#EF4444" };
    }
    if (n >= 6) {                       // 0–100 score scale
      if (n >= 60) return { bg: "#DCFCE7", fg: "#1D9E75" };
      if (n >= 40) return { bg: "#FEF9C3", fg: "#D97706" };
      return { bg: "#FEE2E2", fg: "#EF4444" };
    }
    return { bg: "#F1F5F9", fg: "#64748B" };
  }
  if (agency === "CDP") {
    if (rv === "A" || rv === "A-") return { bg: "#DCFCE7", fg: "#1D9E75" };
    if (rv === "B" || rv === "B-") return { bg: "rgba(55,138,221,.10)", fg: "#378ADD" };
    return { bg: "#FEE2E2", fg: "#EF4444" };
  }
  return { bg: "#F1F5F9", fg: "#64748B" };
}

// ─── Outlook badge (small triangle/arrow) ─────────────────────────────────
export interface OutlookBadge { label: string; fg: string; bg: string; symbol: string; }

const OUTLOOK_MAP: Record<string, [string, string, string, string]> = {
  Stable:      ["Стабильный",      "#64748B", "#F1F5F9", "→"],
  Positive:    ["Позитивный",      "#1D9E75", "#ECFDF5", "↑"],
  Negative:    ["Негативный",      "#EF4444", "#FEE2E2", "↓"],
  Developing:  ["Развивающийся",   "#D97706", "#FEF9C3", "↔"],
  RWN:         ["CW Негативный",   "#EF4444", "#FEE2E2", "⚠"],
  RWP:         ["CW Позитивный",   "#1D9E75", "#ECFDF5", "⚠"],
};

export function outlookBadge(outlook: string | null | undefined): OutlookBadge | null {
  if (!outlook) return null;
  const v = OUTLOOK_MAP[outlook];
  if (!v) return null;
  return { label: v[0], fg: v[1], bg: v[2], symbol: v[3] };
}

// ─── Sector helpers ────────────────────────────────────────────────────────
/** Read sector code from a company robustly (snake/camel/legacy). */
export function coSector(c: any): string {
  return String(c?.sector_code || c?.sector || "").toLowerCase();
}

const SECTOR_COLOR_FALLBACK: Record<string, string> = {
  mining:       "#7F77DD",
  oilgas:       "#EF9F27",
  energy:       "#378ADD",
  transport:    "#1D9E75",
  other:        "#64748B",
};

export function sectorColor(s: SectorBrief | { code: string; color_hex?: string | null } | null | undefined): string {
  if (!s) return "#64748B";
  if (s.color_hex) return s.color_hex;
  return SECTOR_COLOR_FALLBACK[String(s.code).toLowerCase()] || "#64748B";
}

// ─── Rating lookup: build (companyId+agency)→rating map for O(1) access ──
export function buildRatingIndex(ratings: AgencyRatingBrief[]): Map<string, AgencyRatingBrief> {
  const m = new Map<string, AgencyRatingBrief>();
  for (const r of ratings) {
    if (r.company_id && r.agency) m.set(`${r.company_id}::${r.agency}`, r);
  }
  return m;
}

export function getRating(
  index: Map<string, AgencyRatingBrief>,
  companyId: string,
  agency: string,
): AgencyRatingBrief | null {
  return index.get(`${companyId}::${agency}`) || null;
}

// ─── Display value: combine rating + score for ESG agencies ──────────────
export function displayRating(r: AgencyRatingBrief, agency: string): string {
  if (!r.rating) return r.score || "";
  if ((agency === "Sustainable Fitch" || agency === "S&P ESG") && r.score && String(r.score).trim() !== String(r.rating).trim()) {
    return `${r.rating} · ${r.score}`;
  }
  return r.rating;
}

// ─── CSS keyframes (injected once globally) ──────────────────────────────
// Used by all Ratings components. Injected from Ratings.vue's onMounted.
export const RATINGS_GLOBAL_CSS = `
@keyframes ratKpiCardIn {
  0%   { opacity: 0; transform: translateY(14px) scale(.97); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.01); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes ratFadeSlideIn {
  0%   { opacity: 0; transform: translateY(12px); }
  60%  { opacity: 1; transform: translateY(-2px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes ratShimmer {
  0%   { transform: translateX(-120%); }
  100% { transform: translateX(120%); }
}
@keyframes ratKpi2DrawIn {
  from { clip-path: inset(0 100% 0 0); }
  to   { clip-path: inset(0 0% 0 0); }
}
@keyframes ratKpi2Breathe {
  0%, 100% { opacity: 1; }
  50%      { opacity: .4; }
}
`;

export function ensureRatingsCss(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById("ratings-global-css")) return;
  const s = document.createElement("style");
  s.id = "ratings-global-css";
  s.textContent = RATINGS_GLOBAL_CSS;
  document.head.appendChild(s);
}

// ─── Pluralisation for "X компаний" / "X компании" ────────────────────────
export function pluralCompanies(n: number): string {
  const m100 = n % 100, m10 = n % 10;
  if (m100 >= 11 && m100 <= 14) return "компаний";
  if (m10 === 1) return "компания";
  if (m10 >= 2 && m10 <= 4) return "компании";
  return "компаний";
}
