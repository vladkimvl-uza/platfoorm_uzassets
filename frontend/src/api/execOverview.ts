/**
 * Executive Overview API — министерский обзор сектор→компания→проекты+дедлайны.
 * Backend: /backend/app/api/routes/exec_overview.py
 */
import { api } from "./client";

export type DeadlineState = "overdue" | "month" | "quarter" | "later" | "none";

export interface ExecOverviewProject {
  id: string;
  title: string;
  description: string | null;
  direction: string | null;
  direction_id: string | null;
  status: string;
  progress_percent: number;
  due_date: string | null;
  deadline_state: DeadlineState;
}

export interface ExecOverviewDirection {
  id: string;
  code: string;
  name: string;
}

export interface ExecOverviewCompany {
  id: string;
  code: string;
  name: string;
  total: number;
  overdue: number;
  revenue: number | null;
  profit: number | null;
  fin_year: number | null;
  projects: ExecOverviewProject[];
}

export interface ExecOverviewSector {
  id: string | null;
  code: string | null;
  name: string;
  color: string | null;
  short_badge: string | null;
  total: number;
  overdue: number;
  company_count: number;
  companies: ExecOverviewCompany[];
}

export interface ExecOverviewResponse {
  year: number | null;
  as_of: string;
  total: number;
  overdue: number;
  due_this_month: number;
  sector_count: number;
  company_count: number;
  sectors: ExecOverviewSector[];
  directions: ExecOverviewDirection[];
}

export const execOverviewApi = {
  get(year?: number | null): Promise<ExecOverviewResponse> {
    const q = year != null ? `?year=${year}` : "";
    return api.get<ExecOverviewResponse>(`/exec-overview${q}`).then(r => r.data);
  },
};
