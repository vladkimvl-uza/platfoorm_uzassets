/**
 * useCreditScenario.ts — Pack 7.42 (replaces Pack 7.41 minimal version).
 *
 * Полный композабл для admin-секции «Кредитная нагрузка» (SystemConfig)
 * + сохраняет совместимость с ExecDashCreditBlock (loadOverview/overview).
 *
 * Все вызовы идут через src/api/creditScenario.ts (там Pinia-auth via _base.ts).
 */
import { ref, shallowRef, computed, watch } from "vue"
import * as api from "@/api/creditScenario"
import { i18nKey } from "@/locale/keys";
import { getCurrentIntlLocale, t } from "@/locale/i18n";



// ─── Module-level reactive singletons ────────────────────────────────────────

// EXEC DASHBOARD ──
const overview = shallowRef<api.CreditPortfolioOverview | null>(null)
const overviewLoading = ref(false)
const overviewError = ref<string | null>(null)

// ADMIN SECTION ──
const scenarios = shallowRef<api.CreditPortfolioScenario[]>([])
const activeScenarioId = ref<string | null>(null)
const scope = ref<api.LenderScope>("all_uz")
const summary = shallowRef<api.StateSummary | null>(null)
const ratios = shallowRef<api.DebtRatioRow[]>([])
const forecast = shallowRef<api.RepaymentQuarterRow[]>([])
const topLoans = shallowRef<api.TopLoanRow[]>([])
const loanOverrides = shallowRef<api.LoanScenarioRow[]>([])
const customIndicators = shallowRef<api.CustomIndicator[]>([])
const defaultFormula = ref<string>("")
const defaultRr = shallowRef<Record<string, number>>({})

const isLoading = ref(false)
const error = ref<string | null>(null)

const SCOPE_LABELS: Record<api.LenderScope, string> = {
  all_uz: i18nKey("Все внутренние РУ"),
  state: i18nKey("Только государство"),
  local: i18nKey("Только местные банки"),
  foreign: i18nKey("Только иностранные"),
  bond: i18nKey("Только облигации"),
  all: i18nKey("Все кредиты"),
}

