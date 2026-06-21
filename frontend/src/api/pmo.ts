// PMO API — P1: расписание (Гантт) + зависимости задач.
import { api } from './client';

export type ScheduleBarKind = 'project' | 'task';
export type DepType = 'FS' | 'SS' | 'FF' | 'SF';

export interface ScheduleBar {
  id: string;
  kind: ScheduleBarKind;
  project_id: string | null;
  title: string;
  status: string;
  progress_percent: number;
  start: string | null;          // YYYY-MM-DD
  due: string | null;
  baseline_start: string | null;
  baseline_due: string | null;
  is_milestone: boolean;
  assignee_name: string | null;
  direction: string | null;
  slip_days: number;
  on_critical_path: boolean;
  predecessor_ids: string[];
  blocked: boolean;
}

export interface ScheduleResponse {
  company_code: string;
  year: number | null;
  as_of: string;
  bars: ScheduleBar[];
  portfolio_slip_days: number;
  forecast_finish: string | null;
  baseline_finish: string | null;
  critical_path_ids: string[];
  overdue_count: number;
  blocked_count: number;
}

export interface DependencyRead {
  id: string;
  predecessor_id: string;
  successor_id: string;
  dep_type: string;
  lag_days: number;
}

// ── P2: RAID / Health / Status reports ─────────────────────────────────
export type RaidKind = "risk" | "assumption" | "issue" | "dependency";
export type RaidSeverity = "low" | "medium" | "high" | "critical";
export type RaidStatus = "open" | "mitigating" | "closed";

export interface RaidItem {
  id: string;
  company_id: string | null;
  project_id: string | null;
  kind: RaidKind;
  title: string;
  description: string | null;
  owner_id: string | null;
  owner_name: string | null;
  severity: RaidSeverity;
  probability: number;
  impact: number;
  score: number;
  status: RaidStatus;
  mitigation: string | null;
  due_date: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RaidPayload {
  kind?: RaidKind;
  title: string;
  description?: string | null;
  project_id?: string | null;
  owner_name?: string | null;
  severity?: RaidSeverity;
  probability?: number;
  impact?: number;
  status?: RaidStatus;
  mitigation?: string | null;
  due_date?: string | null;
}

export interface HealthProject {
  project_id: string | null;
  title: string;
  rag: "green" | "amber" | "red";
  progress_percent: number;
  slip_days: number;
  overdue_count: number;
  blocked_count: number;
  open_risks: number;
  high_risks: number;
  reasons: string[];
}

export interface HealthResponse {
  company_code: string;
  as_of: string;
  portfolio_rag: "green" | "amber" | "red";
  projects: HealthProject[];
  green: number;
  amber: number;
  red: number;
  open_risks: number;
  high_risks: number;
}

export interface StatusReport {
  id: string;
  company_id: string | null;
  project_id: string | null;
  period: string | null;
  rag: "green" | "amber" | "red";
  summary: string | null;
  metrics: any | null;
  created_at: string;
}

export const pmoApi = {
  getSchedule(code: string, year?: number | null): Promise<ScheduleResponse> {
    const q = year != null ? `?year=${year}` : '';
    return api.get(`/pmo/companies/${encodeURIComponent(code)}/schedule${q}`).then(r => r.data);
  },
  listDependencies(code: string): Promise<DependencyRead[]> {
    return api.get(`/pmo/companies/${encodeURIComponent(code)}/dependencies`).then(r => r.data);
  },
  createDependency(body: {
    predecessor_id: string;
    successor_id: string;
    dep_type?: DepType;
    lag_days?: number;
  }): Promise<DependencyRead> {
    return api.post('/pmo/dependencies', body).then(r => r.data);
  },
  deleteDependency(id: string): Promise<void> {
    return api.delete(`/pmo/dependencies/${id}`).then(() => undefined);
  },

  // ── RAID ──
  listRaid(code: string, opts?: { kind?: string; status?: string }): Promise<RaidItem[]> {
    const p = new URLSearchParams();
    if (opts?.kind) p.set("kind", opts.kind);
    if (opts?.status) p.set("status_filter", opts.status);
    const q = p.toString() ? `?${p.toString()}` : "";
    return api.get(`/pmo/companies/${encodeURIComponent(code)}/raid${q}`).then(r => r.data);
  },
  createRaid(code: string, body: RaidPayload): Promise<RaidItem> {
    return api.post(`/pmo/companies/${encodeURIComponent(code)}/raid`, body).then(r => r.data);
  },
  updateRaid(id: string, body: Partial<RaidPayload>): Promise<RaidItem> {
    return api.patch(`/pmo/raid/${id}`, body).then(r => r.data);
  },
  deleteRaid(id: string): Promise<void> {
    return api.delete(`/pmo/raid/${id}`).then(() => undefined);
  },

  // ── Health / Status reports ──
  getHealth(code: string): Promise<HealthResponse> {
    return api.get(`/pmo/companies/${encodeURIComponent(code)}/health`).then(r => r.data);
  },
  listStatusReports(code: string): Promise<StatusReport[]> {
    return api.get(`/pmo/companies/${encodeURIComponent(code)}/status-reports`).then(r => r.data);
  },
  createStatusReport(code: string, body: { project_id?: string | null; use_ai?: boolean }): Promise<StatusReport> {
    return api.post(`/pmo/companies/${encodeURIComponent(code)}/status-reports`, body).then(r => r.data);
  },
};
