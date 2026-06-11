/**
 * Procurement Analysis API — backend for the BETA tab «Анализ закупочной деятельности».
 * Mirrors legacy paCompute() output 1:1.
 */
import { api } from "./client";

export interface ClosureRow {
  id: string;
  company_id: string;
  company_name: string | null;
  company_color: string | null;
  company_sector: string | null;
  /** Stored as TEXT in DB (the KTRU category 1-15 prefix), so this is a
   *  string at the wire. Frontend coerces via String() when matching. */
  category_id: string | null;
  category_name: string;
  category_unit: string | null;
  product_code: string | null;
  sub_product_code: string | null;
  product_name: string | null;
  supplier: string | null;
  unit_price: number;
  market_avg: number;
  volume: number;
  deviation_pct: number;
  deviation_abs: number | null;
  spread_pct: number | null;
  is_dirty: boolean;
  contract_date: string | null;
  year: number | null;
}

export interface CategoryDeviation {
  category_id: string | null;
  category_name: string;
  category_short: string;
  sum_dev: number;
  sum_ref: number;
  deviation_pct: number;
  closure_count: number;
}

export interface CompanyRatingRow {
  company_id: string;
  company_code: string | null;
  company_name: string;
  company_color: string | null;
  company_sector: string | null;
  company_deviation: number;
  sum_dev: number;
  sum_ref: number;
  above_count: number;
  cat_count: number;
  cat_dev: CategoryDeviation[];
  best_cats: CategoryDeviation[];
  worst_cats: CategoryDeviation[];
  rank: number;
}

export interface CategoryMeta {
  id: number;
  name: string;
  short: string;
  icon: string | null;
  unit?: string;
}

export interface ProductAgg {
  code: string;
  root_code: string;
  name: string;
  unit: string;
  category_id: string | null;
  avg_price: number;
  min_price: number;
  max_price: number;
  spread_pct: number;
  total_spend: number;
  unique_buyers: number;
  contract_count: number;
  max_deviation_pct: number;
  quality_band: "clean" | "wide" | "dirty";
  cluster_index: number;
  total_clusters: number;
  cluster_label: string;
}

export interface CategoryAggregate {
  id: number;
  name: string;
  short: string;
  unit: string;
  all_products: ProductAgg[];
  clean_count: number;
  benchmark_product_count: number;
  clean_spread_min: number | null;
  clean_spread_max: number | null;
}

export interface ProcurementMeta {
  source: "procurementContracts" | "priceListLegacy";
}

export interface ProcurementKpis {
  total_companies: number;
  clean_companies: number;
  total_closures: number;
  clean_closures: number;
  total_overpay_uzs: number;
  above_market_pct: number;
  median_deviation_pct: number;
}

export interface ProcurementAggregate {
  year: number | null;
  sector_code: string | null;
  kpis: ProcurementKpis;
  categories: CategoryMeta[];
  category_aggregates: CategoryAggregate[];
  products_by_code: Record<string, ProductAgg>;
  rating: CompanyRatingRow[];
  purchases: ClosureRow[];
  available_years: number[];
  sectors: { code: string; label: string }[];
  meta: ProcurementMeta;
  generated_at: string;
}

export const procurementAnalysisApi = {
  async getAggregate(params: { year?: number; sector_code?: string; company_id?: string } = {}) {
    const r = await api.get<ProcurementAggregate>("/procurement/aggregate", { params });
    return r.data;
  },
};

// ---------------------------------------------------------------------
// Helpers — paColorByDev (verbatim from legacy)
// ---------------------------------------------------------------------

// Pack 7.9j: legacy verbatim palette (lines 22137-22144) — пастельные оттенки
// для tornado bars и compare sparklines. Бизнес-логика: цвета мягче для глаза,
// но всё ещё чётко различимы по «зона переплаты vs экономии».
export function paColorByDev(dev: number): string {
  if (dev >= 20)  return "#E89B9A";  // dusty coral   — heavy overpay
  if (dev >= 10)  return "#F2C188";  // muted peach   — significant overpay
  if (dev >= 0)   return "#FCE0B8";  // pastel beige  — slight overpay/norm
  if (dev >= -10) return "#A8DBC4";  // soft mint     — slight savings
  return "#7DBFA1";                   // muted sage    — deep savings
}

/** Format compact UZS: 1.2 трлн / 530 млрд / 10.5 млн */
export function paFmtMoneyShort(v: number | null | undefined): string {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (n === 0) return "0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1e12) return sign + (abs / 1e12).toFixed(2) + " трлн";
  if (abs >= 1e9) return sign + (abs / 1e9).toFixed(2) + " млрд";
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(1) + " млн";
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(0) + " тыс.";
  return sign + abs.toFixed(0);
}

/** Coerce-compare for category_id. Backend stores as TEXT, CategoryMeta.id is int.
 *  Use everywhere category_id is compared/filtered. */
export function paSameCat(a: string | number | null | undefined, b: string | number | null | undefined): boolean {
  if (a == null || b == null) return false;
  return String(a) === String(b);
}

export function paFmtMoney(v: number | null | undefined): string {
  if (v == null || isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

/** Wrap a long label across `maxChars` chunks (Chart.js radar/bar labels). */
export function paWrapLabel(label: string, maxChars = 12): string | string[] {
  if (!label || label.length <= maxChars) return label;
  const words = String(label).split(/\s+/);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if (!cur) { cur = w; continue; }
    if ((cur + " " + w).length <= maxChars) cur += " " + w;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  return lines.length > 1 ? lines : label;
}
