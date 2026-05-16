import { api } from "./client";
import type { TaskBrief, QuartersObject, EconomicEffect } from "./tasks";

export interface ProjectBrief {
  id: string;
  num: string | null;
  title: string;
  status: "init" | "new" | "active" | "review" | "done" | "quarterly" | "monthly" | "ongoing";
  priority: "high" | "medium" | "low";
  board_id: string | null;
  board_name: string | null;
  company_id: string | null;
  company_code: string | null;
  company_name: string | null;
  assignee_email: string | null;
  assignee_name: string | null;
  assignee_id: string | null;
  due_date: string | null;
  portfolio_year: number | null;
  progress_percent: number;
  is_overdue: boolean;
  tags: string[] | null;
  tasks_total: number;
  tasks_done: number;
  quarters?: QuartersObject | null;
  consultant?: string | string[] | null;
  direction?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends ProjectBrief {
  description: string | null;
  scope: string | null;
  consultants: string[];
  extra: Record<string, unknown> | null;
  legacy_id: string | null;
  creator_id: string | null;
  start_date: string | null;
  completed_at: string | null;
  consultant_comment?: string | null;
  economic_effect?: EconomicEffect | null;
}

export interface ProjectListResponse {
  items: ProjectBrief[];
  total: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  available_years: number[];
}

export interface ProjectCreate {
  title: string;
  description?: string;
  num?: string;
  status?: "init" | "new" | "active" | "review" | "done" | "quarterly" | "monthly" | "ongoing";
  priority?: "high" | "medium" | "low";
  board_id?: string;
  company_id?: string;
  direction_id?: string;
  assignee_email?: string;
  assignee_name?: string;
  start_date?: string;
  due_date?: string;
  portfolio_year?: number;
  tags?: string[];
  consultant?: string | string[];
  consultant_comment?: string;
  economic_effect?: EconomicEffect;
  quarters?: QuartersObject;
  direction?: string;
  scope?: string;
}

export interface ProjectUpdate {
  title?: string;
  description?: string;
  num?: string;
  status?: "init" | "new" | "active" | "review" | "done" | "quarterly" | "monthly" | "ongoing";
  priority?: "high" | "medium" | "low";
  board_id?: string;
  company_id?: string;
  direction_id?: string;
  assignee_email?: string;
  assignee_name?: string;
  start_date?: string;
  due_date?: string;
  portfolio_year?: number;
  progress_percent?: number;
  tags?: string[];
  consultant?: string | string[] | null;
  consultant_comment?: string | null;
  economic_effect?: EconomicEffect | null;
  quarters?: QuartersObject | null;
  direction?: string | null;
  scope?: string | null;
}

export interface ProjectListQuery {
  portfolio_year?: number;
  company_id?: string;
  company_code?: string;
  board_id?: string;
  status?: string;
  priority?: string;
  assignee_email?: string;
  only_overdue?: boolean;
  has_economic_effect?: boolean;
  search?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export const projectsApi = {
  async list(query: ProjectListQuery = {}) {
    const { data } = await api.get<ProjectListResponse>("/projects", { params: query });
    return data;
  },
  async getOne(id: string) {
    const { data } = await api.get<ProjectDetail>(`/projects/${id}`);
    return data;
  },
  async getTasks(id: string) {
    const { data } = await api.get<TaskBrief[]>(`/projects/${id}/tasks`);
    return data;
  },
  async create(payload: ProjectCreate) {
    const { data } = await api.post<ProjectDetail>("/projects", payload);
    return data;
  },
  async update(id: string, payload: ProjectUpdate) {
    const { data } = await api.patch<ProjectDetail>(`/projects/${id}`, payload);
    return data;
  },
  async archive(id: string) {
    await api.delete(`/projects/${id}`);
  },
};
