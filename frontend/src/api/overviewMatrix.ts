/**
 * Overview matrix config API — ручная настройка квартальной матрицы «Сводного обзора»
 * по компании+году (выбор проектов, переопределения, свои пункты).
 */
import { api } from "./client";

export interface MatrixOverride {
  title?: string | null;
  due_date?: string | null;   // 'YYYY-MM-DD' или null
  quarter?: number | null;    // 0..3 или null = по дате
  hidden?: boolean | null;
}

export interface MatrixCustomItem {
  id: string;
  direction_id?: string | null;
  direction_name?: string | null;
  title: string;
  due_date?: string | null;
  quarter?: number | null;
}

export interface MatrixConfig {
  hidden: string[];
  overrides: Record<string, MatrixOverride>;
  custom: MatrixCustomItem[];
}

export interface MatrixConfigResponse {
  company_id: string;
  year: number;
  config: MatrixConfig;
  updated_at?: string | null;
  updated_by_name?: string | null;
}

export function emptyMatrixConfig(): MatrixConfig {
  return { hidden: [], overrides: {}, custom: [] };
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
