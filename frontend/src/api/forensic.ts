/**
 * Forensic & Procurement audit API — свод план/факт закупок + статус форензик-аудита.
 * Здесь нужен только overview (для честного счётчика «forensic проведён» в финансах).
 */
import { api } from "./client";

export interface ForensicCompanyRow {
  k: string;              // код компании
  n: string;              // имя
  forensic?: string;      // статус форензика ('Завершён' | 'В процессе' | ...)
  auditor?: string;
  aYears?: string;
}

export interface ForensicOverviewKpis {
  total_companies: number;
  plan_approved: number;
  forensic_done: number;
  with_auditor: number;
}

export interface ForensicOverviewResponse {
  companies: ForensicCompanyRow[];
  kpis: ForensicOverviewKpis;
}

export const forensicApi = {
  async overview(): Promise<ForensicOverviewResponse> {
    const r = await api.get<ForensicOverviewResponse>("/forensic/overview");
    return r.data;
  },
};
