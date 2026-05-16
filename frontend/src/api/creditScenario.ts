// Pack 7.41 — credit-scenario API client.
//
// Wraps fetch calls to /api/credit-scenario/*. Uses the same axios/fetch
// pattern as Vladimir's other API files. If your project uses axios with
// a configured client, swap `fetch` for that instead.

import { apiUrl, getAuthHeaders } from './_base'

export type LenderScope = 'all_uz' | 'state' | 'local' | 'foreign' | 'bond' | 'all'

export interface CreditPortfolioScenario {
  id: string
  macro_scenario_key: string
  name_ru: string | null
  state_forgiveness_pct: number | null
  refinance_rate_delta_pp: number | null
  default_rate_pct: number | null
  repayment_acceleration_pct: number | null
  risk_formula_text: string | null
  risk_rr_by_lender: Record<string, number>
  extra: Record<string, unknown>
  created_at: string
  updated_at: string | null
}

export interface StateSummary {
  scope: string
  loans_count: number
  companies_count: number
  banks_count: number
  sum_total_usd: number
  debt_outstanding_usd: number
  repaid_usd: number
  repaid_pct: number
  guaranteed_usd: number
  guaranteed_pct: number
  avg_rate_pct: number
  fx_exposure_pct: number
  overdue_usd: number
  overdue_count: number
  expected_loss_usd: number
  flagged_loans_count: number
  next_12mo_payments_usd: number
}

export interface DebtRatioRow {
  company_id: string
  company_name: string
  debt_usd: number
  ebitda_usd: number | null
  revenue_usd: number | null
  fcf_usd: number | null
  debt_service_usd: number | null
  debt_to_ebitda: number | null
  debt_to_revenue: number | null
  icr: number | null
  fcf_debt_service: number | null
  risk_zone: string
}

export interface RepaymentQuarterRow {
  period_year: number
  period_quarter: number
  scheduled_usd: number
  paid_usd: number
  overdue_usd: number
  forgiven_usd: number
  custom_usd: number
  is_custom: boolean
  is_history: boolean
}

export interface TopLoanRow {
  loan_id: string
  loan_code: string
  bank: string
  company_name: string
  lender_type: string | null
  is_guaranteed: boolean
  debt_usd: number
  rate: number | null
  date_due: string | null
  forgiveness_pct: number | null
  rate_override: number | null
  rescheduled_to: string | null
  default_probability: number | null
  partial_repayment_pct: number | null
  notes: string | null
}

export interface CustomIndicator {
  id: string
  key: string
  name_ru: string
  input_type: string
  min_value: number | null
  max_value: number | null
  current_value: number | null
  formula_text: string | null
  aggregation: string | null
  source_metric: string | null
  tooltip_ru: string | null
}

export interface FormulaValidateResponse {
  ok: boolean
  error: string | null
  error_position: number | null
  variables_used: string[]
}

export interface FormulaTestResponse {
  ok: boolean
  error: string | null
  loan_code: string | null
  inputs: Record<string, unknown>
  steps: string[]
  final_value: number | null
}


async function _get<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(`/credit-scenario${path}`), {
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error(`GET /credit-scenario${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

async function _send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(apiUrl(`/credit-scenario${path}`), {
    method,
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${method} /credit-scenario${path} failed: ${res.status}`)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}


// Scenarios CRUD
export const listScenarios = () => _get<CreditPortfolioScenario[]>('/scenarios')
export const getScenario = (id: string) => _get<CreditPortfolioScenario>(`/scenarios/${id}`)
export const createScenario = (body: Partial<CreditPortfolioScenario>) =>
  _send<CreditPortfolioScenario>('POST', '/scenarios', body)
export const updateScenario = (id: string, body: Partial<CreditPortfolioScenario>) =>
  _send<CreditPortfolioScenario>('PUT', `/scenarios/${id}`, body)
export const deleteScenario = (id: string) => _send<void>('DELETE', `/scenarios/${id}`)

// Computed
export const fetchStateSummary = (scope: LenderScope, scenarioId?: string) => {
  const qs = new URLSearchParams({ scope })
  if (scenarioId) qs.set('scenario_id', scenarioId)
  return _get<StateSummary>(`/state-summary?${qs}`)
}
export const fetchDebtRatios = (scope: LenderScope, topN = 10) =>
  _get<DebtRatioRow[]>(`/debt-ratios?scope=${scope}&top_n=${topN}`)
export const fetchRepaymentForecast = (
  scope: LenderScope,
  yearsBack = 2,
  yearsForward = 5,
  scenarioId?: string,
) => {
  const qs = new URLSearchParams({
    scope,
    years_back: String(yearsBack),
    years_forward: String(yearsForward),
  })
  if (scenarioId) qs.set('scenario_id', scenarioId)
  return _get<RepaymentQuarterRow[]>(`/repayment-forecast?${qs}`)
}
export const fetchTopLoans = (scope: LenderScope, topN = 10, scenarioId?: string) => {
  const qs = new URLSearchParams({ scope, top_n: String(topN) })
  if (scenarioId) qs.set('scenario_id', scenarioId)
  return _get<TopLoanRow[]>(`/top-loans?${qs}`)
}

