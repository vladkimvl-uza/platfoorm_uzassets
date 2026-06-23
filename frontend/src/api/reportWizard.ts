/**
 * Report wizard config API — сохранённый «Мастер отчёта» по компании+году.
 */
import { api } from "./client";

export interface ReportWizardResponse {
  config: Record<string, unknown>;
  updated_at?: string | null;
  updated_by_name?: string | null;
}

export const reportWizardApi = {
  async get(code: string, year: number): Promise<ReportWizardResponse> {
    const r = await api.get<ReportWizardResponse>(`/report-wizard/${encodeURIComponent(code)}/${year}`);
    return r.data;
  },
  async save(code: string, year: number, config: Record<string, unknown>): Promise<ReportWizardResponse> {
    const r = await api.put<ReportWizardResponse>(`/report-wizard/${encodeURIComponent(code)}/${year}`, { config });
    return r.data;
  },
};
