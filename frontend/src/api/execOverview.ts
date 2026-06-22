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
  // «Ход проекта» — последний нарративный апдейт (status_update)
  last_update: string | null;
  last_update_at: string | null;
  last_update_health: string | null;
  last_update_author: string | null;
}

export interface ExecOverviewDirection {
  id: string;
  code: string;
  name: string;
}

export interface ExecOverviewTask {
  id: string;
  title: string;
  status: string;
  assignee_name: string | null;
  progress_percent: number;
  due_date: string | null;
  deadline_state: DeadlineState;
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
  // Ключевые результаты бизнес-плана за Q1 (план/факт, абс. UZS)
  q1_revenue_plan: number | null;
  q1_revenue_fact: number | null;
  q1_profit_plan: number | null;
  q1_profit_fact: number | null;
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
  projectTasks(projectId: string): Promise<ExecOverviewTask[]> {
    return api.get<ExecOverviewTask[]>(`/exec-overview/projects/${projectId}/tasks`).then(r => r.data);
  },
};
