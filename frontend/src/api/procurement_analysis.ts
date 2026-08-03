/**
 * Procurement Analysis API — backend for the BETA tab «Анализ закупочной деятельности».
 * Mirrors legacy paCompute() output 1:1.
 */
import { api } from "./client";
import { fmtNumber } from "@/locale";
import { getCurrentLocale, t } from "@/locale/i18n";

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
  product_type: string | null;          // 'PRODUCT' | 'SERVICE'
  supplier: string | null;
  supplier_inn: string | null;
  unit_price: number;
  market_avg: number;
  volume: number;
  deviation_pct: number;
  deviation_abs: number | null;
  spread_pct: number | null;
  is_dirty: boolean;
  contract_date: string | null;
  year: number | null;
  // Заключение центра экспертизы (по каждой закупке)
  conclusion_text: string | null;
  conclusion_status: string | null;
  conclusion_date: string | null;
  conclusion_author_name: string | null;
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
  company_deviation: number | null;   // null = нет сопоставимых позиций
  has_comparable?: boolean;
  sum_dev: number;
  sum_ref: number;
  above_count: number;
  cat_count: number;
  cat_dev: CategoryDeviation[];
  best_cats: CategoryDeviation[];
  worst_cats: CategoryDeviation[];
  // legacy-compat (бэк всегда шлёт; нужны PaRatingPanel/PaLeaders)
  sum_overpay: number;
  sum_savings: number;
  red_pct: number;
  yellow_pct: number;
  green_pct: number;
  problem_cats: number;
  total_count: number;
  low_sample: boolean;                  // мало сопоставимых позиций → % недостоверен
  // Совокупный расход компании (лот-дедуп, ВСЕ типы) + разбивка — для шапки профиля
  company_total_spend: number;
  goods_spend: number;
  services_spend: number;
  works_spend: number;
  total_lots: number;
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
  product_type: string;                 // 'PRODUCT' | 'SERVICE'
  category_id: string | null;
  avg_price: number;
  min_price: number;
  max_price: number;
  spread_pct: number;                   // разброс ПО ПОЛОСЕ сопоставимости
  full_spread_pct: number;              // полный разброс (для плашки «грязный код N×»)
  total_spend: number;
  total_volume: number;
  unique_buyers: number;
  contract_count: number;
  max_deviation_pct: number;
  quality_band: "clean" | "wide" | "dirty";
  potential_saving: number;             // Σ volume×(price − best comparable)
  cluster_index: number;
  total_clusters: number;
  cluster_label: string;
}

// ── Поставщики / способы / площадки (лот-дедуплицированный спенд) ──
export interface SupplierAgg {
  supplier_inn: string | null;
  supplier_name: string;
  spend: number;
  spend_share_pct: number;
  lot_count: number;
  company_count: number;
  company_codes: string[];
  saved_amount: number;
  saved_rate_pct: number;
  is_cross: boolean;
  excess_uzs: number;                   // переплата над медианой рынка
  comparable_spend: number;
  premium_pct: number;
  overpriced_lines: number;
}

export interface SupplierConcentration {
  company_id: string;
  company_name: string;
  company_color: string | null;
  company_sector: string | null;
  spend: number;
  supplier_count: number;
  top1_name: string | null;
  top1_pct: number;
  top3_pct: number;
  hhi: number;                          // 0..10000
}

export interface MethodAgg {
  method: string;
  label: string;
  lot_count: number;
  spend: number;
  spend_share_pct: number;
  saved_amount: number;
  saved_rate_pct: number;
  is_competitive: boolean;
}

export interface PlatformAgg {
  platform: string;
  lot_count: number;
  spend: number;
  spend_share_pct: number;
  saved_amount: number;
  saved_rate_pct: number;
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
  // null = сопоставимых компаний нет, судить не о чем
  above_market_pct: number | null;
  median_deviation_pct: number | null;
  // расширение (лот-дедуплицированные деньги)
  total_spend: number;
  total_lots: number;
  saved_amount: number;
  // null = экономия не указана в источнике (не «торговались и не сэкономили»)
  saved_rate_pct: number | null;
  saving_known_lots: number;
  saving_known_spend: number;
  saving_unknown_spend: number;
  no_tender_spend: number;              // спенд НЕКОНКУРЕНТНЫХ методов (e_shop/каталог)
  no_tender_pct: number | null;         // доля спенда без конкурентной процедуры
  competitive_no_saving_spend: number;  // конкурентные процедуры с нулевой экономией
  competitive_no_saving_pct: number | null;  // считается только по лотам с известной экономией
  potential_saving_uzs: number;
  supplier_count: number;
  disclosed_supplier_pct: number | null;
  cross_supplier_pct: number;           // доля спенда у сквозных (по ВСЕМ, не топ-50)
  services_spend: number;
  services_pct: number | null;
  goods_spend: number;
  works_spend: number;
  works_pct: number | null;
}

