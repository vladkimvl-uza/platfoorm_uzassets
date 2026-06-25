/**
 * ESG API client.
 *
 * Wraps /esg endpoints: overview, company detail, metrics CRUD, issues CRUD.
 *
 * The 3 pillars (E/S/G) shape the entire UI — most components display
 * tri-pillar splits (3-card strips, 3-column grids).
 */
import { api, type ModerationQueuedTag } from "./client";

export type Pillar = "E" | "S" | "G";
export type Severity = "low" | "med" | "high" | "critical";
export type IssueStatus = "open" | "in_progress" | "mitigated" | "closed";

export const PILLAR_META: { key: Pillar; label: string; color: string; full: string }[] = [
  { key: "E", label: "Окружающая среда", color: "#1D9E75", full: "Environmental" },
  { key: "S", label: "Социальная сфера", color: "#7F77DD", full: "Social" },
  { key: "G", label: "Корпуправление",   color: "#378ADD", full: "Governance" },
];

export const SEVERITY_META: { key: Severity; label: string; color: string }[] = [
  { key: "low",      label: "Низкая",       color: "#7DC4A0" },
  { key: "med",      label: "Средняя",      color: "#EF9F27" },
  { key: "high",     label: "Высокая",      color: "#E24B4A" },
  { key: "critical", label: "Критическая", color: "#991B1B" },
];

export const ISSUE_STATUS_META: { key: IssueStatus; label: string; color: string }[] = [
  { key: "open",        label: "Открыто",     color: "#E24B4A" },
  { key: "in_progress", label: "В работе",    color: "#EF9F27" },
  { key: "mitigated",   label: "Смягчено",    color: "#7DC4A0" },
  { key: "closed",      label: "Закрыто",     color: "#94A3B8" },
];

// ---------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------

export interface PillarStat {
  pillar: Pillar;
  metric_count: number;
  company_count: number;
  avg_target_attainment: number | null;
  avg_benchmark_diff: number | null;
  on_target_count: number;
  behind_count: number;
}

export interface IssueSeverityStat {
  severity: Severity;
  label: string;
  color: string;
  count: number;
}

export interface AgencyRatingCell {
  agency: string;
  rating_id: string | null;   // для inline-редактирования в таблице ESG
  rating: string | null;
  score: string | null;
  outlook: string | null;
  rating_date_text: string | null;
  report_url: string | null;
  is_recent: boolean;
}

export interface ESGCompanyScore {
  company_id: string;
  company_code: string;
  company_name: string | null;
  company_abbr: string | null;
  sector_code: string | null;
  sector_color: string | null;
  e_score: number | null;
  s_score: number | null;
  g_score: number | null;
  overall_score: number | null;
  metric_count: number;
  issues_open: number;
  issues_critical: number;
  last_year_reported: number | null;
  rank: number;
  ratings_by_agency: AgencyRatingCell[];
  composite_esg_score: number | null;     // 0..10 from agency ratings
  has_any_rating: boolean;
  recent_updates_count: number;
}

export interface ESGOverviewKpis {
  total_companies: number;
  companies_with_data: number;
  metrics_total: number;
  issues_open: number;
  issues_critical: number;
  avg_overall_score: number | null;
  covered_count: number;
  coverage_pct: number;
  leader_company_id: string | null;
  leader_company_name: string | null;
  leader_composite: number | null;
  leader_rating_letter: string | null;
  leader_ratings_count: number;
  unrated_count: number;
  recent_updates_count: number;
}

export interface AgencyCoverageStat {
  agency: string;
  count: number;
  color: string;
}

export interface RecentRatingUpdate {
  company_id: string;
  company_code: string;
  company_name: string;
  sector_code: string | null;
  sector_color: string | null;
  agency: string;
  agency_color: string;
  rating: string | null;
  score: string | null;
  rating_date_text: string | null;
  report_url: string | null;
}

