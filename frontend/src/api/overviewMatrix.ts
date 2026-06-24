/**
 * Overview matrix config API — ручная настройка квартальной матрицы «Сводного обзора»
 * по компании+году (выбор проектов, переопределения, свои пункты).
 */
import { api } from "./client";

export interface MatrixOverride {
  title?: string | null;
  due_date?: string | null;   // 'YYYY-MM-DD' или null
  quarter?: number | null;    // старт-квартал (0..3) или null = по дате
  quarter_end?: number | null; // конец-квартал (Гант-растяжка) или null = один квартал
  hidden?: boolean | null;
}

export interface MatrixCustomItem {
  id: string;
  direction_id?: string | null;
  direction_name?: string | null;
  title: string;
  due_date?: string | null;
  quarter?: number | null;
  quarter_end?: number | null;
}

export interface ManualProject {
  id: string;
  title: string;
  ref_project_id?: string | null;   // связанный системный проект (автоподстановка)
  quarter?: number | null;          // старт-квартал (0..3)
  quarter_end?: number | null;      // конец-квартал (Гант-растяжка)
  due_date?: string | null;
  details?: string | null;          // текст выноски (внизу отчёта)
}

export interface ManualDirection {
  id: string;
  name: string;
  projects: ManualProject[];
}

export interface MatrixConfig {
  hidden: string[];
  overrides: Record<string, MatrixOverride>;
  custom: MatrixCustomItem[];
  // Ручной отчёт: направления/проекты вписываются вручную, детали — в выноску.
  manual_directions: ManualDirection[];
}

export interface MatrixConfigResponse {
  company_id: string;
  year: number;
  config: MatrixConfig;
  updated_at?: string | null;
  updated_by_name?: string | null;
}

export function emptyMatrixConfig(): MatrixConfig {
  return { hidden: [], overrides: {}, custom: [], manual_directions: [] };
}

export const overviewMatrixApi = {
  async get(companyId: string, year: number): Promise<MatrixConfigResponse> {
    const r = await api.get<MatrixConfigResponse>(`/overview-matrix/${companyId}/${year}`);
    return r.data;
  },
  async save(companyId: string, year: number, config: MatrixConfig): Promise<MatrixConfigResponse> {
    const r = await api.put<MatrixConfigResponse>(`/overview-matrix/${companyId}/${year}`, config);
    return r.data;
  },
};
