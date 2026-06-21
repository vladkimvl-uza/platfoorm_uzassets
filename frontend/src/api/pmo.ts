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
};