export interface SectorBreakdownItem {
  code: string;
  label: string;
  color: string;
  total: number;
  covered: number;
  coverage_pct: number;
  leader_company_id: string | null;
  leader_company_name: string | null;
  leader_composite: number | null;
}

export interface ESGOverviewResponse {
  year: number | null;
  sector_code: string | null;
  kpis: ESGOverviewKpis;
  pillars: PillarStat[];
  issue_severity_split: IssueSeverityStat[];
  rankings: ESGCompanyScore[];
  agency_coverage: AgencyCoverageStat[];
  sector_breakdown: SectorBreakdownItem[];
  recent_updates: RecentRatingUpdate[];
  available_years: number[];
  sectors: { code: string; count: number }[];
  generated_at: string;
}

export interface ESGMetricBrief {
  id: string;
  company_id: string;
  year: number;
  pillar: Pillar;
  metric_code: string;
  metric_name: string;
  value: number | null;
  unit: string | null;
  target: number | null;
  benchmark: number | null;
  notes: string | null;
  target_attainment_pct: number | null;
  benchmark_diff_pct: number | null;
}

export interface ESGIssueBrief {
  id: string;
  company_id: string;
  company_code: string | null;
  company_name: string | null;
  pillar: Pillar;
  title: string;
  description: string | null;
  severity: Severity | null;
  status: IssueStatus;
  created_at: string;
}

export interface ESGCompanyDetail {
  company_id: string;
  company_code: string;
  company_name: string | null;
  sector_code: string | null;
  year: number;
  e_score: number | null;
  s_score: number | null;
  g_score: number | null;
  overall_score: number | null;
  metrics_e: ESGMetricBrief[];
  metrics_s: ESGMetricBrief[];
  metrics_g: ESGMetricBrief[];
  issues: ESGIssueBrief[];
  available_years: number[];
  tracked_years: number[];
}

export interface ESGMetricUpsertPayload {
  company_id: string;
  year: number;
  pillar: Pillar;
  metric_code: string;
  metric_name: string;
  value?: number | null;
  unit?: string | null;
  target?: number | null;
  benchmark?: number | null;
  notes?: string | null;
}

export interface ESGIssueCreatePayload {
  company_id: string;
  pillar: Pillar;
  title: string;
  description?: string | null;
  severity?: Severity;
}

export interface ESGIssueUpdatePayload {
  pillar?: Pillar;
  title?: string;
  description?: string | null;
  severity?: Severity;
  status?: IssueStatus;
}

// ---------------------------------------------------------------------
// ESG Maturity Cockpit — матрица зрелости + EMS
// ---------------------------------------------------------------------

