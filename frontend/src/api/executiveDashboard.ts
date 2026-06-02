/**
 * api/executiveDashboard.ts — Executive Dashboard API.
 * Pack 1-5 (full coverage).
 */
import { api as apiClient } from "./client";

// ─── Pack 1 ───
export interface ExecCompanyInSector {
  company_id: string;
  name: string;
  pct: number;
  board_id?: string | null;
  task_total: number;
  task_done: number;
}

export interface ExecSectorRow {
  id: string;
  label: string;
  color: string;
  companies_total: number;
  companies_active: number;
  avg_pct: number;
  companies: ExecCompanyInSector[];
}

export interface ExecBottomMetrics {
  proj_count: number;
  task_count: number;
  done_proj: number;
  done_tasks: number;
  deferred_proj: number;
  deferred_tasks: number;
  avg_completion: number;
}

export interface ExecAvailableSector {
  id: string;
  label: string;
  color: string;
}

// ─── Pack 2 — Ratings ───
export interface ExecRingCard {
  label: string;
  rated_count: number;
  total: number;
  not_covered: number;
  accent: string;
  score: number | null;
  delta_2024: number;
}

export interface ExecRatingCell {
  rating: string | null;
  outlook: string | null;
  score: string | null;
  rated_at: string | null;
  report_url: string | null;
}

export interface ExecRatingRow {
  company_id: string;
  name: string;
  fitch: ExecRatingCell | null;
  sp: ExecRatingCell | null;
  moodys: ExecRatingCell | null;
  sf: ExecRatingCell | null;
  sp_esg: ExecRatingCell | null;
  cdp: ExecRatingCell | null;
}

export interface ExecRatingsBlock {
  ring_cards: ExecRingCard[];
  rows: ExecRatingRow[];
  rated_total_unique: number;
  overall_total: number;
}

// ─── Pack 2 — Execution chart ───
export interface ExecExecutionRow {
  company_id: string;
  name: string;
  pct: number;          // факт: % завершённых задач
  plan_pct?: number;    // план: % задач, чей дедлайн уже наступил
  sector: string;
}

// ═══ Pack 4 — Row 3 ═══

export interface ExecDirectionRow {
  id: string;
  label: string;
  color: string;
  projects_total: number;
  projects_done: number;
  tasks_total: number;
  tasks_done: number;
  progress_pct: number;
}

export interface ExecGovernanceCompany {
  company_id: string;
  name: string;
  sector: string;
  score: number;
  score_pct: number;
  board_size: number;
  independent_count: number;
  women_count: number;
  indep_pct: number;
  women_pct: number;
}

export interface ExecGovernanceBlock {
  total_companies: number;
  avg_score: number;
  top_score: number;
  avg_indep_pct: number;
  avg_women_pct: number;
  top_companies: ExecGovernanceCompany[];
}

export interface ExecStandardsRing {
  done: number;
  active: number;
  init: number;
  not_started: number;
  pct: number;
}

export interface ExecStandardsAttention {
  company_id: string;
  name: string;
  sector: string;
  ifrs_status: string;
  forensic_status: string;
  gaps: string[];
}

export interface ExecStandardsBlock {
  total_companies: number;
  ifrs: ExecStandardsRing;
  forensic: ExecStandardsRing;
  attention_list: ExecStandardsAttention[];
}

// ═══ Pack 5 — Row 2.55 / 2.6 / 2.7 ═══

// Block 1: Economic Effect
export interface ExecEEKpi {
  realized_sum: number;
  planned_sum: number;
  pipeline_sum: number;
  conversion_pct: number;
  done_count: number;
  active_count: number;
  total_count: number;
  has_data: boolean;
}

export interface ExecEEProject {
  project_id: string;
  title: string;
  company_name: string;
  sector: string;
  direction: string | null;
  status: string;
  planned_value: number;
  realized_value: number;
  pct_realized: number;
  unit: string;
}

export interface ExecEconomicEffectBlock {
  year: number;
  kpi: ExecEEKpi;
  top_projects: ExecEEProject[];
}

// Block 2: BP Tracker
export interface ExecBPCompanyRow {
  company_id: string;
  name: string;
  sector: string;
  plan_value: number;
  fact_value: number;
  pct: number | null;
  display_pct: number | null;
  display_label: string | null;
  display_label_full: string | null;
  delta: number | null;
  cls: string;
  note: string | null;
}

