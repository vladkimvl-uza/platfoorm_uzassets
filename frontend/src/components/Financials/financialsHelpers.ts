// ============================================================================
// Financials dashboard — shared utilities                       [Phase 19a-2]
//
// Used by all FinDashboard components.
// ============================================================================

import type {
  PortfolioSummaryResponse, PortfolioCompanyMetrics,
} from "@/api/financials";
import type { CompanyListItem, SectorBrief } from "@/api/companies";

// ─── Formatting ────────────────────────────────────────────────────────────

/** Format a raw value (in UZS) into "млрд" or "млн" representation,
 *  with non-breaking-space-separated thousands (Russian convention). */
export function fmtBigNumber(
  valueRaw: number | null | undefined,
  unit: "bln" | "mln",
): string {
  // 2026-05-25: 0 трактуется как "нет данных" → прочерк (по запросу пользователя)
  if (valueRaw == null || isNaN(valueRaw) || valueRaw === 0) return "—";
  const divisor = unit === "bln" ? 1_000_000_000 : 1_000_000;
  const scaled = valueRaw / divisor;
  const rounded = unit === "bln" && Math.abs(scaled) < 10
    ? scaled.toFixed(1)
    : Math.round(scaled).toString();
  const parts = rounded.split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  return parts.join(",");
}

/** Compact format for table cells: 47 763 (no unit suffix), or "—" when null/0.
 * 2026-05-25: 0 трактуется как «нет данных» по требованию пользователя. */