export interface ESGMaturityCellBrief {
  dimension: string;
  sub_key: string;
  stage: number;
  status_text?: string | null;
  value_text?: string | null;
  evidence_url?: string | null;
  due_date?: string | null;
}
export interface ESGRatingMini {
  agency: string;
  rating: string | null;
  score: string | null;
  outlook: string | null;
  report_url: string | null;
}
export interface ESGMaturityCompany {
  company_id: string;
  company_code: string;
  company_name?: string | null;
  sector_code?: string | null;
  sector_name?: string | null;
  sector_color?: string | null;
  cells: ESGMaturityCellBrief[];
  dim_stage: Record<string, number>;   // D1..D6 → 0..4
  ems: number;                         // 0..100
  rating_count: number;
  ratings: ESGRatingMini[];            // сами ESG-рейтинги (агентство/значение/ссылка)
  not_needed?: boolean;                // «не нуждается» → исключена из метрик/статистики
}
export interface ESGMaturityHeatmap {
  year: number;
  companies: ESGMaturityCompany[];
  ems_mean: number;
  ems_median: number;
  ems_delta_yoy?: number | null;
  baskets: { mature: number; developing: number; starting: number };
  climate_funnel: number[];   // passed per stage 1..4
  risk_funnel: number[];      // passed per stage 1..3
  iso_full_count: number;
  rated_count: number;
  total_companies: number;
  available_years: number[];
  generated_at: string;
}
export interface ESGMaturityCellUpsertPayload {
  company_id: string;
  year: number;
  dimension: string;
  sub_key?: string;
  stage?: number | null;
  status_text?: string | null;
  value_text?: string | null;
  evidence_url?: string | null;
  due_date?: string | null;
  extra?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------
// ESG SWOT / выводы
// ---------------------------------------------------------------------
export interface ESGSwotItemBrief {
  id?: string | null;
  kind: "strength" | "weakness";
  scope: "portfolio" | "company";
  company_id?: string | null;
  company_code?: string | null;
  company_name?: string | null;
  title?: string | null;
  body: string;
  severity?: string | null;
  order_idx: number;
}
export interface ESGSwotResponse {
  portfolio_strengths: ESGSwotItemBrief[];
  portfolio_weaknesses: ESGSwotItemBrief[];
  company_items: ESGSwotItemBrief[];
  generated_at: string;
}
export interface ESGSwotUpsertPayload {
  id?: string | null;
  kind: "strength" | "weakness";
  scope: "portfolio" | "company";
  company_id?: string | null;
  title?: string | null;
  body: string;
  severity?: string | null;
  order_idx?: number;
}

// ---------------------------------------------------------------------
// ESG-отчёты по годам (годовая таблица в профиле зрелости)
// ---------------------------------------------------------------------
export interface ESGReportBrief {
  id?: string | null;
  company_id: string;
  year: number;
  status: string | null;
  report_url: string | null;
  note: string | null;
  changed_by_name: string | null;
  updated_at: string | null;
}
export interface ESGReportListResponse {
  company_id: string;
  company_code: string | null;
  company_name: string | null;
  items: ESGReportBrief[];
  last_changed_by_name: string | null;
  last_changed_at: string | null;
  last_changed_year: number | null;
  generated_at: string;
}
export interface ESGReportUpsertPayload {
  company_id: string;
  year: number;
  status?: string | null;
  report_url?: string | null;
  note?: string | null;
}

// ---------------------------------------------------------------------
// ESG-релевантные KPI по компаниям (подтягиваются из модуля KPI по контексту)
// ---------------------------------------------------------------------
export interface ESGKpiBrief {
  name: string;
  unit: string | null;
  manager: string | null;
  plan: number | null;
  fact: number | null;
  pct: number | null;
  direction: string;
}
export interface ESGKpiCompany {
  company_id: string;
  company_code: string | null;
  kpis: ESGKpiBrief[];
}
export interface ESGKpiResponse {
  year: number;
  items: ESGKpiCompany[];
  generated_at: string;
}
export interface ESGKpiCreatePayload {
  company_id: string;
  year: number;
  name: string;
  unit?: string | null;
  direction?: "up" | "down";
  plan?: number | null;
  fact?: number | null;
}

// ---------------------------------------------------------------------
// API
// ---------------------------------------------------------------------

export const esgApi = {
  async getOverview(params: { year?: number; sector_code?: string; rankings_limit?: number } = {}) {
    const r = await api.get<ESGOverviewResponse>("/esg/overview", { params });
    return r.data;
  },

  async getCompanyDetail(companyId: string, year?: number) {
    const r = await api.get<ESGCompanyDetail>(
      `/esg/companies/${companyId}`,
      { params: year ? { year } : {} },
    );
    return r.data;
  },

  async getMaturityHeatmap(year?: number): Promise<ESGMaturityHeatmap> {
    const r = await api.get<ESGMaturityHeatmap>("/esg/maturity/heatmap", { params: year ? { year } : {} });
    return r.data;
  },

  async upsertMaturityCell(payload: ESGMaturityCellUpsertPayload): Promise<ESGMaturityCellBrief | ModerationQueuedTag> {
    const r = await api.put<ESGMaturityCellBrief | ModerationQueuedTag>("/esg/maturity/cell", payload);
    return r.data;
  },

  async getSwot(): Promise<ESGSwotResponse> {
    const r = await api.get<ESGSwotResponse>("/esg/swot");
    return r.data;
  },

  async upsertSwot(payload: ESGSwotUpsertPayload): Promise<ESGSwotItemBrief | ModerationQueuedTag> {
    const r = await api.put<ESGSwotItemBrief | ModerationQueuedTag>("/esg/swot", payload);
    return r.data;
  },

  async getCompanyReports(companyId: string): Promise<ESGReportListResponse> {
    const r = await api.get<ESGReportListResponse>(`/esg/companies/${companyId}/reports`);
    return r.data;
  },

  async upsertReport(payload: ESGReportUpsertPayload): Promise<ESGReportBrief | ModerationQueuedTag> {
    const r = await api.put<ESGReportBrief | ModerationQueuedTag>("/esg/report", payload);
    return r.data;
  },

  async getEsgKpis(year?: number): Promise<ESGKpiResponse> {
    const r = await api.get<ESGKpiResponse>("/esg/kpis", { params: year ? { year } : {} });
    return r.data;
  },

  async addEsgKpi(payload: ESGKpiCreatePayload): Promise<ESGKpiBrief> {
    const r = await api.post<ESGKpiBrief>("/esg/kpi", payload);
    return r.data;
  },

  async upsertMetric(payload: ESGMetricUpsertPayload): Promise<ESGMetricBrief | ModerationQueuedTag> {
    const r = await api.put<ESGMetricBrief | ModerationQueuedTag>("/esg/metric", payload);
    return r.data;
  },

  async deleteMetric(metricId: string) {
    await api.delete(`/esg/metric/${metricId}`);
  },

  async listIssues(params: {
    company_id?: string;
    pillar?: Pillar;
    severity?: Severity;
    status?: IssueStatus;
    limit?: number;
  } = {}) {
    const r = await api.get<ESGIssueBrief[]>("/esg/issues", { params });
    return r.data;
  },

  async createIssue(payload: ESGIssueCreatePayload): Promise<ESGIssueBrief | ModerationQueuedTag> {
    const r = await api.post<ESGIssueBrief | ModerationQueuedTag>("/esg/issue", payload);
    return r.data;
  },

  async updateIssue(issueId: string, payload: ESGIssueUpdatePayload): Promise<ESGIssueBrief | ModerationQueuedTag> {
    const r = await api.patch<ESGIssueBrief | ModerationQueuedTag>(`/esg/issue/${issueId}`, payload);
    return r.data;
  },

  async deleteIssue(issueId: string) {
    await api.delete(`/esg/issue/${issueId}`);
  },
};

// ---------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------

export function pillarMeta(p: Pillar | string): { label: string; color: string } {
  const m = PILLAR_META.find((x) => x.key === p);
  return m ? { label: m.label, color: m.color } : { label: String(p), color: "#94A3B8" };
}

export function severityMeta(s: Severity | string | null | undefined): { label: string; color: string } {
  if (!s) return { label: "—", color: "#94A3B8" };
  const m = SEVERITY_META.find((x) => x.key === s);
  return m ? { label: m.label, color: m.color } : { label: String(s), color: "#94A3B8" };
}

export function issueStatusMeta(s: IssueStatus | string | null | undefined): { label: string; color: string } {
  if (!s) return { label: "—", color: "#94A3B8" };
  const m = ISSUE_STATUS_META.find((x) => x.key === s);
  return m ? { label: m.label, color: m.color } : { label: String(s), color: "#94A3B8" };
}

/** Score 0-100 → color: green ≥75, mint ≥50, amber ≥25, red <25. */
export function scoreColor(s: number | null | undefined): string {
  if (s == null) return "#94A3B8";
  if (s >= 75) return "#1D9E75";
  if (s >= 50) return "#7DC4A0";
  if (s >= 25) return "#EF9F27";
  return "#E24B4A";
}

/** Format ESG metric value with unit. */
export function fmtMetricValue(v: number | null | undefined, unit: string | null | undefined): string {
  if (v == null) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  const numStr = n.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  return unit ? `${numStr} ${unit}` : numStr;
}
