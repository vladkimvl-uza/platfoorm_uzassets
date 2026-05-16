/**
 * scenarios.ts — Pack 7.40
 * ─────────────────────────────────────────────────────────────────
 * Клиент для /scenarios — управление сценариями и override'ами
 * макропоказателей по годам.
 *
 * Доступ:
 *   • Чтение — любой авторизованный пользователь
 *   • Запись — только admin (is_owner или admin.users)
 */
import { api as apiClient } from "./client";

const BASE = "/scenarios";

export interface ScenarioOverride {
  year: number;
  inflation_pct: number | null;
  cb_rate_pct: number | null;
  gdp_growth_pct: number | null;
  usd_rate: number | null;
  eur_rate: number | null;
  uz_budget_trln: number | null;
  notes: string | null;
}

export interface Scenario {
  id: string;
  code: string;
  name_ru: string;
  description: string | null;
  color_hex: string | null;
  sort_order: number;
  is_seeded: boolean;
  overrides: ScenarioOverride[];
}

export interface ScenarioCreate {
  code: string;
  name_ru: string;
  description?: string | null;
  color_hex?: string | null;
  sort_order?: number;
}

export interface ScenarioUpdate {
  name_ru?: string | null;
  description?: string | null;
  color_hex?: string | null;
  sort_order?: number | null;
}

export interface ScenarioOverrideUpsert {
  inflation_pct?: number | null;
  cb_rate_pct?: number | null;
  gdp_growth_pct?: number | null;
  usd_rate?: number | null;
  eur_rate?: number | null;
  uz_budget_trln?: number | null;
  notes?: string | null;
}

// Backend возвращает Decimal как строки — нормализуем к числам
function _normOverride(o: any): ScenarioOverride {
  return {
    year: o.year,
    inflation_pct: o.inflation_pct != null ? Number(o.inflation_pct) : null,
    cb_rate_pct: o.cb_rate_pct != null ? Number(o.cb_rate_pct) : null,
    gdp_growth_pct: o.gdp_growth_pct != null ? Number(o.gdp_growth_pct) : null,
    usd_rate: o.usd_rate != null ? Number(o.usd_rate) : null,
    eur_rate: o.eur_rate != null ? Number(o.eur_rate) : null,
    uz_budget_trln: o.uz_budget_trln != null ? Number(o.uz_budget_trln) : null,
    notes: o.notes ?? null,
  };
}

function _normScenario(s: any): Scenario {
  return {
    id: s.id,
    code: s.code,
    name_ru: s.name_ru,
    description: s.description ?? null,
    color_hex: s.color_hex ?? null,
    sort_order: s.sort_order ?? 0,
    is_seeded: !!s.is_seeded,
    overrides: Array.isArray(s.overrides)
      ? s.overrides.map(_normOverride).sort((a: ScenarioOverride, b: ScenarioOverride) => a.year - b.year)
      : [],
  };
}

export const scenariosApi = {
  /** Список всех сценариев с их override'ами. */
  async list(): Promise<Scenario[]> {
    const { data } = await apiClient.get(BASE);
    return (data as any[]).map(_normScenario)
      .sort((a, b) => (a.sort_order - b.sort_order) || a.code.localeCompare(b.code));
  },

  /** Создать кастомный сценарий. */
  async create(payload: ScenarioCreate): Promise<Scenario> {
    const { data } = await apiClient.post(BASE, payload);
    return _normScenario(data);
  },

  /** Обновить метаданные сценария (имя, описание, цвет, порядок). */
  async update(id: string, payload: ScenarioUpdate): Promise<Scenario> {
    const { data } = await apiClient.patch(`${BASE}/${id}`, payload);
    return _normScenario(data);
  },

  /** Удалить сценарий. Системные (seeded) — нельзя. */
  async remove(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/${id}`);
  },

  /** Upsert override для одного года. NULL поля → очистить значение. */
  async upsertOverride(
    scenarioId: string,
    year: number,
    payload: ScenarioOverrideUpsert,
  ): Promise<ScenarioOverride> {
    const body = { year, ...payload };
    const { data } = await apiClient.put(
      `${BASE}/${scenarioId}/overrides/${year}`,
      body,
    );
    return _normOverride(data);
  },

  /** Удалить запись override для года (полный fallback на base). */
  async deleteOverride(scenarioId: string, year: number): Promise<void> {
    await apiClient.delete(`${BASE}/${scenarioId}/overrides/${year}`);
  },
};
