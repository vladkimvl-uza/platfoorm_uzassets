/**
 * Procurement Analysis API — backend for the BETA tab «Анализ закупочной деятельности».
 */
import { api } from "./client";

export interface ClosureRow {
  id: string;
  company_id: string;
  company_name: string | null;
  company_color: string | null;
  company_sector: string | null;
  category_id: number;
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
  category_id: number;
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
  rating: CompanyRatingRow[];
  purchases: ClosureRow[];
  available_years: number[];
  sectors: { code: string; label: string }[];
  generated_at: string;
}

export const procurementAnalysisApi = {
  async getAggregate(params: { year?: number; sector_code?: string; company_id?: string } = {}) {
    const r = await api.get<ProcurementAggregate>("/procurement/aggregate", { params });
    return r.data;
  },
};

// ---------------------------------------------------------------------
// ---------------------------------------------------------------------

export function paColorByDev(dev: number): string {
  if (dev <= -10) return "#0F6E56";    // strong green: deep economy
  if (dev < 0) return "#1D9E75";       // green: moderate economy
  if (dev <= 3) return "#94A3B8";      // grey: norm zone
  if (dev <= 10) return "#EF9F27";     // amber: above market
  return "#E24B4A";                     // red: significant overpayment
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

export function paFmtMoney(v: number | null | undefined): string {
  if (v == null || isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}