export function useCreditScenario() {
  // ─── Computed ───
  const activeScenario = computed<api.CreditPortfolioScenario | null>(() => {
    if (!activeScenarioId.value) return null
    return scenarios.value.find((s) => s.id === activeScenarioId.value) || null
  })

  const scopeLabel = computed(() => SCOPE_LABELS[scope.value] || scope.value)

  // ─── EXEC DASHBOARD API) ───
  async function loadOverview(scenarioId?: string) {
    overviewLoading.value = true
    overviewError.value = null
    try {
      overview.value = await api.getOverview(scenarioId)
    } catch (e: any) {
      overviewError.value = e?.message || String(e)
      console.error("[useCreditScenario] loadOverview failed:", e)
    } finally {
      overviewLoading.value = false
    }
  }

  // ─── ADMIN: scenarios CRUD ───
  async function loadScenarios() {
    isLoading.value = true
    error.value = null
    try {
      scenarios.value = await api.listScenarios()
      // Auto-pick first scenario if none active
      if (!activeScenarioId.value && scenarios.value.length > 0) {
        activeScenarioId.value = scenarios.value[0].id
      }
    } catch (e: any) {
      error.value = e?.message || String(e)
    } finally {
      isLoading.value = false
    }
  }

  function setActiveScenario(id: string | null) {
    activeScenarioId.value = id
  }

  async function saveActiveScenario(patch: Partial<api.CreditPortfolioScenario>) {
    if (!activeScenarioId.value) return null
    try {
      const updated = await api.updateScenario(activeScenarioId.value, patch)
      // Replace in list
      scenarios.value = scenarios.value.map((s) => (s.id === updated.id ? updated : s))
      return updated
    } catch (e: any) {
      error.value = t('Сохранение не удалось: {value0}', { value0: e?.message || e })
      throw e
    }
  }

  // ─── ADMIN: scope ───
  function setScope(s: api.LenderScope) {
    scope.value = s
  }

  // ─── ADMIN: read endpoints ───
  async function loadSummary() {
    if (!activeScenarioId.value) return
    try {
      summary.value = await api.fetchStateSummary(scope.value, activeScenarioId.value)
    } catch (e: any) {
      console.error("[useCreditScenario] loadSummary:", e)
      // P1 аудита (тихие сбои): не молчать на load — иначе пустой дашборд
      // неотличим от «данных нет». Зеркалит поведение save-путей файла.
      error.value = t('Не удалось загрузить сводку: {value0}', { value0: e?.message || e })
    }
  }

  async function loadRatios(topN = 6) {
    try {
      ratios.value = await api.fetchDebtRatios(scope.value, topN)
    } catch (e: any) {
      console.error("[useCreditScenario] loadRatios:", e)
      error.value = t('Не удалось загрузить коэффициенты долга: {value0}', { value0: e?.message || e })
    }
  }

  async function loadForecast(yearsBack = 2, yearsForward = 5) {
    if (!activeScenarioId.value) return
    try {
      forecast.value = await api.fetchRepaymentForecast(scope.value, yearsBack, yearsForward, activeScenarioId.value)
    } catch (e: any) {
      console.error("[useCreditScenario] loadForecast:", e)
      error.value = t('Не удалось загрузить прогноз погашения: {value0}', { value0: e?.message || e })
    }
  }

  async function loadTopLoans(topN = 20) {
    if (!activeScenarioId.value) return
    try {
      topLoans.value = await api.fetchTopLoans(scope.value, topN, activeScenarioId.value)
    } catch (e: any) {
      console.error("[useCreditScenario] loadTopLoans:", e)
      error.value = t('Не удалось загрузить крупнейшие займы: {value0}', { value0: e?.message || e })
    }
  }

  // ─── ADMIN: loan overrides ───
  async function loadLoanOverrides() {
    if (!activeScenarioId.value) return
    try {
      loanOverrides.value = await api.listLoanOverrides(activeScenarioId.value)
    } catch (e) {
      console.error("[useCreditScenario] loadLoanOverrides:", e)
    }
  }

  async function upsertLoanOverride(loanId: string, body: Partial<api.LoanScenarioRow>) {
    if (!activeScenarioId.value) return null
    try {
      const r = await api.upsertLoanOverride(activeScenarioId.value, loanId, body)
      await loadLoanOverrides()
      await loadTopLoans()
      return r
    } catch (e: any) {
      error.value = t('Не удалось сохранить override: {value0}', { value0: e?.message || e })
      throw e
    }
  }

  async function deleteLoanOverride(loanId: string) {
    if (!activeScenarioId.value) return
    try {
      await api.deleteLoanOverride(activeScenarioId.value, loanId)
      await loadLoanOverrides()
      await loadTopLoans()
    } catch (e: any) {
      error.value = t('Не удалось удалить override: {value0}', { value0: e?.message || e })
    }
  }

  // ─── ADMIN: custom indicators ───
  async function loadCustomIndicators() {
    try {
      customIndicators.value = await api.listCustomIndicators()
    } catch (e) {
      console.error("[useCreditScenario] loadCustomIndicators:", e)
    }
  }

  async function createCustomIndicator(body: Partial<api.CustomIndicator>) {
    try {
      const r = await api.createCustomIndicator(body)
      await loadCustomIndicators()
      return r
    } catch (e: any) {
      error.value = t('Создание индикатора не удалось: {value0}', { value0: e?.message || e })
      throw e
    }
  }

  async function updateCustomIndicator(id: string, body: Partial<api.CustomIndicator>) {
    try {
      const r = await api.updateCustomIndicator(id, body)
      await loadCustomIndicators()
      return r
    } catch (e: any) {
      error.value = t('Обновление индикатора не удалось: {value0}', { value0: e?.message || e })
      throw e
    }
  }

  async function deleteCustomIndicator(id: string) {
    try {
      await api.deleteCustomIndicator(id)
      await loadCustomIndicators()
    } catch (e: any) {
      error.value = t('Удаление индикатора не удалось: {value0}', { value0: e?.message || e })
    }
  }

  // ─── ADMIN: risk formula ───
  async function validateFormula(formulaText: string) {
    return await api.validateFormula(formulaText)
  }

  async function testFormula(formulaText: string, loanId?: string) {
    return await api.testFormula(formulaText, loanId)
  }

  async function loadDefaults() {
    try {
      const [f, rr] = await Promise.all([api.getDefaultFormula(), api.getDefaultRr()])
      defaultFormula.value = f.formula_text
      defaultRr.value = rr
    } catch (e) {
      console.error("[useCreditScenario] loadDefaults:", e)
    }
  }

  // ─── Загрузить ВСЁ что нужно для admin-таба ───
  async function loadAll() {
    isLoading.value = true
    error.value = null
    try {
      if (!scenarios.value.length) await loadScenarios()
      if (!defaultFormula.value) await loadDefaults()
      await Promise.all([
        loadSummary(),
        loadRatios(),
        loadForecast(),
        loadTopLoans(),
        loadLoanOverrides(),
        loadCustomIndicators(),
      ])
    } catch (e: any) {
      error.value = e?.message || String(e)
    } finally {
      isLoading.value = false
    }
  }

  // Auto-reload data when scope or active scenario change
  watch([scope, activeScenarioId], () => {
    if (activeScenarioId.value) {
      Promise.all([loadSummary(), loadForecast(), loadTopLoans(), loadLoanOverrides()])
    }
  })

  return {
    // EXEC DASHBOARD compat
    overview, overviewLoading, overviewError, loadOverview,
    // ADMIN state
    scenarios, activeScenario, activeScenarioId, scope, scopeLabel,
    summary, ratios, forecast, topLoans, loanOverrides, customIndicators,
    defaultFormula, defaultRr, isLoading, error,
    // ADMIN actions
    loadScenarios, setActiveScenario, saveActiveScenario,
    setScope, loadSummary, loadRatios, loadForecast, loadTopLoans,
    loadLoanOverrides, upsertLoanOverride, deleteLoanOverride,
    loadCustomIndicators, createCustomIndicator, updateCustomIndicator, deleteCustomIndicator,
    validateFormula, testFormula, loadDefaults, loadAll,
    // raw api (escape hatch)
    api,
  }
}

