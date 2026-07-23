import { api } from "@/api/client";

export type ValueSource = "unit_cost" | "procurement" | "business_plan" | "kpi" | "manual";
export type ValueKind = "economy" | "uplift" | "risk";
export type ValueStatus = "identified" | "in_progress" | "realized" | "dismissed";

export interface ValueOpportunity {
  id: string;
  company_id: string | null;
  company_name: string | null;
  sector_color: string | null;
  year: number | null;
  source: ValueSource;
  kind: ValueKind;
  status: ValueStatus;
  title: string;
  description: string | null;
  value_amount: string | number | null;
  realized_amount: string | number | null;
  owner: string | null;
  target_date: string | null;
  realized_at: string | null;
  fingerprint: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValueByStatus { status: string; count: number; amount: number; realized: number; }
export interface ValueByCompany {
  company_id: string | null; company_name: string; sector_color: string | null;
  count: number; amount: number; realized: number;
}
export interface ValueSummary {
  total_count: number;
  identified_amount: number;
  in_progress_amount: number;
  realized_amount: number;
  by_status: ValueByStatus[];
  by_source: ValueByStatus[];
  by_company: ValueByCompany[];
}

export interface ValueOpportunityInput {
  company_id?: string | null;
  year?: number | null;
  source?: ValueSource;
  kind?: ValueKind;
  status?: ValueStatus;
  title: string;
  description?: string | null;
  value_amount?: number | null;
  realized_amount?: number | null;
  owner?: string | null;
  target_date?: string | null;
}

export const valueApi = {
  list: (params?: { status?: string; source?: string; company_id?: string }) =>
    api.get<ValueOpportunity[]>("/value", { params }).then((r) => r.data),
  summary: () => api.get<ValueSummary>("/value/summary").then((r) => r.data),
  create: (body: ValueOpportunityInput) =>
    api.post<ValueOpportunity>("/value", body).then((r) => r.data),
  update: (id: string, body: Partial<ValueOpportunityInput>) =>
    api.patch<ValueOpportunity>(`/value/${id}`, body).then((r) => r.data),
  remove: (id: string) => api.delete(`/value/${id}`).then((r) => r.data),
};

export const VALUE_SOURCE_LABEL: Record<ValueSource, string> = {
  unit_cost: "Удел. себестоимость", procurement: "Закупки", business_plan: "Бизнес-план",
  kpi: "KPI", manual: "Ручной ввод",
};
export const VALUE_KIND_LABEL: Record<ValueKind, string> = {
  economy: "Экономия", uplift: "Рост", risk: "Риск",
};
export const VALUE_STATUS_LABEL: Record<ValueStatus, string> = {
  identified: "Выявлено", in_progress: "В работе", realized: "Реализовано", dismissed: "Отклонено",
};
