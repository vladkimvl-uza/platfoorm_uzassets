/**
 * IFRS report history API — даты публикации МСФО-отчётности по компаниям (с 2022).
 */
import { api } from "./client";

export interface IfrsHistoryRow {
  company_id: string;
  year: number;
  published_on: string | null;   // 'YYYY-MM-DD'
  updated_by_name: string | null;
  updated_at: string | null;
}

export interface IfrsHistoryLastChange {
  by_name: string | null;
  at: string | null;
}

export interface IfrsHistoryResponse {
  rows: IfrsHistoryRow[];
  last_change: IfrsHistoryLastChange;
}

export const ifrsReportHistoryApi = {
  async list(): Promise<IfrsHistoryResponse> {
    const r = await api.get<IfrsHistoryResponse>("/ifrs-report-history");
    return r.data;
  },
  async upsert(companyId: string, year: number, publishedOn: string | null): Promise<IfrsHistoryRow> {
    const r = await api.put<IfrsHistoryRow>(`/ifrs-report-history/${companyId}/${year}`, {
      published_on: publishedOn,
    });
    return r.data;
  },
};