// Loan overrides
export const listLoanOverrides = (scenarioId: string) =>
  _get<unknown[]>(`/loan-overrides/${scenarioId}`)
export const upsertLoanOverride = (
  scenarioId: string,
  loanId: string,
  body: Record<string, unknown>,
) => _send<unknown>('PUT', `/loan-overrides/${scenarioId}/${loanId}`, body)
export const deleteLoanOverride = (scenarioId: string, loanId: string) =>
  _send<void>('DELETE', `/loan-overrides/${scenarioId}/${loanId}`)

// Custom indicators
export const listCustomIndicators = () =>
  _get<CustomIndicator[]>('/custom-indicators')
export const createCustomIndicator = (body: Partial<CustomIndicator>) =>
  _send<CustomIndicator>('POST', '/custom-indicators', body)
export const updateCustomIndicator = (id: string, body: Partial<CustomIndicator>) =>
  _send<CustomIndicator>('PUT', `/custom-indicators/${id}`, body)
export const deleteCustomIndicator = (id: string) =>
  _send<void>('DELETE', `/custom-indicators/${id}`)

// Formula
export const validateFormula = (formulaText: string) =>
  _send<FormulaValidateResponse>('POST', '/formula/validate', {
    formula_text: formulaText,
  })
export const testFormula = (formulaText: string, loanId?: string) =>
  _send<FormulaTestResponse>('POST', '/formula/test', {
    formula_text: formulaText,
    loan_id: loanId,
  })
export const getDefaultFormula = () => _get<{ formula_text: string }>('/formula/default')
export const getDefaultRr = () => _get<Record<string, number>>('/default-rr-by-lender')


// ─── Pack 7.41 — Executive Dashboard types ──────────────────────────────────

export interface CreditLenderSegment {
  lender_type: string
  label_ru: string
  debt_usd: number
  loans_count: number
  pct: number
}
export interface CreditCurrencySegment {
  currency: string
  label_ru: string
  debt_usd: number
  loans_count: number
  pct: number
}
export interface CreditMaturitySegment {
  bucket: string
  label_ru: string
  debt_usd: number
  loans_count: number
  pct: number
}

export interface CreditPortfolioOverview {
  portfolio_total_usd: number
  outstanding_usd: number
  repaid_usd: number
  repaid_pct: number
  loans_count: number
  banks_count: number
  companies_count: number
  soes_count: number
  avg_rate_weighted: number
  guaranteed_usd: number
  guaranteed_pct: number
  due_12mo_usd: number
  due_12mo_loans: number
  overdue_usd: number
  overdue_loans: number
  overdue_companies: number
  fx_exposure_usd: number
  fx_exposure_pct: number
  expected_loss_usd: number
  expected_loss_loans: number
  by_lender_type: CreditLenderSegment[]
  by_currency: CreditCurrencySegment[]
  by_maturity: CreditMaturitySegment[]
}

export interface CreditLoanRow {
  loan_id: string
  loan_code: string
  bank: string
  bank_short_name: string | null
  company_name: string
  borrower_unit: string | null
  lender_type: string
  currency: string
  rate: number | null
  rate_text: string | null
  sum_total: number | null
  debt_usd: number | null
  date_get: string | null
  date_due: string | null
  is_guaranteed: boolean
  days_to_maturity: number | null
  overdue_days: number | null
}

export interface CreditDrilldownGroup {
  key: string
  label_ru: string
  debt_usd: number
  pct: number
  loans_count: number
  banks_count?: number
  lender_type?: string
}

// ─── Pack 7.41 endpoints ────────────────────────────────────────────────────

export const getOverview = (scenarioId?: string) => {
  const qs = scenarioId ? `?cp_scenario_id=${scenarioId}` : ''
  return _get<CreditPortfolioOverview>(`/overview${qs}`)
}

export const getDrilldownLoans = (params: {
  lender_type?: string
  currency?: string
  maturity_bucket?: string
  is_guaranteed?: boolean
  overdue_only?: boolean
  limit?: number
}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return _get<CreditLoanRow[]>(`/drilldown/loans?${qs}`)
}

export const getDrilldownByCompany = (params: {
  lender_type?: string
  currency?: string
  maturity_bucket?: string
  top_n?: number
}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) qs.set(k, String(v))
  })
  return _get<CreditDrilldownGroup[]>(`/drilldown/groups-by-company?${qs}`)
}

export const getDrilldownByBank = (params: {
  lender_type?: string
  currency?: string
  maturity_bucket?: string
  top_n?: number
}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) qs.set(k, String(v))
  })
  return _get<CreditDrilldownGroup[]>(`/drilldown/groups-by-bank?${qs}`)
}

export const applyMigrations = () => _send<any>('POST', '/_apply-migrations', {})