// ─── Formatters (re-exported for components) ─────────────────────────────────
// All take Decimal-as-string from API, so we coerce via Number() first.
function _num(v: any): number | null {
  if (v == null) return null
  const n = typeof v === "number" ? v : Number(v)
  return isNaN(n) ? null : n
}
export function fmtUsdMlrd(v: any): string {
  const n = _num(v); if (n == null) return "—"
  const abs = Math.abs(n)
  if (abs >= 1e9) return t('${value0} млрд', { value0: (n / 1e9).toFixed(2) })
  if (abs >= 1e6) return t('${value0} млн', { value0: (n / 1e6).toFixed(1) })
  if (abs >= 1e3) return t('${value0} тыс', { value0: (n / 1e3).toFixed(1) })
  return `$${n.toFixed(0)}`
}
export function fmtUsdMln(v: any): string {
  const n = _num(v); if (n == null) return "—"
  return t('${value0} млн', { value0: (n / 1e6).toFixed(0) })
}
export function fmtPct(v: any, digits = 1): string {
  const n = _num(v); if (n == null) return "—"
  return `${n.toFixed(digits)}%`
}
export function fmtCount(v: any): string {
  const n = _num(v); if (n == null) return "—"
  return Math.round(n).toLocaleString(getCurrentIntlLocale())
}
export function fmtRate(v: any): string {
  const n = _num(v); if (n == null) return "—"
  return `${(n * 100).toFixed(2)}%`
}
