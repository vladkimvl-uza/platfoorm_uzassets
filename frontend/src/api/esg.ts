/**
 * ESG API client.
 *
 * Wraps /esg endpoints: overview, company detail, metrics CRUD, issues CRUD.
 *
 * The 3 pillars (E/S/G) shape the entire UI — most components display
 * tri-pillar splits (3-card strips, 3-column grids).
 */
import { api } from "./client";

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

export interface ESGCompanyScore {
  company_id: string;
  company_code: string;
  company_name: string | null;
  sector_code: string | null;
  e_score: number | null;
  s_score: number | null;
  g_score: number | null;
  overall_score: number | null;
  metric_count: number;
  issues_open: number;
  issues_critical: number;
  last_year_reported: number | null;
  rank: number;
}

export interface ESGOverviewKpis {
  total_companies: number;
  companies_with_data: number;
  metrics_total: number;
  issues_open: number;
  issues_critical: number;
  avg_overall_score: number | null;
}

export interface ESGOverviewResponse {
  year: number | null;
  sector_code: string | null;
  kpis: ESGOverviewKpis;
  pillars: PillarStat[];
  issue_severity_split: IssueSeverityStat[];
  rankings: ESGCompanyScore[];
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

  async upsertMetric(payload: ESGMetricUpsertPayload) {
    const r = await api.put<ESGMetricBrief>("/esg/metric", payload);
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

  async createIssue(payload: ESGIssueCreatePayload) {
    const r = await api.post<ESGIssueBrief>("/esg/issue", payload);
    return r.data;
  },

  async updateIssue(issueId: string, payload: ESGIssueUpdatePayload) {
    const r = await api.patch<ESGIssueBrief>(`/esg/issue/${issueId}`, payload);
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