export function fmtCompact(valueRaw: number | null | undefined, unit: "bln" | "mln"): string {
  if (valueRaw == null || isNaN(valueRaw) || valueRaw === 0) return "—";
  const divisor = unit === "bln" ? 1_000_000_000 : 1_000_000;
  const scaled = valueRaw / divisor;
  // Show fractional only for very small numbers in bln mode
  const rounded = unit === "bln" && Math.abs(scaled) < 1 && Math.abs(scaled) > 0
    ? scaled.toFixed(2)
    : Math.round(scaled).toString();
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

export const VIEW_TABS_IFRS = [
  { value: "PL",   label: "P&L" },
  { value: "SOFP", label: "SOFP" },
  { value: "CF",   label: "Cash Flow" },
] as const;

export const VIEW_TABS_NSBU = [
  { value: "PL", label: "Финансовые результаты" },
  { value: "BS", label: "Баланс" },
] as const;

// ─── Metric tabs (depends on standard + viewTab) ───────────────────────────

export interface MetricDef {
  id: string;
  label: string;
}

export function metricsFor(standard: "IFRS" | "NSBU", viewTab: string): MetricDef[] {
  if (standard === "IFRS") {
    if (viewTab === "SOFP") {
      return [
        { id: "totalAssets",      label: "Активы" },
        { id: "equity",           label: "Капитал" },
        { id: "totalLiabilities", label: "Обязательства" },
        { id: "debt",             label: "Долг" },
        { id: "cash",             label: "Денежные ср-ва" },
      ];
    }
    if (viewTab === "CF") {
      return [
        { id: "cfo",            label: "CFO" },
        { id: "cfi",            label: "CFI" },
        { id: "cff",            label: "CFF" },
        { id: "dividendsPaid",  label: "Дивиденды" },
      ];
    }
    return [
      { id: "revenue",      label: "Выручка" },
      { id: "cogs",         label: "Себестоимость" },
      { id: "grossProfit",  label: "Вал. прибыль" },
      { id: "opProfit",     label: "Опер. прибыль" },
      { id: "profit",       label: "Чистая прибыль" },
      { id: "ebitda",       label: "EBITDA" },
    ];
  }
  // NSBU
  if (viewTab === "BS") {
    return [
      { id: "totalAssets",      label: "Итого активы" },
      { id: "totalLiabilities", label: "Обязательства" },
      { id: "equity",           label: "Собственный капитал" },
      { id: "cash",             label: "Денежные средства" },
      { id: "debt",             label: "Долг" },
      { id: "accountsReceivable", label: "Дебиторская задолж." },
      { id: "accountsPayable",    label: "Кредиторская задолж." },
    ];
  }
  return [
    { id: "revenue",     label: "Выручка" },
    { id: "grossProfit", label: "Валовая прибыль" },
    { id: "ebitda",      label: "EBITDA" },
    { id: "profit",      label: "Чистая прибыль" },
    { id: "accountsReceivable", label: "Дебиторская задолж." },
    { id: "accountsPayable",    label: "Кредиторская задолж." },
  ];
}

// ─── Sector lookup helpers ────────────────────────────────────────────────

const SECTOR_FALLBACK_COLOR: Record<string, string> = {
  // Short legacy keys (legacy format)
  mining:    "#9B8EC4",
  oilgas:    "#1D9E75",
  energy:    "#EF9F27",
  transport: "#378ADD",
  other:     "#888780",
  // Full DB keys (Postgres format)
  mining_metallurgy:        "#9B8EC4",
  oil_gas:                  "#1D9E75",
  transport_communications: "#378ADD",
};

export function sectorColor(s: SectorBrief | null | undefined): string {
  if (!s) return "#888780";
  if (s.color_hex) return s.color_hex;
  return SECTOR_FALLBACK_COLOR[String(s.code).toLowerCase()] || "#888780";
}

/** Build company_code → CompanyListItem map (for sector lookup). */
export function buildCompanyIndex(companies: CompanyListItem[]): Map<string, CompanyListItem> {
  const m = new Map<string, CompanyListItem>();
  for (const c of companies) {
    if (c.code) m.set(c.code.toLowerCase(), c);
  }
  return m;
}

// ─── Sector aggregation (for donut + bar table) ───────────────────────────

export interface SectorBucket {
  sectorCode: string;
  label: string;
  color: string;
  total: number;
  count: number;
  /** Companies sorted by metric value descending */
  companies: Array<{
    company_code: string;
    company_name: string;
    company_name_short: string | null;
    /** All years' values for selected metric, in display year order */
    valuesByYear: Record<number, number | null>;
    /** Total of all years (or just current-year value) for this metric */
    sumAllYears: number;
    yoyPct: number | null;
  }>;
}

/** Group portfolio items by sector for the selected metric.
 *  Aggregates across ALL years in the response (used by big table).
 *  For donut: caller filters values to a single year. */
export function aggregateBySector(
  summary: PortfolioSummaryResponse,
  companyIdx: Map<string, CompanyListItem>,
  sectors: SectorBrief[],
  metric: string,
  yearForDonut: number,
): {
  buckets: SectorBucket[];
  donutByYear: Array<{ sectorCode: string; label: string; color: string; total: number; pct: number }>;
} {
  const sectorByCode: Record<string, SectorBrief> = {};
  for (const s of sectors) sectorByCode[String(s.code).toLowerCase()] = s;

  // sectorCode → bucket
  const buckets: Record<string, SectorBucket> = {};

  function getBucket(secCode: string): SectorBucket {
    const code = secCode || "other";
    if (!buckets[code]) {
      const sec = sectorByCode[code];
      buckets[code] = {
        sectorCode: code,
        label: sec?.name_ru || (code === "other" ? "Другое" : code),
        color: sectorColor(sec),
        total: 0,
        count: 0,
        companies: [],
      };
    }
    return buckets[code];
  }

  for (const item of summary.items) {
    const co = companyIdx.get(item.company_code.toLowerCase());
    const secCode = String(co?.sector_code || "").toLowerCase() || "other";

    // Build valuesByYear for selected metric across all years
    const valuesByYear: Record<number, number | null> = {};
    let sumAllYears = 0;
    let curYearVal: number | null = null;
    for (const y of summary.years) {
      const v = item.by_year[y]?.[metric];
      valuesByYear[y] = (typeof v === "number") ? v : null;
      if (v != null) sumAllYears += v;
      if (y === yearForDonut) curYearVal = (typeof v === "number") ? v : null;
    }

    // YoY for current year (vs previous year)
    const cur = item.by_year[yearForDonut]?.[metric];
    const prev = item.by_year[yearForDonut - 1]?.[metric];
    let yoyPct: number | null = null;
    // 0 = «нет данных» → не показываем ложные ±100% при отсутствии факта.
    if (typeof cur === "number" && cur !== 0 && typeof prev === "number" && prev !== 0) {
      yoyPct = ((cur - prev) / Math.abs(prev)) * 100;
    }

    const bucket = getBucket(secCode);
    bucket.companies.push({
      company_code: item.company_code,
      company_name: item.company_name,
      company_name_short: item.company_name_short,
      valuesByYear,
      sumAllYears,
      yoyPct,
    });

    if (curYearVal != null) {
      bucket.total += curYearVal;
      bucket.count += 1;
    }
  }

  // Sort companies inside buckets by sumAllYears desc (relative magnitude)
  for (const b of Object.values(buckets)) {
    b.companies.sort((a, b2) => Math.abs(b2.sumAllYears) - Math.abs(a.sumAllYears));
  }

  // Sort buckets by sector sort_order (or by total desc as fallback)
  const orderedBuckets = Object.values(buckets).sort((a, b) => {
    const sa = sectorByCode[a.sectorCode];
    const sb = sectorByCode[b.sectorCode];
    if (sa && sb) return (sa.sort_order || 0) - (sb.sort_order || 0);
    return Math.abs(b.total) - Math.abs(a.total);
  });

  // Donut totals (filtered to yearForDonut only)
  const grandTotal = orderedBuckets.reduce((s, b) => s + Math.abs(b.total), 0) || 1;
  const donutByYear = orderedBuckets
    .filter(b => Math.abs(b.total) > 0)
    .sort((a, b) => Math.abs(b.total) - Math.abs(a.total))
    .map(b => ({
      sectorCode: b.sectorCode,
      label: b.label,
      color: b.color,
      total: b.total,
      pct: Math.round(Math.abs(b.total) / grandTotal * 100),
    }));

  return { buckets: orderedBuckets, donutByYear };
}

// ─── KPI band derivation (Phase 19a-1) ─────────────────────────────────────

export interface PortfolioKpis {
  totalRevenue: number;
  totalOpProfit: number;
  opMargin: number;
  totalEbitda: number;
  ebitdaMargin: number;
  totalNetProfit: number;
  netMargin: number;
  lossMakingCount: number;
  totalCompaniesWithData: number;
  prevYearRevenue: number;
  revenueYoYPct: number;
  netProfitDeltaPp: number;
  companiesInYear: number;
  companiesWithProfit: number;
  totalAccountsReceivable: number;
  totalAccountsPayable: number;
}

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
  const accountsReceivable = totals.accountsReceivable || 0;
  const accountsPayable = totals.accountsPayable || 0;

  const prevRevenue = prev.revenue || 0;
  const prevNetProfit = prev.profit || 0;

  const opMargin = revenue ? (opProfit / revenue) * 100 : 0;
  const ebitdaMargin = revenue ? (ebitda / revenue) * 100 : 0;
  const netMargin = revenue ? (netProfit / revenue) * 100 : 0;
  const prevNetMargin = prevRevenue ? (prevNetProfit / prevRevenue) * 100 : 0;

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

  let lossMaking = 0;
  let inYear = 0;
  let withProfit = 0;   // компании, у которых ЕСТЬ данные по прибыли (знаменатель карточки «Убыточные»)
  for (const item of summary.items) {
    const ydata = item.by_year[year];
    if (!ydata) continue;
    // Count company as "having data" if ANY metric is non-null
    // (matches legacy logic — not only revenue, also EBITDA/profit/etc.)
    const hasAnyData = Object.values(ydata).some(v => v != null);
    if (!hasAnyData) continue;
    inYear += 1;
    if (ydata.profit != null) withProfit += 1;
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
    companiesWithProfit: withProfit,
    totalAccountsReceivable: accountsReceivable,
    totalAccountsPayable: accountsPayable,
  };
}

// ─── Filter portfolio by sector ────────────────────────────────────────────

export function filterBySector(
  items: PortfolioCompanyMetrics[],
  companyIdx: Map<string, CompanyListItem>,
  sectorCode: string,
): PortfolioCompanyMetrics[] {
  if (!sectorCode) return items;
  const target = sectorCode.toLowerCase();
  return items.filter(it => {
    const co = companyIdx.get(it.company_code.toLowerCase());
    return String(co?.sector_code || "").toLowerCase() === target;
  });
}

// ─── Animation injection ──────────────────────────────────────────────────

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
@keyframes finBarGrow {
  from { width: 0; }
  to   { width: var(--w, 0%); }
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
