/**
 * Business Plan + KPI API client.
 * 1:1 mirror of backend routes /bp/* and /kpi/*.
 */
import { api, type ModerationQueuedTag } from "./client";
import { fmtNumber } from "@/locale";
import { getCurrentLocale, t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";


// ─── Constants (mirror legacy BP_FIELDS, BP_PERIODS) ─────────────

export const BP_PERIODS: { key: BpPeriod; label: string }[] = [
  { key: "annual", label: i18nKey("Год") },
  { key: "q1", label: "Q1" },
  { key: "q2", label: "Q2" },
  { key: "q3", label: "Q3" },
  { key: "q4", label: "Q4" },
];

export type BpPeriod = "annual" | "q1" | "q2" | "q3" | "q4";

export interface BpFieldMeta {
  key: string;
  label: string;
  group: "opRevenue" | "opExpenses" | "opResult" | "finActivity" | "final";
  auto: boolean;
  formula?: string;
  positive?: boolean;
  sub?: boolean;
  /** «Итог», считаемый по формуле, но ДОПУСКАЮЩИЙ ручное переопределение по
   *  компаниям (напр. чистая прибыль): показываем ввод во всех колонках, факт —
   *  с автоподстановкой из НСБУ, план/прогноз — с подсказкой расчёта. Сохранённое
   *  значение перебивает формулу (бэкенд bp_compute уважает stored > derived). */
  overridable?: boolean;
}

// Default — also returned by GET /bp/metrics
export const BP_FIELDS: BpFieldMeta[] = [
  { key: "revenue",     label: i18nKey("Чистая выручка от реализации"),                   group: "opRevenue", auto: false },
  { key: "cogs",        label: i18nKey("Себестоимость реализованной продукции"),          group: "opRevenue", auto: false, positive: true },
  { key: "grossProfit", label: i18nKey("Валовая прибыль"),                                 group: "opRevenue", auto: true,  formula: "revenue - cogs" },
  { key: "opExpenses",  label: i18nKey("Расходы периода"),                                 group: "opExpenses", auto: false, positive: true },
  { key: "sellExp",     label: i18nKey("— расходы на реализацию"),                         group: "opExpenses", auto: false, positive: true, sub: true },
  { key: "adminExp",    label: i18nKey("— административные расходы"),                      group: "opExpenses", auto: false, positive: true, sub: true },
  { key: "otherOpExp",  label: i18nKey("— прочие операционные расходы"),                   group: "opExpenses", auto: false, positive: true, sub: true },
  { key: "otherOpInc",  label: i18nKey("Прочие доходы от основной деятельности"),          group: "opResult",   auto: false },
  { key: "opProfit",    label: i18nKey("Операционная прибыль"),                            group: "opResult",   auto: true,  formula: "grossProfit - opExpenses + otherOpInc" },
  { key: "finIncome",   label: i18nKey("Финансовые доходы"),                               group: "finActivity", auto: false },
  { key: "divIncome",   label: i18nKey("— доходы в виде дивидендов"),                      group: "finActivity", auto: false, sub: true },
  { key: "intIncome",   label: i18nKey("— доходы в виде процентов"),                       group: "finActivity", auto: false, sub: true },
  { key: "fxIncome",    label: i18nKey("— доходы от курсовых разниц"),                     group: "finActivity", auto: false, sub: true },
  { key: "otherFinInc", label: i18nKey("— прочие фин. доходы"),                            group: "finActivity", auto: false, sub: true },
  { key: "finCost",     label: i18nKey("Финансовые расходы"),                              group: "finActivity", auto: false, positive: true },
  { key: "intExp",      label: i18nKey("— расходы в виде процентов"),                      group: "finActivity", auto: false, positive: true, sub: true },
  { key: "fxLoss",      label: i18nKey("— убытки от курсовых разниц"),                     group: "finActivity", auto: false, positive: true, sub: true },
  { key: "otherFinExp", label: i18nKey("— прочие фин. расходы"),                           group: "finActivity", auto: false, positive: true, sub: true },
  { key: "hhProfit",    label: i18nKey("Прибыль от общехоз. деятельности"),                group: "final",      auto: true, formula: "opProfit + finIncome - finCost" },
  { key: "pbt",         label: i18nKey("Прибыль до налогообложения"),                      group: "final",      auto: true, formula: "hhProfit" },
  { key: "tax",         label: i18nKey("Налог на прибыль"),                                group: "final",      auto: false, positive: true },
  { key: "profit",      label: i18nKey("Чистая прибыль (убыток) периода"),                 group: "final",      auto: true, formula: "pbt - tax", overridable: true },
];

// ─── Field-set helpers ─────────────────────────────────────────────

/** True for expense metrics (positive=true): cogs, opExpenses (+ subs),
 *  finCost (+ subs), tax. Used by «Только расходы» BP toggle. */
export function isExpenseField(f: BpFieldMeta): boolean {
  return f.positive === true;
}

/** True for income metrics — opposite of expense, excluding auto/calculated
 *  fields (grossProfit, opProfit, hhProfit, pbt, profit) since those are
 *  derived totals, not raw income. */
export function isIncomeField(f: BpFieldMeta): boolean {
  return !f.auto && !f.positive;
}

/** Filter BP_FIELDS down to the «expenses-only» subset. The toggle hides
 *  income/calculated fields. Parent-without-children combinations stay
 *  intact: e.g. `opExpenses` keeps its 3 `sub: true` siblings, `finCost`
 *  keeps its 3 subs. Standalone `cogs` and `tax` keep no subs. */
export function expenseFields(): BpFieldMeta[] {
  return BP_FIELDS.filter(isExpenseField);
}

/** Income-only subset (revenue + finIncome group). */
export function incomeFields(): BpFieldMeta[] {
  return BP_FIELDS.filter(isIncomeField);
}

export type BpViewMode = "all" | "expenses" | "income";

/** Переопределяемые «итоги» (чистая прибыль и т.п.) — авто по формуле, но
 *  редактируемые вручную. Показываем их нижней строкой-итогом и в income, и в
 *  expenses, чтобы бухгалтер/владелец мог задать/сверить чистую прибыль в любом
 *  из режимов (в «all» они уже присутствуют внутри BP_FIELDS). */
export function overridableFinals(): BpFieldMeta[] {
  return BP_FIELDS.filter(f => f.overridable === true);
}

/** Helper for UI: return BP_FIELDS or subset depending on view-mode. */
export function bpFieldsFor(viewMode: BpViewMode): BpFieldMeta[] {
  if (viewMode === "expenses") return [...expenseFields(), ...overridableFinals()];
  if (viewMode === "income")   return [...incomeFields(), ...overridableFinals()];
  return BP_FIELDS;
}

// ─── Types ─────────────────────────────────────────────────────────

export interface AvailableCompany {
  company_id: string;
  company_name_ru: string;
  company_code: string | null;
  sector_code: string | null;
  sector_color: string | null;
  years: number[];
}

export interface BpCell {
  plan: string | number | null;
  expect: string | number | null;
  fact: string | number | null;
  fact_auto?: boolean;
  /** источник автоподстановки факта: 'nsbu' (финотчётность) | 'ytd' (нараст.
   *  итог Q4 — кварталы хранятся нарастающим итогом, q4 = весь год) */
  fact_source?: "nsbu" | "ytd" | null;
  /** значение источника (приходит всегда — для сравнения с ручным фактом в редакторе) */
  fact_source_value?: string | number | null;
}

export interface BpComputed {
  company_id: string;
  year: number;
  period: BpPeriod;
  metrics: Record<string, BpCell>;
}

export interface BpRecordUpsert {
  company_id: string;
  year: number;
  period: BpPeriod;
  metric: string;
  plan?: number | null;
  expect?: number | null;
  fact?: number | null;
}

/** При квартальном периоде plan/expect/fact — дельты «за квартал», cum_* —
 *  нарастающим итогом. Σ дельт ≠ cum при разном покрытии компаний. */
export interface BpMetricTotal {
  metric: string;
  plan: string | number | null;
  expect: string | number | null;
  fact: string | number | null;
  has_plan: boolean;
  has_expect: boolean;
  has_fact: boolean;
  cum_plan?: string | number | null;
  cum_expect?: string | number | null;
  cum_fact?: string | number | null;
}

export interface BpCompanyRow {
  company_id: string;
  company_name_ru: string;
  sector_code: string | null;
  sector_color: string | null;
  rev_fact: string | number | null;
  rev_plan: string | number | null;
  pct: number | null;
}

export interface BpSectorRow {
  sector_code: string;
  label: string;
  sum_revenue: string | number;
}

/** Квартальная строка сводки. Кварталы БП хранятся НАРАСТАЮЩИМ ИТОГОМ (НСБУ:
 *  q1=1 кв, q2=полугодие, q3=9 мес, q4=год): cum_* — Σ хранимых YTD по компаниям,
 *  *_delta — «за квартал» (Σ по-компанейских дельт, null-guard по компании).
 *  plan/fact ≡ cum_plan/cum_fact (обратная совместимость). */
export interface BpQuarterRow {
  q: BpPeriod;
  plan: string | number | null;        // DEPRECATED ≡ cum_plan
  fact: string | number | null;        // DEPRECATED ≡ cum_fact
  expect?: string | number | null;     // ≡ cum_expect
  cum_plan?: string | number | null;
  cum_expect?: string | number | null;
  cum_fact?: string | number | null;
  plan_delta?: string | number | null;
  expect_delta?: string | number | null;
  fact_delta?: string | number | null;
  co_count_cum_fact?: number;
  co_count_fact_delta?: number;
  co_count_cum_plan?: number;
}

/** Зеркало backend ytd_to_deltas: «за квартал» = ytd[n] − ytd[n−1] (q1 = ytd[0]);
 *  честный null, когда сам квартал ИЛИ предыдущий не заполнен. */
export function ytdToDeltas(vals: (number | null)[]): (number | null)[] {
  const out: (number | null)[] = [];
  let prev: number | null = null;
  vals.forEach((v, i) => {
    if (v == null || (i > 0 && prev == null)) out.push(null);
    else out.push(i > 0 ? v - (prev as number) : v);
    prev = v;
  });
  return out;
}

export interface BpSummary {
  year: number;
  period: BpPeriod;
  co_count: number;
  totals: BpMetricTotal[];
  prev_totals: BpMetricTotal[];
  by_company: BpCompanyRow[];
  by_sector: BpSectorRow[];
  by_quarter: BpQuarterRow[];
}

export interface BpAttentionIssue {
  severity: "high" | "medium" | "low";
  title: string;
  value: string;
  detail: string;
}

export interface BpComment {
  id: string;
  company_id: string;
  year: number;
  period: BpPeriod;
  body: string;
  author_id: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Прогноз БП (детерминированный движок core/forecast) ───────────
// Использует ForecastBlock/ForecastSeriesPoint, объявленные ниже (KPI-секция).
export interface BpMetricForecast {
  key: string; label: string; unit: string | null; direction: string;
  plan: number | null; expect: number | null; fact: number | null;
  annual: ForecastBlock; history: ForecastSeriesPoint[];
}
export interface BpCompanyForecast {
  company_id: string; company_code: string | null; company_name: string;
  base_year: number; horizon: number; future_years: number[];
  metrics: BpMetricForecast[]; note: string;
}

/** Прогноз оставшихся кварталов года (ghost-бары «Динамики по кварталам»).
 *  Движок forecast_quarters на ДЕЛЬТАХ «за квартал»; value/low/high — тоже
 *  величины за квартал. */
export interface BpQuarterProjection {
  period: string;                   // 'q1'..'q4'
  value: number | null;
  low: number | null;
  high: number | null;
  co_count: number;
}
/** Черновик плана (генератор): предложение по вводимой метрике ОФР. */
export interface BpPlanDraftMetric {
  key: string;
  label: string;
  annual: number | null;
  low: number | null;
  high: number | null;
  quarters_ytd: (number | null)[] | null;   // [q1..q4] НАРАСТАЮЩИМ итогом
  method: string;                            // cagr|ols|none
  confidence: string;
  note: string;
}
export interface BpPlanDraft {
  company_id: string;
  target_year: number;
  base_years: number[];
  metrics: BpPlanDraftMetric[];
  note: string;
}

export interface BpQuarterOutlook {
  year: number;
  metric: string;
  scope: "company" | "portfolio";
  company_id: string | null;
  co_count: number;
  q_plan: (number | null)[];
  q_fact: (number | null)[];
  projections: BpQuarterProjection[];
  expected_year: number | null;
  method: string;                   // pace|seasonal|run_rate|plan|actual|mixed|none
  confidence: string;               // high|medium|low|none
  note: string;
}

// ─── KPI Types ─────────────────────────────────────────────────────

export type KpiPeriod = "year" | "q1" | "q2" | "q3" | "q4";
export type KpiStatus = "over" | "hit" | "risk" | "crit" | "fail";

export interface KpiIndicator {
  id: string;
  manager_id: string;
  sort_order: number;
  name: string;
  unit: string | null;
  direction?: "up" | "down";   // 'up' = больше=лучше (по умолч.), 'down' = меньше=лучше
  weight: string | number;
  plan_year: string | number | null;
  fact_year: string | number | null;
  q1_weight: string | number;
  q2_weight: string | number;
  q3_weight: string | number;
  q4_weight: string | number;
  q1_plan: string | number | null;
  q1_fact: string | number | null;
  q2_plan: string | number | null;
  q2_fact: string | number | null;
  q3_plan: string | number | null;
  q3_fact: string | number | null;
  q4_plan: string | number | null;
  q4_fact: string | number | null;
  /** Конвенция кварталов строки: 'per_quarter' — суммы за квартал (год = Σ),
   *  'cumulative' — нарастающим итогом (Q2 = полугодие, Q4 = год). */
  quarters_mode?: "per_quarter" | "cumulative";
  notes: string | null;
  // Связь с метрикой Бизнес-плана (reference-pull). null/"" = свободный KPI.
  bp_metric_key?: string | null;
  // Read-through план/факт из BP/НСБУ для связанной строки (не из БД индикатора):
  bp_resolved?: boolean;
  bp_source?: string | null;            // 'nsbu' | 'ytd' | 'bp_plan' | null
  bp_plan_resolved?: string | number | null;
  bp_fact_resolved?: string | number | null;
  bp_expect_resolved?: string | number | null;   // «ожидаемое» из БП (annual)
}

export interface KpiManager {
  id: string;
  company_id: string;
  year: number;
  sort_order: number;
  title: string;
  short_title: string | null;
  role: string | null;
  indicators: KpiIndicator[];
}

// ─── Прогноз KPI (детерминированный движок core/forecast) ─────────
export interface ForecastPoint {
  period: string;                 // 'q3' | 'q4' | '2027'
  value: number | null;
  low: number | null;
  high: number | null;
  quarters?: (number | null)[] | null;   // [q1..q4] разбивка года (сезонность)
}
export interface ForecastBlock {
  method: string;                 // 'pace'|'seasonal'|'run_rate'|'plan'|'actual'|'ols'|'cagr'|'none'
  confidence: string;             // 'high'|'medium'|'low'|'none'
  points_used: number;
  note: string;
  expected_year: number | null;
  projections: ForecastPoint[];
}
export interface ForecastSeriesPoint { year: number; fact: number | null; plan: number | null; }
export interface IndicatorForecast {
  name: string; unit: string | null; direction: string; weight: number;
  bp_metric_key: string | null; manager: string; role: string | null;
  plan_year: number | null; fact_year: number | null;
  q_plan: (number | null)[]; q_fact: (number | null)[];
  quarterly: ForecastBlock; annual: ForecastBlock; history: ForecastSeriesPoint[];
}
export interface ManagerForecast { title: string; role: string | null; indicators: IndicatorForecast[]; }

/** Черновик планов KPI (генератор «Рассчитать показатели»). */
export interface KpiPlanDraftIndicator {
  name: string;
  manager: string;
  linked: boolean;                          // план тянется из БП (reference-pull)
  current_plan_year: number | null;
  proposed_plan_year: number | null;
  low: number | null;
  high: number | null;
  proposed_q: (number | null)[] | null;     // суммы ЗА квартал (конвенция KPI)
  method: string;
  confidence: string;
  note: string;
}
export interface KpiPlanDraft {
  company_id: string;
  target_year: number;
  base_years: number[];
  indicators: KpiPlanDraftIndicator[];
  note: string;
}
export interface CompanyForecast {
  company_id: string; company_code: string | null; company_name: string;
  base_year: number; horizon: number; future_years: number[];
  managers: ManagerForecast[];
  completion: ForecastBlock | null; completion_history: ForecastSeriesPoint[];
  note: string;
}

export interface KpiIndicatorUpsert {
  sort_order?: number;
  name: string;
  unit?: string | null;
  direction?: "up" | "down";
  weight?: number;
  plan_year?: number | null;
  fact_year?: number | null;
  q1_weight?: number;
  q2_weight?: number;
  q3_weight?: number;
  q4_weight?: number;
  q1_plan?: number | null;
  q1_fact?: number | null;
  q2_plan?: number | null;
  q2_fact?: number | null;
  q3_plan?: number | null;
  q3_fact?: number | null;
  q4_plan?: number | null;
  q4_fact?: number | null;
  /** Конвенция кварталов строки — ОБЯЗАТЕЛЬНО возвращать при сохранении:
   *  PUT пересоздаёт дерево, пропуск поля сбросит признак в 'per_quarter'. */
  quarters_mode?: "per_quarter" | "cumulative";
  notes?: string | null;
  bp_metric_key?: string | null;   // связь с метрикой Бизнес-плана (reference-pull)
}

export interface KpiManagerUpsert {
  sort_order?: number;
  title: string;
  short_title?: string | null;
  role?: string | null;
  indicators: KpiIndicatorUpsert[];
}

export interface KpiCompanyYearUpsert {
  company_id: string;
  year: number;
  managers: KpiManagerUpsert[];
}

export interface KpiIndPayload {
  co_id: string;
  co_name: string;
  mgr_idx: number;
  mgr: string;
  ind_idx: number;
  ind_id: string;
  name: string;
  unit: string | null;
  weight: string | number;
  plan: string | number | null;
  fact: string | number | null;
  ratio: number | null;
  pct: number | null;              // clamp[0;150] для отображения
  pct_raw?: number | null;         // без клэмпа
  is_anomaly?: boolean;            // pct_raw вне [0;300] — вероятная ошибка данных
  source?: string | null;          // происхождение plan/fact: annual|ytd|quarter|nsbu|bp_plan
  status: KpiStatus | null;
  bp_metric_key?: string | null;
}

export interface KpiCompanyRow {
  company_id: string;
  co_name: string;
  sector_code: string | null;
  sector_color: string | null;
  count: number;
  ind_total?: number;
  hit: number;
  risk: number;
  crit: number;
  pct: number;
  low_sample?: boolean;
  weight_skew?: boolean;
}

export interface KpiSectorRow {
  sector_code: string;
  label: string;
  pct: number | null;
  count: number;
  co_count: number;
  low_sample?: boolean;
}

export interface KpiQuarterAgg {
  q: "q1" | "q2" | "q3" | "q4";
  plan: number | null;
  fact: number | null;
}

export interface KpiSummary {
  year: number;
  period: string;
  co_count: number;
  total_count: number;
  overall: number | null;
  low_sample?: boolean;
  has_plan?: boolean;
  over_count: number;
  hit_count: number;
  risk_count: number;
  crit_count: number;
  fail_count: number;
  distribution: Record<KpiStatus, KpiIndPayload[]>;
  by_company: KpiCompanyRow[];
  by_sector: KpiSectorRow[];
  by_quarter: KpiQuarterAgg[];
  achievements: KpiIndPayload[];
  issues: KpiIndPayload[];
}

export interface KpiAttentionIssue {
  severity: "high" | "medium" | "low";
  title: string;
  value: string;
  detail: string;
}

export interface KpiComment {
  id: string;
  company_id: string;
  year: number;
  period: string;
  body: string;
  author_id: string | null;
  created_at: string;
  updated_at: string;
}

// ─── API methods ──────────────────────────────────────────────────

export const bpApi = {
  async getMetrics(): Promise<BpFieldMeta[]> {
    const { data } = await api.get<BpFieldMeta[]>("/bp/metrics");
    return data;
  },

  async availableCompanies(): Promise<AvailableCompany[]> {
    const { data } = await api.get<AvailableCompany[]>("/bp/available-companies");
    return data;
  },

  async getComputed(companyId: string, year: number, period: BpPeriod): Promise<BpComputed> {
    const { data } = await api.get<BpComputed>(`/bp/${companyId}/${year}/${period}`);
    return data;
  },

  /** Детерминированный прогноз финансовых метрик БП (годы + кварталы). */
  async getForecast(companyId: string, baseYear: number, horizon = 2): Promise<BpCompanyForecast> {
    const { data } = await api.get<BpCompanyForecast>(
      `/bp/forecast/${companyId}/${baseYear}`, { params: { horizon } },
    );
    return data;
  },

  /** Прогноз оставшихся кварталов года: companyId → по компании, без — сводно. */
  async getQuarterOutlook(year: number, metric: string, companyId?: string | null): Promise<BpQuarterOutlook> {
    const { data } = await api.get<BpQuarterOutlook>(
      `/bp/quarter-forecast/${year}`,
      { params: { metric, ...(companyId ? { company_id: companyId } : {}) } },
    );
    return data;
  },

  /** Черновик плана на год из истории (генератор «Рассчитать показатели»). */
  async getPlanDraft(companyId: string, targetYear: number): Promise<BpPlanDraft> {
    const { data } = await api.get<BpPlanDraft>(`/bp/plan-draft/${companyId}/${targetYear}`);
    return data;
  },

  async getRaw(companyId: string, year: number): Promise<{
    data: Record<string, Record<string, BpCell>>;
    editorToken: string | null;
  }> {
    const resp = await api.get(`/bp/raw/${companyId}/${year}`);
    return {
      data: resp.data,
      editorToken: (resp.headers["x-editor-token"] as string) || null,
    };
  },

  async upsertCell(payload: BpRecordUpsert): Promise<{ ok: boolean }> {
    const { data } = await api.post("/bp/upsert", payload);
    return data;
  },

  async bulkUpsert(
    records: BpRecordUpsert[],
    editorToken?: string | null,
  ): Promise<{ upserted: number; editorToken: string | null } | ModerationQueuedTag> {
    // If-Match — optimistic-lock (409 EditorConflict, если кто-то сохранил параллельно)
    const resp = await api.post(
      "/bp/bulk-upsert",
      { records },
      editorToken ? { headers: { "If-Match": editorToken } } : undefined,
    );
    if (resp.data && resp.data.queued) return resp.data as ModerationQueuedTag;
    return {
      upserted: resp.data.upserted,
      editorToken: (resp.headers["x-editor-token"] as string) || null,
    };
  },

  async deleteYear(companyId: string, year: number): Promise<void> {
    await api.delete(`/bp/${companyId}/${year}`);
  },

  async getSummary(year: number, period: BpPeriod, metric: string = "revenue"): Promise<BpSummary> {
    const { data } = await api.get<BpSummary>(
      `/bp/summary/${year}/${period}`,
      { params: { metric } },
    );
    return data;
  },

  async getAttention(companyId: string, year: number, period: BpPeriod): Promise<BpAttentionIssue[]> {
    const { data } = await api.get<BpAttentionIssue[]>(`/bp/attention/${companyId}/${year}/${period}`);
    return data;
  },

  async getComment(companyId: string, year: number, period: BpPeriod): Promise<BpComment | null> {
    const { data } = await api.get<BpComment | null>(`/bp/comment/${companyId}/${year}/${period}`);
    return data;
  },

  async upsertComment(companyId: string, year: number, period: BpPeriod, body: string): Promise<BpComment> {
    const { data } = await api.put<BpComment>("/bp/comment", { company_id: companyId, year, period, body });
    return data;
  },
};

export const kpiApi = {
  async availableCompanies(): Promise<AvailableCompany[]> {
    const { data } = await api.get<AvailableCompany[]>("/kpi/available-companies");
    return data;
  },

  /** GET KPI tree + editor token. Pack 153: caller stores `editorToken`
   *  and echoes it back on the next save via `replaceCompanyYear(..., token)`
   *  to detect concurrent edits. */
  async getCompanyYear(companyId: string, year: number): Promise<{
    managers: KpiManager[];
    editorToken: string | null;
  }> {
    const resp = await api.get<KpiManager[]>(`/kpi/${companyId}/${year}`);
    return {
      managers: resp.data,
      editorToken: (resp.headers["x-editor-token"] as string) || null,
    };
  },

  async replaceCompanyYear(
    payload: KpiCompanyYearUpsert,
    editorToken?: string | null,
  ): Promise<{
    result: { managers: number; indicators: number } | ModerationQueuedTag;
    editorToken: string | null;
  }> {
    const resp = await api.put(
      `/kpi/${payload.company_id}/${payload.year}`,
      payload,
      editorToken ? { headers: { "If-Match": editorToken } } : undefined,
    );
    return {
      result: resp.data,
      editorToken: (resp.headers["x-editor-token"] as string) || null,
    };
  },

  async deleteYear(companyId: string, year: number): Promise<void> {
    await api.delete(`/kpi/${companyId}/${year}`);
  },

  /** Детерминированный прогноз KPI компании (кварталы + будущие годы). */
  async getForecast(companyId: string, baseYear: number, horizon = 2): Promise<CompanyForecast> {
    const { data } = await api.get<CompanyForecast>(
      `/kpi/${companyId}/forecast/${baseYear}`, { params: { horizon } },
    );
    return data;
  },

  /** Черновик планов KPI на год из истории (генератор «Рассчитать показатели»). */
  async getPlanDraft(companyId: string, targetYear: number): Promise<KpiPlanDraft> {
    const { data } = await api.get<KpiPlanDraft>(`/kpi/plan-draft/${companyId}/${targetYear}`);
    return data;
  },

  async getSummary(year: number, period: KpiPeriod | "annual"): Promise<KpiSummary> {
    const p = period === "annual" ? "year" : period;
    const { data } = await api.get<KpiSummary>(`/kpi/summary/${year}/${p}`);
    return data;
  },

  async getAttention(companyId: string, year: number, period: string): Promise<KpiAttentionIssue[]> {
    const { data } = await api.get<KpiAttentionIssue[]>(`/kpi/attention/${companyId}/${year}/${period}`);
    return data;
  },

  async getComment(companyId: string, year: number, period: string): Promise<KpiComment | null> {
    const { data } = await api.get<KpiComment | null>(`/kpi/comment/${companyId}/${year}/${period}`);
    return data;
  },

  async upsertComment(companyId: string, year: number, period: string, body: string): Promise<KpiComment> {
    const { data } = await api.put<KpiComment>("/kpi/comment", { company_id: companyId, year, period, body });
    return data;
  },

  async listTemplates(): Promise<{
    templates: Array<{ company_code: string; company_id: string | null; company_name: string | null }>;
  }> {
    const { data } = await api.get(`/kpi/templates`);
    return data;
  },

  async loadTemplate(companyCode: string, year: number): Promise<{
    company_id: string; company_name: string; company_code: string; year: number;
    managers_added: number; indicators_added: number;
  }> {
    const { data } = await api.post(`/kpi/load-template/${encodeURIComponent(companyCode)}/${year}`);
    return data;
  },

  /** @deprecated use loadTemplate('ngmk', year) */
  async loadNgmkTemplate(year: number) {
    return this.loadTemplate("ngmk", year);
  },
};

// ─── Helpers ──────────────────────────────────────────────────────

export function num(v: string | number | null | undefined): number {
  if (v == null) return 0;
  return typeof v === "number" ? v : Number(v);
}

export function bpFmt(v: string | number | null | undefined): string {
  if (v == null) return "—";
  const n = num(v);
  if (isNaN(n)) return "—";
  const av = Math.abs(n);
  if (av >= 1000) return fmtNumber(Math.round(n), getCurrentLocale(), { decimals: 0 });
  if (av >= 10) return fmtNumber(n, getCurrentLocale(), { decimals: 0 });
  return fmtNumber(n, getCurrentLocale(), { decimals: 2 });
}

/** Auto-scale: >= 1000 млрд → trln, otherwise млрд */
export function bpFmtScaled(v: string | number | null | undefined): { value: string; unit: string } {
  if (v == null) return { value: "—", unit: "" };
  const n = num(v);
  const av = Math.abs(n);
  if (av >= 1000) {
    return {
      value: fmtNumber(n / 1000, getCurrentLocale(), { decimals: 1 }),
      unit: t("трлн"),
    };
  }
  if (av >= 100) return { value: fmtNumber(Math.round(n), getCurrentLocale(), { decimals: 0 }), unit: t("млрд") };
  return {
    value: fmtNumber(n, getCurrentLocale(), { decimals: 1 }),
    unit: t("млрд"),
  };
}

export function bpPctColor(p: number | null): string {
  if (p == null) return "#94A3B8";
  if (p >= 1.0) return "#1D9E75";
  if (p >= 0.9) return "#EF9F27";
  return "#E24B4A";
}

export function bpDeltaColor(deltaPct: number): string {
  if (deltaPct >= 0) return "#3D9C72";
  if (deltaPct >= -5) return "#C99A4D";
  return "#C36868";
}

/** Mirror legacy _kpisColor */
export function kpiStatusColor(pct: number): string {
  if (pct >= 100) return "#1D9E75";
  if (pct >= 95) return "#7DC4A0";
  if (pct >= 75) return "#EF9F27";
  if (pct >= 50) return "#E24B4A";
  return "#B91C1C";
}

export function kpiStatusLabel(s: KpiStatus): string {
  switch (s) {
    case "over": return t('Превышено');
    case "hit": return t('На цели');
    case "risk": return t('В риске');
    case "crit": return t('Критично');
    case "fail": return t('Провал');
  }
}

export function shortenCompanyName(co: string | null | undefined): string {
  if (!co) return "";
  // i18n-exempt-start -- legal-form cleanup for company names, not UI copy.
  return String(co)
    .replace(/^АО\s*"?/, "")
    .replace(/^"/, "")
    .replace(/"$/, "")
    .replace(/\s*ДК$/, "")
    .replace(/\s*АЖ$/, " АЖ");
  // i18n-exempt-end
}
