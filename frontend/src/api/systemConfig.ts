/**
 * systemConfig.ts
 * ─────────────────────────────────────────────────────────────────
 * Клиент для /system-config/yearly-rates — админ-редактируемые
 * системные константы по годам:
 *   • Среднегодовой курс UZS/USD
 *   • Доходная часть бюджета Республики Узбекистан, трлн сум
 *   • Инфляция, ставка ЦБ, рост ВВП — на будущее
 *
 * Pack 7.35
 */
import { api as apiClient } from "./client";

const BASE = "/system-config";

export interface YearlyRate {
  year: number;
  label: string | null;
  is_closed: boolean;
  usd_rate: number | null;
  eur_rate: number | null;
  uz_budget_trln: number | null;
  inflation_pct: number | null;
  cb_rate_pct: number | null;
  gdp_growth_pct: number | null;
}

export interface YearlyRateUpdate {
  label?: string | null;
  is_closed?: boolean | null;
  usd_rate?: number | null;
  eur_rate?: number | null;
  uz_budget_trln?: number | null;
  inflation_pct?: number | null;
  cb_rate_pct?: number | null;
  gdp_growth_pct?: number | null;
}

export interface YearlyRateCreate {
  year: number;
  label?: string | null;
  is_closed?: boolean;
  usd_rate?: number | null;
  eur_rate?: number | null;
  uz_budget_trln?: number | null;
  inflation_pct?: number | null;
  cb_rate_pct?: number | null;
  gdp_growth_pct?: number | null;
}

export const systemConfigApi = {
  /** Получить все годы с курсами и бюджетом (отсортировано по году). */
  async listYearlyRates(): Promise<YearlyRate[]> {
    const { data } = await apiClient.get(`${BASE}/yearly-rates`);
    // Backend возвращает Decimal как строки — нормализуем к числам
    return (data as any[]).map((r) => ({
      year: r.year,
      label: r.label,
      is_closed: r.is_closed,
      usd_rate: r.usd_rate != null ? Number(r.usd_rate) : null,
      eur_rate: r.eur_rate != null ? Number(r.eur_rate) : null,
      uz_budget_trln: r.uz_budget_trln != null ? Number(r.uz_budget_trln) : null,
      inflation_pct: r.inflation_pct != null ? Number(r.inflation_pct) : null,
      cb_rate_pct: r.cb_rate_pct != null ? Number(r.cb_rate_pct) : null,
      gdp_growth_pct: r.gdp_growth_pct != null ? Number(r.gdp_growth_pct) : null,
    }));
  },

  /** Создать новый год в реестре. */
  async createYearlyRate(payload: YearlyRateCreate): Promise<YearlyRate> {
    const { data } = await apiClient.post(`${BASE}/yearly-rates`, payload);
    return {
      ...data,
      usd_rate: data.usd_rate != null ? Number(data.usd_rate) : null,
      eur_rate: data.eur_rate != null ? Number(data.eur_rate) : null,
      uz_budget_trln: data.uz_budget_trln != null ? Number(data.uz_budget_trln) : null,
      inflation_pct: data.inflation_pct != null ? Number(data.inflation_pct) : null,
      cb_rate_pct: data.cb_rate_pct != null ? Number(data.cb_rate_pct) : null,
      gdp_growth_pct: data.gdp_growth_pct != null ? Number(data.gdp_growth_pct) : null,
    };
  },

  /** Обновить одно или несколько полей для года.
   *  allowClosed=true — обходит блокировку для is_closed=true years */
  async updateYearlyRate(
    year: number,
    payload: YearlyRateUpdate,
    options: { allowClosed?: boolean } = {},
  ): Promise<YearlyRate> {
    const params = options.allowClosed ? { allow_closed: true } : {};
    const { data } = await apiClient.patch(`${BASE}/yearly-rates/${year}`, payload, { params });
    return {
      ...data,
      usd_rate: data.usd_rate != null ? Number(data.usd_rate) : null,
      eur_rate: data.eur_rate != null ? Number(data.eur_rate) : null,
      uz_budget_trln: data.uz_budget_trln != null ? Number(data.uz_budget_trln) : null,
      inflation_pct: data.inflation_pct != null ? Number(data.inflation_pct) : null,
      cb_rate_pct: data.cb_rate_pct != null ? Number(data.cb_rate_pct) : null,
      gdp_growth_pct: data.gdp_growth_pct != null ? Number(data.gdp_growth_pct) : null,
    };
  },

  /** Удалить год. force=true — обходит cascade-check (опасно). */
  async deleteYearlyRate(year: number, options: { force?: boolean } = {}): Promise<void> {
    const params = options.force ? { force: true } : {};
    await apiClient.delete(`${BASE}/yearly-rates/${year}`, { params });
  },
};
