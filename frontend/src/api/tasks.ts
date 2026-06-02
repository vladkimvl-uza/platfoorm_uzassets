import { api, type ModerationQueuedTag } from "./client";

// =====================================================================
// Types matching backend schemas
// =====================================================================

export interface BoardBrief {
  id: string;
  name: string;
  description: string | null;
  color_hex: string | null;
  sector_code: string | null;
  company_id: string | null;
  company_code: string | null;
  company_name: string | null;
  is_archived: boolean;
  sort_order: number;
  tasks_total: number;
  tasks_by_status: Record<string, number>;
}

export interface BoardListResponse {
  items: BoardBrief[];
  total: number;
}

export interface QuartersObject {
  q1?: { weight?: number; plan?: number; fact?: number | null } | boolean;
  q2?: { weight?: number; plan?: number; fact?: number | null } | boolean;
  q3?: { weight?: number; plan?: number; fact?: number | null } | boolean;
  q4?: { weight?: number; plan?: number; fact?: number | null } | boolean;
}

export interface EconomicEffect {
  value?: number;
  currency?: string;
  note?: string;
  updatedBy?: string;
}

export interface TaskBrief {
  id: string;
  num: string | null;
  title: string;
  status: "init" | "new" | "active" | "review" | "done" | "quarterly" | "monthly" | "ongoing";
  priority: "high" | "medium" | "low";
  board_id: string | null;
  board_name: string | null;
  company_id: string | null;
  company_code: string | null;
  assignee_email: string | null;
  assignee_name: string | null;
  assignee_id: string | null;
  due_date: string | null;
  portfolio_year: number | null;
  project_id?: string | null;
  // Year-transfer (Phase 13) — 2026-05-26: surfaced in TaskBrief
  linked_year?: number | null;
  linked_task_id?: string | null;
  is_project: boolean;
  progress_percent: number;
  sort_order?: number;
  is_overdue: boolean;
  tags: string[] | null;
  quarters?: QuartersObject | null;
  consultant?: string | string[] | null;
  direction?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskDetail extends TaskBrief {
  description: string | null;
  scope: string | null;
  linked_task_id: string | null;
  consultants: string[];
  extra: Record<string, unknown> | null;
  legacy_id: string | null;
  creator_id: string | null;
  start_date: string | null;
  completed_at: string | null;
  consultant_comment?: string | null;
  economic_effect?: EconomicEffect | null;
}

export interface TaskListResponse {
  items: TaskBrief[];
  total: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
}

export interface KanbanColumn {
  status: string;
  label: string;
  color: string;
  tasks: TaskBrief[];
  count: number;
}

export interface BoardKanban {
  board: BoardBrief;
  columns: KanbanColumn[];
}

export interface TaskCreate {
  title: string;
  description?: string;
  num?: string;
  status?: "init" | "new" | "active" | "review" | "done" | "quarterly" | "monthly" | "ongoing";
  priority?: "high" | "medium" | "low";
  board_id?: string;
  company_id?: string;
  project_id?: string;
  direction_id?: string;
  assignee_email?: string;
  assignee_name?: string;
  start_date?: string;
  due_date?: string;
  portfolio_year?: number;
  is_project?: boolean;
  tags?: string[];
  consultant?: string | string[];
  consultant_comment?: string;
  economic_effect?: EconomicEffect;
  quarters?: QuartersObject;
  direction?: string;
  scope?: string;
}

export interface TaskUpdate {
  title?: string;
  description?: string;
  num?: string;
  status?: "init" | "new" | "active" | "review" | "done" | "quarterly" | "monthly" | "ongoing";
  priority?: "high" | "medium" | "low";
  board_id?: string;
  company_id?: string;
  project_id?: string;
  direction_id?: string;
  assignee_email?: string;
  assignee_name?: string;
  start_date?: string;
  due_date?: string;
  portfolio_year?: number;
  progress_percent?: number;
  sort_order?: number;
  tags?: string[];
  // Year-transfer (Phase 13)
  linked_year?: number | null;
  linked_task_id?: string | null;
  consultant?: string | string[] | null;
  consultant_comment?: string | null;
  economic_effect?: EconomicEffect | null;
  quarters?: QuartersObject | null;
  direction?: string | null;
  scope?: string | null;
}

export interface TaskListQuery {
  board_id?: string;
  company_id?: string;
  company_code?: string;
  status?: string;
  priority?: string;
  assignee_email?: string;
  portfolio_year?: number;
  is_project?: boolean;
  only_overdue?: boolean;
  search?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

// =====================================================================
// API methods
// =====================================================================

export const boardsApi = {
  async list(params: { sector?: string; company_id?: string; archived?: boolean; search?: string } = {}) {
    const { data } = await api.get<BoardListResponse>("/boards", { params });
    return data;
  },
  async getOne(id: string) {
    const { data } = await api.get<BoardBrief>(`/boards/${id}`);
    return data;
  },
  async getKanban(id: string, portfolio_year?: number) {
    const { data } = await api.get<BoardKanban>(`/boards/${id}/kanban`, {
      params: portfolio_year ? { portfolio_year } : {},
    });
    return data;
  },
};

export const tasksApi = {
  async list(query: TaskListQuery = {}) {
    const { data } = await api.get<TaskListResponse>("/tasks", { params: query });
    return data;
  },
  async getOne(id: string) {
    const { data } = await api.get<TaskDetail>(`/tasks/${id}`);
    return data;
  },
  async create(payload: TaskCreate): Promise<TaskDetail | ModerationQueuedTag> {
    const { data } = await api.post<TaskDetail | ModerationQueuedTag>("/tasks", payload);
    return data;
  },
  async update(id: string, payload: TaskUpdate): Promise<TaskDetail | ModerationQueuedTag> {
    const { data } = await api.patch<TaskDetail | ModerationQueuedTag>(`/tasks/${id}`, payload);
    return data;
  },
  async archive(id: string) {
    await api.delete(`/tasks/${id}`);
  },
  /** Toggle the binary "результат" flag. Returns the new state. */
  async toggleResult(id: string): Promise<{ result_at: string | null }> {
    const { data } = await api.post<{ result_at: string | null }>(`/tasks/${id}/result`);
    return data;
  },
};

export const projectsResultApi = {
  /** Toggle the binary "результат" flag on a project. */
  async toggle(id: string): Promise<{ result_at: string | null }> {
    const { data } = await api.post<{ result_at: string | null }>(`/projects/${id}/result`);
    return data;
  },
};