export interface ExecBPBlock {
  year: number;
  prev_year: number;
  metric: string;
  metric_label: string;
  standard: string;
  mode: string;
  head_sub: string;
  is_signed_metric: boolean;
  plan_total: number;
  fact_total: number;
  sum_plan_ll: number;
  sum_fact_plan_ll: number;
  sum_prev_ll: number;
  sum_fact_ll: number;
  overall_pct: number | null;
  prev_overall_pct: number | null;
  overall_delta: number | null;
  overall_label: string | null;
  rows: ExecBPCompanyRow[];
  on_target: number;
  attention: number;
  behind: number;
  total_count: number;
  with_pct_count: number;
  available_metrics: string[];
}

// Block 3: Tax Contribution
export interface ExecTaxKpi {
  income_tax: number;
  vat: number;
  total: number;
  yoy_total_pct: number | null;
  yoy_income_tax_pct: number | null;
  yoy_vat_pct: number | null;
  budget_share_pct: number | null;
  budget: number | null;
  vat_is_estimate?: boolean;    // Pack 7.9h: НДС = revenue × 12% оценка
}

export interface ExecTaxTopPayer {
  company_id: string;
  name: string;
  sector: string;
  amount: number;
  share_pct: number;
}

export interface ExecTaxBlock {
  year: number;
  prev_year: number;
  has_data: boolean;
  standard: string;
  cos_count: number;
  missing_companies?: string[]; // Pack 7.9h: компании без NSBU PL
  kpi: ExecTaxKpi;
  top_payers: ExecTaxTopPayer[];
}

// ─── Top-level payload ───
export interface ExecutiveDashboardData {
  year: number;
  total_companies: number;
  title_main: string;
  title_sub: string;
  row1_title: string;
  row1_subtitle: string;
  sectors: ExecSectorRow[];
  bottom_metrics: ExecBottomMetrics;

  // Pack 2
  ratings: ExecRatingsBlock | null;
  execution_chart: ExecExecutionRow[];
  avg_execution_pct: number;

  // Pack 4 — Row 3
  directions: ExecDirectionRow[];
  governance: ExecGovernanceBlock | null;
  standards: ExecStandardsBlock | null;

  // Pack 5 — Row 2.55 / 2.6 / 2.7
  economic_effect: ExecEconomicEffectBlock | null;
  bp_tracker: ExecBPBlock | null;
  tax_contribution: ExecTaxBlock | null;

  available_years: number[];
  available_sectors: ExecAvailableSector[];
}

const BASE = "/dashboard/executive";

export async function getExecutiveDashboard(
  year: number,
  sectors?: string[],
  bpMetric?: string,
): Promise<ExecutiveDashboardData> {
  const params: Record<string, any> = {};
  if (sectors && sectors.length) {
    params.sectors = sectors;
  }
  if (bpMetric) {
    params.bp_metric = bpMetric;
  }
  const { data } = await apiClient.get<ExecutiveDashboardData>(`${BASE}/${year}`, {
    params,
    paramsSerializer: { indexes: null },
  });
  return data;
}


// ═══ Pack 7.36 — Directions drill modal ═══

export interface ExecDirectionDrillProject {
  id: string;
  title: string;
  status: string;       // init/new/active/review/done
  due_date: string | null;
  progress_percent: number;
  is_overdue: boolean;
  assignee_name: string | null;
}

export interface ExecDirectionDrillTask {
  id: string;
  title: string;
  status: string;
  due_date: string | null;
  progress_percent: number;
  is_overdue: boolean;
  assignee_name: string | null;
  priority: string;     // low/medium/high
}

export interface ExecDirectionDrillCompany {
  company_id: string;
  company_name: string;
  sector: string;       // mining/oilgas/energy/transport/other
  projects_total: number;
  projects_done: number;
  tasks_total: number;
  tasks_done: number;
  tasks_overdue: number;
  projects: ExecDirectionDrillProject[];
  tasks: ExecDirectionDrillTask[];
}

export interface ExecDirectionDrillResponse {
  direction_id: string;       // code, e.g. "esg"
  direction_label: string;
  direction_color: string;
  progress_pct: number;
  companies_count: number;
  projects_total: number;
  projects_done: number;
  tasks_total: number;
  tasks_done: number;
  tasks_overdue: number;
  assignees_count: number;
  companies: ExecDirectionDrillCompany[];
}

/**
 * Fetch detailed breakdown for one direction (Pack 7.36 drill modal).
 *
 * @param year — optional portfolio year filter; null/undefined fetches all
 */
export async function fetchDirectionDrill(
  directionCode: string,
  year?: number,
): Promise<ExecDirectionDrillResponse> {
  const params: Record<string, any> = {};
  if (year != null) params.year = year;
  const { data } = await apiClient.get<ExecDirectionDrillResponse>(
    `${BASE}/directions/${directionCode}`,
    { params },
  );
  return data;
}
