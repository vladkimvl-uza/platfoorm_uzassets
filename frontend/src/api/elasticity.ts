/**
 * elasticity.ts — Pack 7.43 API client.
 * Использует тот же fetch+_base.ts паттерн что и creditScenario.ts.
 */
import { apiUrl, getAuthHeaders } from "./_base"

// ─── Types ──────────────────────────────────────────────────────────────────
export type MacroFactor =
  | "inflation_pct" | "cb_rate_pct" | "usd_rate" | "eur_rate"
  | "gdp_growth_pct" | "oil_price_brent"

export type TargetMetric =
  | "revenue" | "ebitda" | "opex" | "capex" | "debt_service" | "net_income"

export interface ElasticityCoef {
  id: string
  scenario_id: string | null
  company_id: string | null
  macro_factor: MacroFactor
  target_metric: TargetMetric
  beta: number | string
  notes: string | null
  source: "manual" | "seed_sector_default" | "imported"
  created_at: string
  updated_at: string
}

export interface ElasticityUpsert {
  scenario_id?: string | null
  company_id?: string | null
  macro_factor: MacroFactor
  target_metric: TargetMetric
  beta: number
  notes?: string | null
}

export interface ProjectEffect {
  id: string
  project_id: string
  effective_year: number
  target_metric: TargetMetric
  delta_value_uzs_mln: number | string | null
  delta_pct: number | string | null
  probability_pct: number | string
  confidence: "low" | "medium" | "high"
  notes: string | null
  extra: any
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface ProjectEffectUpsert {
  project_id: string
  effective_year: number
  target_metric: TargetMetric
  delta_value_uzs_mln?: number | null
  delta_pct?: number | null
  probability_pct?: number
  confidence?: "low" | "medium" | "high"
  notes?: string | null
}

export interface DecompositionComponent {
  label_ru: string
  contribution_uzs_mln: number | string
  contribution_pct: number | string
  kind: "base" | "macro" | "project" | "total"
  detail?: any
}

export interface DecompositionResult {
  company_id: string | null
  company_name: string | null
  target_metric: TargetMetric
  year: number
  base_value_uzs_mln: number | string
  forecast_value_uzs_mln: number | string
  macro_effect_uzs_mln: number | string
  projects_effect_uzs_mln: number | string
  components: DecompositionComponent[]
  explanation: string
}

export interface Constants {
  macro_factors: Array<{ code: MacroFactor; label_ru: string }>
  target_metrics: Array<{ code: TargetMetric; label_ru: string }>
  sector_defaults_hint: string
}

// ─── Fetch helpers ──────────────────────────────────────────────────────────
async function _get<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(`/elasticity${path}`), { headers: getAuthHeaders() })
  if (!res.ok) throw new Error(`GET /elasticity${path} failed: ${res.status}`)
  return res.json()
}
async function _send<T>(method: string, path: string, body?: any): Promise<T> {
  const res = await fetch(apiUrl(`/elasticity${path}`), {
    method,
    headers: getAuthHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${method} /elasticity${path} failed: ${res.status}`)
  if (res.status === 204) return undefined as T
  return res.json()
}

// ─── Endpoints ──────────────────────────────────────────────────────────────
export const getConstants = () => _get<Constants>("/constants")

export const listCoefficients = (params: {
  scenario_id?: string
  company_id?: string
  include_global?: boolean
} = {}) => {
  const qs = new URLSearchParams()
  if (params.scenario_id) qs.set("scenario_id", params.scenario_id)
  if (params.company_id) qs.set("company_id", params.company_id)
  if (params.include_global !== undefined) qs.set("include_global", String(params.include_global))
  return _get<ElasticityCoef[]>(`/coefficients?${qs}`)
}

export const upsertCoefficient = (payload: ElasticityUpsert) =>
  _send<ElasticityCoef>("PUT", "/coefficients", payload)

export const deleteCoefficient = (id: string) =>
  _send<{ deleted: boolean }>("DELETE", `/coefficients/${id}`)

export const listProjectEffects = (params: {
  project_id?: string
  effective_year?: number
  target_metric?: string
  company_id?: string
} = {}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) qs.set(k, String(v))
  })
  return _get<ProjectEffect[]>(`/project-effects?${qs}`)
}

export const upsertProjectEffect = (payload: ProjectEffectUpsert) =>
  _send<ProjectEffect>("PUT", "/project-effects", payload)

export const deleteProjectEffect = (id: string) =>
  _send<{ deleted: boolean }>("DELETE", `/project-effects/${id}`)

export const getDecomposition = (params: {
  scenario_id: string
  target_metric: TargetMetric
  target_year: number
  company_id?: string
  base_year?: number
}) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) qs.set(k, String(v))
  })
  return _get<DecompositionResult>(`/decomposition?${qs}`)
}

export const applyMigrations = () =>
  _send<any>("POST", "/_apply-migrations", {})
