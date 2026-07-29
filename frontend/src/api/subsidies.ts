/**
 * Subsidies registry API — реестр субсидий по компаниям портфеля.
 * Метрика «Субсидии» в финансах + модалка-реестр с фильтрами.
 */
import { api } from "./client";
import { fmtNumber } from "@/locale";
import { getCurrentLocale, t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

export interface SubsidyRow {
  id: string;
  company_id: string;
  company_name: string | null;
  company_code: string | null;
  sector_code: string | null;
  sector_name: string | null;
  sector_color: string | null;
  year: number | null;
  amount: number | null;
  program: string | null;
  source: string | null;
  kind: string | null;
  status: string | null;
  allocation_date: string | null;
  note: string | null;
  created_by_name: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SubsidyUpsert {
  company_id: string;
  year?: number | null;
  amount?: number | null;
  program?: string | null;
  source?: string | null;
  kind?: string | null;
  status?: string | null;
  allocation_date?: string | null;
  note?: string | null;
}

export type SubsidyPatch = Omit<SubsidyUpsert, "company_id">;

export interface SubsidyCompanyAgg {
  company_id: string;
  company_name: string | null;
  company_code: string | null;
  sector_code: string | null;
  sector_name: string | null;
  sector_color: string | null;
  total: number;
  count: number;
}

export interface SubsidySectorAgg {
  sector_code: string | null;
  sector_name: string | null;
  sector_color: string | null;
  total: number;
  count: number;
}

export interface SubsidySummary {
  year: number | null;
  sector_code: string | null;
  total: number;
  count: number;
  by_company: SubsidyCompanyAgg[];
  by_sector: SubsidySectorAgg[];
}

export const subsidiesApi = {
  async list(params: { year?: number; sector_code?: string; company_id?: string } = {}): Promise<SubsidyRow[]> {
    const r = await api.get<SubsidyRow[]>("/subsidies", { params });
    return r.data;
  },

  async summary(params: { year?: number; sector_code?: string } = {}): Promise<SubsidySummary> {
    const r = await api.get<SubsidySummary>("/subsidies/summary", { params });
    return r.data;
  },

  async create(payload: SubsidyUpsert): Promise<SubsidyRow> {
    const r = await api.post<SubsidyRow>("/subsidies", payload);
    return r.data;
  },

  async update(id: string, patch: SubsidyPatch): Promise<SubsidyRow> {
    const r = await api.put<SubsidyRow>(`/subsidies/${id}`, patch);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/subsidies/${id}`);
  },
};

// ─── Helpers ──────────────────────────────────────────────────────

/** Compact сум formatting: 1.5 трлн / 530 млрд / 12.0 млн сум. */
export function fmtSubsidySum(v: number | null | undefined): { value: string; unit: string } {
  if (v == null || isNaN(Number(v))) return { value: "—", unit: "" };
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e12) return { value: fmtNumber(n / 1e12, getCurrentLocale(), { decimals: 1 }), unit: t("трлн сум") };
  if (abs >= 1e9)  return { value: fmtNumber(n / 1e9, getCurrentLocale(), { decimals: 1 }),  unit: t("млрд сум") };
  if (abs >= 1e6)  return { value: fmtNumber(n / 1e6, getCurrentLocale(), { decimals: 1 }),  unit: t("млн сум") };
  if (abs >= 1e3)  return { value: fmtNumber(Math.round(n / 1e3), getCurrentLocale()), unit: t("тыс. сум") };
  return { value: fmtNumber(Math.round(n), getCurrentLocale()), unit: t("сум") };
}

export const SUBSIDY_STATUSES: { key: string; label: string }[] = [
  { key: "planned",   label: i18nKey("Запланирована") },
  { key: "allocated", label: i18nKey("Выделена") },
  { key: "received",  label: i18nKey("Получена") },
  { key: "used",      label: i18nKey("Освоена") },
  { key: "cancelled", label: i18nKey("Отменена") },
];

export function subsidyStatusLabel(key: string | null | undefined): string {
  if (!key) return "—";
  return SUBSIDY_STATUSES.find(s => s.key === key)?.label || key;
}
