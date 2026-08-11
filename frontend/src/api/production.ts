import { api } from "@/api/client";
import { i18nKey } from "@/locale/keys";

/**
 * Периоды производственных показателей: кварталы + полугодия + год.
 * Единый источник для тумблеров и подписей (по образцу BP_PERIODS). Период —
 * свободная строка: бэкенд не валидирует и хранит его полем записи
 * (raw_snapshot.productionData: {k, year, period, lines}), расчёт per-record
 * (не нарастающий итог). Метки — i18n-маркеры, оборачивать в t() при выводе.
 */
export const PRODUCTION_PERIODS: { key: string; label: string }[] = [
  { key: "q1", label: "Q1" },
  { key: "q2", label: "Q2" },
  { key: "q3", label: "Q3" },
  { key: "q4", label: "Q4" },
  { key: "h1", label: i18nKey("1 полугодие") },
  { key: "h2", label: i18nKey("2 полугодие") },
  { key: "annual", label: i18nKey("Год") },
];
/** Ключи периодов в каноническом порядке. */
export const PRODUCTION_PERIOD_KEYS = PRODUCTION_PERIODS.map((p) => p.key);
/** Метка периода (i18n-маркер — оборачивать в t()). */
export function productionPeriodLabel(key: string): string {
  return PRODUCTION_PERIODS.find((p) => p.key === key)?.label || key;
}
/** Родительный падеж для «скопировать из …» (номенклатуру из другого периода). */
export function productionPeriodGenitive(key: string): string {
  const m: Record<string, string> = {
    h1: i18nKey("1 полугодия"), h2: i18nKey("2 полугодия"), annual: i18nKey("года"),
    q1: "Q1", q2: "Q2", q3: "Q3", q4: "Q4",
  };
  return m[key] || key;
}

export interface ProdLine {
  name: string;
  unit?: string | null;
  total?: boolean;
  parent?: number | null;
  baseN?: number | null; baseM?: number | null;
  planN?: number | null; planM?: number | null;
  expN?: number | null; expM?: number | null;
  factN?: number | null; factM?: number | null;
  growthM?: number | null; growthN?: number | null; growthPct?: number | null;
  execPct?: number | null; execState?: "pct" | "nofact" | "noplan"; execBasis?: "money" | "natura";
  execKind?: "fact" | "forecast";
}

export interface ProdCompany {
  k: string; n: string; s: string; sector_color: string;
  unit?: string | null;
  baseM?: number | null; planM?: number | null; expM?: number | null; factM?: number | null;
  baseN?: number | null; planN?: number | null; expN?: number | null; factN?: number | null;
  execPct?: number | null; execState: "pct" | "nofact" | "noplan"; execBasis?: "money" | "natura";
  execKind?: "fact" | "forecast";
  growthPct?: number | null;
  has_data: boolean;
  lines: ProdLine[];
}

export interface ProdKpis {
  present: number; with_data: number;
  plan_total: number; expect_total: number; fact_total?: number; exec_pct: number | null;
  over: number; under: number; ontarget: number; overpar: number;
}

export interface ProdOverview {
  companies: ProdCompany[];
  kpis: ProdKpis;
  year: number;
  period: string;
}

export interface ProdCompanyDetail {
  company: ProdCompany;
  year: number;
  period: string;
  years: number[];
  combos: { year: number; period: string }[];
}

export const productionApi = {
  overview: (year: number, period: string) =>
    api.get<ProdOverview>("/production/overview", { params: { year, period } }).then((r) => r.data),
  available: () =>
    api.get<{ years: number[]; combos: { year: number; period: string }[] }>("/production/available").then((r) => r.data),
  // Одна компания — для вкладки БП в карточке компании (scoped на бэке).
  companyDetail: (code: string, year: number, period: string) =>
    api.get<ProdCompanyDetail>(`/production/companies/${encodeURIComponent(code)}`, { params: { year, period } }).then((r) => r.data),
  upsertCompany: (code: string, body: { year: number; period: string; lines: ProdLine[] }) =>
    api.put(`/production/companies/${encodeURIComponent(code)}`, body).then((r) => r.data),
};
