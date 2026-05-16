// ============================================================================
// Financials dashboard — shared utilities                       [Phase 19a-1]
//
// Used by all FinDashboard components. Mostly formatting + KPI math
// derived from the portfolio-summary response.
// ============================================================================

import type { PortfolioSummaryResponse, PortfolioCompanyMetrics } from "@/api/financials";

// ─── Formatting ────────────────────────────────────────────────────────────

/** Format a raw value (in UZS) into a "млрд" or "млн" representation,
 *  with space-separated thousands. Returns plain numbers, no currency suffix. */
export function fmtBigNumber(
  valueRaw: number | null | undefined,
  unit: "bln" | "mln",
): string {
  if (valueRaw == null || isNaN(valueRaw)) return "—";
  const divisor = unit === "bln" ? 1_000_000_000 : 1_000_000;
  const scaled = valueRaw / divisor;
  // Decimals: bln → no fractional unless small; mln → integer
  const rounded = unit === "bln" && Math.abs(scaled) < 10
    ? scaled.toFixed(1)
    : Math.round(scaled).toString();
  // Insert thin spaces every 3 digits (Russian convention)
  const parts = rounded.split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  return parts.join(",");
}

export function fmtPct(value: number | null | undefined, fractionDigits = 0): string {
  if (value == null || isNaN(value)) return "—";
  return `${value.toFixed(fractionDigits)}%`;
}

export function fmtPctSigned(value: number | null | undefined, fractionDigits = 0): string {
  if (value == null || isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(fractionDigits)}%`;
}

// ─── Standard / view tabs ──────────────────────────────────────────────────

export const STANDARDS = [
  { value: "NSBU", label: "НСБУ" },
  { value: "IFRS", label: "МСФО" },
] as const;

export const CURRENCIES = [
  { value: "UZS", label: "UZS" },
  { value: "USD", label: "USD" },
  { value: "EUR", label: "EUR" },
] as const;

export const UNITS = [
  { value: "bln", label: "млрд" },
  { value: "mln", label: "млн" },
] as const;

/** View tabs depend on standard (IFRS has 3 statements, NSBU has 2). */
export const VIEW_TABS_IFRS = [
  { value: "PL",   label: "P&L" },
  { value: "SOFP", label: "SOFP" },
  { value: "CF",   label: "Cash Flow" },
] as const;

export const VIEW_TABS_NSBU = [
  { value: "PL", label: "Финансовые результаты" },
  { value: "BS", label: "Баланс" },
] as const;

// ─── KPI band derivation ───────────────────────────────────────────────────

export interface PortfolioKpis {
  totalRevenue: number;       // raw UZS
  totalOpProfit: number;      // raw UZS
  opMargin: number;           // %
  totalEbitda: number;        // raw UZS
  ebitdaMargin: number;       // %
  totalNetProfit: number;     // raw UZS
  netMargin: number;          // %
  lossMakingCount: number;    // companies with profit < 0
  totalCompaniesWithData: number;
  prevYearRevenue: number;
  revenueYoYPct: number;      // % change vs previous year (like-for-like)
  netProfitDeltaPp: number;   // pp change of net margin vs previous year
  /** companies counted in the year totals (have any P&L data for the year) */
  companiesInYear: number;
}

/** Build the top-band KPI object for a specific year. */
export function computePortfolioKpis(
  summary: PortfolioSummaryResponse | null,
  year: number,
): PortfolioKpis | null {
  if (!summary) return null;

  const totals = summary.portfolio_totals_by_year[year] || {};
  const prev = summary.portfolio_totals_by_year[year - 1] || {};

  const revenue = totals.revenue || 0;
  const opProfit = totals.opProfit || 0;
  const ebitda = totals.ebitda || 0;
  const netProfit = totals.profit || 0;

  const prevRevenue = prev.revenue || 0;
  const prevNetProfit = prev.profit || 0;

  const opMargin = revenue ? (opProfit / revenue) * 100 : 0;
  const ebitdaMargin = revenue ? (ebitda / revenue) * 100 : 0;
  const netMargin = revenue ? (netProfit / revenue) * 100 : 0;
  const prevNetMargin = prevRevenue ? (prevNetProfit / prevRevenue) * 100 : 0;

  // Like-for-like prev revenue: include only companies that have data in BOTH years
  let prevRevenueLL = 0;
  let currentRevenueLL = 0;
  for (const item of summary.items) {
    const yCur = item.by_year[year];
    const yPrev = item.by_year[year - 1];
    if (yCur?.revenue != null && yPrev?.revenue != null) {
      currentRevenueLL += yCur.revenue;
      prevRevenueLL += yPrev.revenue;
    }
  }
  const revenueYoYPct = prevRevenueLL > 0
    ? ((currentRevenueLL - prevRevenueLL) / prevRevenueLL) * 100
    : 0;

  // Loss-making companies in this year (net profit < 0)
  let lossMaking = 0;
  let inYear = 0;
  for (const item of summary.items) {
    const ydata = item.by_year[year];
    if (!ydata || ydata.revenue == null) continue;
    inYear += 1;
    if (ydata.profit != null && ydata.profit < 0) lossMaking += 1;
  }

  return {
    totalRevenue: revenue,
    totalOpProfit: opProfit,
    opMargin,
    totalEbitda: ebitda,
    ebitdaMargin,
    totalNetProfit: netProfit,
    netMargin,
    lossMakingCount: lossMaking,
    totalCompaniesWithData: summary.coverage.companies_total,
    prevYearRevenue: prevRevenue,
    revenueYoYPct,
    netProfitDeltaPp: netMargin - prevNetMargin,
    companiesInYear: inYear,
  };
}

// ─── Sector filter helper ──────────────────────────────────────────────────

/** Filter portfolio items by sector_code (case-insensitive). */
export function filterBySector(
  items: PortfolioCompanyMetrics[],
  sectorCode: string,
): PortfolioCompanyMetrics[] {
  if (!sectorCode) return items;
  const target = sectorCode.toLowerCase();
  return items.filter(it => String(it.sector_code || "").toLowerCase() === target);
}

// ─── Animation injection (kpi2 chain — same as Ratings) ────────────────────

const FIN_CSS = `
@keyframes finKpiCardIn {
  0%   { opacity: 0; transform: translateY(14px) scale(.97); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.01); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes finFadeSlideIn {
  0%   { opacity: 0; transform: translateY(12px); }
  60%  { opacity: 1; transform: translateY(-2px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes finShimmer {
  0%   { transform: translateX(-120%); }
  100% { transform: translateX(120%); }
}
@keyframes finKpi2DrawIn {
  from { clip-path: inset(0 100% 0 0); }
  to   { clip-path: inset(0 0% 0 0); }
}
@keyframes finKpi2Breathe {
  0%, 100% { opacity: 1; }
  50%      { opacity: .4; }
}
`;

export function ensureFinancialsCss(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById("financials-global-css")) return;
  const s = document.createElement("style");
  s.id = "financials-global-css";
  s.textContent = FIN_CSS;
  document.head.appendChild(s);
}