export interface WorkServiceByCompany {
  company_id: string;
  company_name: string;
  company_color: string | null;
  company_sector: string | null;
  services_spend: number;
  services_lots: number;
  works_spend: number;
  works_lots: number;
  total_spend: number;
}

/** Честный знаменатель экрана: по какой части данных посчитаны цифры. */
export interface ProcurementCoverage {
  companies_total: number;
  companies_with_data: number;
  companies_comparable: number;
  closures_total: number;
  lots_total: number;
  spend_total: number;
  comparable_spend: number;
  comparable_spend_pct: number | null;
  saving_known_lots_pct: number | null;
  category_known_pct: number | null;
  supplier_known_pct: number | null;
  period_from: string | null;
  period_to: string | null;
  years: number[];
}

export interface ProcurementAggregate {
  year: number | null;
  sector_code: string | null;
  has_data?: boolean;
  coverage?: ProcurementCoverage;
  kpis: ProcurementKpis;
  categories: CategoryMeta[];
  category_aggregates: CategoryAggregate[];
  products_by_code: Record<string, ProductAgg>;
  rating: CompanyRatingRow[];
  purchases: ClosureRow[];
  suppliers_top: SupplierAgg[];
  suppliers_cross: SupplierAgg[];
  suppliers_expensive: SupplierAgg[];
  supplier_concentration: SupplierConcentration[];
  methods: MethodAgg[];
  platforms: PlatformAgg[];
  works_services: WorkServiceByCompany[];
  available_years: number[];
  sectors: { code: string; label: string }[];
  meta: ProcurementMeta;
  generated_at: string;
}

export interface PaClosureUpdateResult {
  ok: boolean;
  id: string;
  unit_price?: number | null;
  market_avg?: number | null;
  deviation_pct?: number | null;
  siblings_recomputed?: number;
  conclusion_text?: string | null;
  conclusion_status?: string | null;
  conclusion_date?: string | null;
  conclusion_author_name?: string | null;
}

export interface PaClosurePatch {
  unit_price?: number;
  volume?: number;
  product_code?: string;
  product_name?: string;
  supplier_name?: string;
  is_dirty?: boolean;
  dirty_reason?: string;
  conclusion_text?: string | null;
  conclusion_status?: string | null;
}

export const procurementAnalysisApi = {
  async getAggregate(params: { year?: number; sector_code?: string; company_id?: string } = {}) {
    const r = await api.get<ProcurementAggregate>("/procurement/aggregate", { params });
    return r.data;
  },

  /** Update one closure (PUT /procurement/closures/{id}). Used for the
   *  per-purchase «Заключение центра экспертизы». Requires procurement.edit. */
  async updateClosure(id: string, patch: PaClosurePatch): Promise<PaClosureUpdateResult> {
    const r = await api.put<PaClosureUpdateResult>(`/procurement/closures/${id}`, patch);
    return r.data;
  },
};

// ---------------------------------------------------------------------
// Helpers — paColorByDev (verbatim from legacy)
// ---------------------------------------------------------------------

// legacy verbatim palette (lines 22137-22144) — пастельные оттенки
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
  const locale = getCurrentLocale();
  if (abs >= 1e12) return `${sign}${fmtNumber(abs / 1e12, locale, { decimals: 2 })} ${t("трлн")}`;
  if (abs >= 1e9) return `${sign}${fmtNumber(abs / 1e9, locale, { decimals: 2 })} ${t("млрд")}`;
  if (abs >= 1e6) return `${sign}${fmtNumber(abs / 1e6, locale, { decimals: 1 })} ${t("млн")}`;
  if (abs >= 1e3) return `${sign}${fmtNumber(abs / 1e3, locale, { decimals: 0 })} ${t("тыс.")}`;
  return sign + fmtNumber(abs, locale);
}

/** Coerce-compare for category_id. Backend stores as TEXT, CategoryMeta.id is int.
 *  Use everywhere category_id is compared/filtered. */
export function paSameCat(a: string | number | null | undefined, b: string | number | null | undefined): boolean {
  if (a == null || b == null) return false;
  return String(a) === String(b);
}

export function paFmtMoney(v: number | null | undefined): string {
  if (v == null || isNaN(Number(v))) return "—";
  return fmtNumber(Number(v), getCurrentLocale(), { decimals: 2, minDecimals: 0 });
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
