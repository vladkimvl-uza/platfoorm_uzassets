/**
 * FinModel API client — minimal surface needed for the data-entry UI.
 *
 * Only the endpoints the editor actually calls are wrapped here. The backend
 * has 25 endpoints (audit, scenarios, comments, etc.) but those will be added
 * when their respective UI tabs are reconnected.
 */
import { api } from "./client";

const BASE = "/finmodel";

export type RowType = "input" | "subtotal" | "grand" | "check";

export interface TemplateRow {
  code: string;
  section: "BS" | "PL";
  order_idx: number;
  parent_code: string | null;
  row_type: RowType;
  name_ru: string;
  name_uz: string | null;
  name_uz_cyr: string | null;
  name_en: string | null;
  formula: string | null;
  dashboard_category: string | null;
  sign_convention: "positive" | "negative" | null;
  is_indent: number;
  legacy_note: string | null;
}

export interface CellValue {
  row_code: string;
  value: string | null;
  is_calculated: boolean;
  updated_at: string | null;
}

export interface YearLock {
  year: number;
  status: "draft" | "review" | "approved" | "locked";
  locked_at: string | null;
  locked_by: string | null;
  approval_note: string | null;
}

export interface BalanceCheck {
  is_balanced: boolean;
  delta: string;
  asset_total: string;
  liab_total: string;
}

export interface YearData {
  company_id: string;
  year: number;
  lock: YearLock;
  cells: CellValue[];
  balance_check: BalanceCheck;
}

export interface ValidationIssue {
  rule_id: string;
  severity: "error" | "warning" | "info";
  row_code: string | null;
  message_ru: string;
  message_en: string | null;
}

export interface MacroGlobal {
  year: number;
  uz_inflation: string | null;
  us_inflation: string | null;
  uzs_usd_avg_rate: string | null;
  uzs_eur_avg_rate: string | null;
  uzs_rub_avg_rate: string | null;
  uzs_cny_avg_rate: string | null;
  updated_at: string | null;
}

export interface MacroEffective {
  year: number;
  uz_inflation: string | null;
  us_inflation: string | null;
  uzs_usd_avg_rate: string | null;
  uzs_eur_avg_rate: string | null;
  uzs_rub_avg_rate: string | null;
  uzs_cny_avg_rate: string | null;
  source: Record<string, "company" | "global" | "none">;
}

export interface MacroCompanyPayload {
  uz_inflation?: string | null;
  us_inflation?: string | null;
  uzs_usd_avg_rate?: string | null;
  uzs_eur_avg_rate?: string | null;
  uzs_rub_avg_rate?: string | null;
  uzs_cny_avg_rate?: string | null;
}

export interface AuditEntry {
  id: string;
  year: number;
  row_code: string;
  value_before: string | null;
  value_after: string | null;
  actor_id: string | null;
  source: string;
  ts: string;
}

export const finmodelApi = {
  async getTemplate(): Promise<TemplateRow[]> {
    const { data } = await api.get<TemplateRow[]>(`${BASE}/template`);
    return data;
  },
  async listYears(companyId: string): Promise<YearLock[]> {
    const { data } = await api.get<YearLock[]>(`${BASE}/${companyId}`);
    return data;
  },
  async getYear(companyId: string, year: number): Promise<YearData> {
    const { data } = await api.get<YearData>(`${BASE}/${companyId}/${year}`);
    return data;
  },
  async createYear(companyId: string, year: number): Promise<YearLock> {
    const { data } = await api.post<YearLock>(`${BASE}/${companyId}/year/${year}`);
    return data;
  },
  async patchCell(
    companyId: string,
    year: number,
    rowCode: string,
    value: string | null,
  ): Promise<CellValue> {
    const { data } = await api.patch<CellValue>(
      `${BASE}/${companyId}/${year}/cell`,
      { row_code: rowCode, value },
    );
    return data;
  },

  async validate(companyId: string, year: number): Promise<ValidationIssue[]> {
    const { data } = await api.get<ValidationIssue[]>(`${BASE}/${companyId}/${year}/validate`);
    return data;
  },

  async listMacroGlobal(): Promise<MacroGlobal[]> {
    const { data } = await api.get<MacroGlobal[]>(`${BASE}/macro/global`);
    return data;
  },

  async getMacro(companyId: string, year: number): Promise<MacroEffective> {
    const { data } = await api.get<MacroEffective>(`${BASE}/${companyId}/${year}/macro`);
    return data;
  },

  async putMacro(
    companyId: string,
    year: number,
    payload: MacroCompanyPayload,
  ): Promise<MacroEffective> {
    const { data } = await api.put<MacroEffective>(
      `${BASE}/${companyId}/${year}/macro`,
      payload,
    );
    return data;
  },

  async getAudit(
    companyId: string,
    year: number,
    rowCode?: string,
    limit = 100,
  ): Promise<{ items: AuditEntry[]; total: number }> {
    const params: Record<string, string | number> = { limit };
    if (rowCode) params.row_code = rowCode;
    const { data } = await api.get(`${BASE}/${companyId}/${year}/audit`, { params });
    return data;
  },

  async exportCsv(companyId: string, year: number, includeMacro = true): Promise<Blob> {
    const { data } = await api.get(`${BASE}/${companyId}/${year}/export.csv`, {
      params: { include_macro: includeMacro },
      responseType: "blob",
    });
    return data as Blob;
  },

  async deleteYear(companyId: string, year: number): Promise<void> {
    await api.delete(`${BASE}/${companyId}/year/${year}`);
  },

  async lockYear(
    companyId: string,
    year: number,
    status: "review" | "approved" | "locked",
    note?: string,
  ): Promise<YearLock> {
    const { data } = await api.post<YearLock>(
      `${BASE}/${companyId}/year/${year}/lock`,
      { status, approval_note: note ?? null },
    );
    return data;
  },

  async unlockYear(companyId: string, year: number): Promise<YearLock> {
    const { data } = await api.post<YearLock>(`${BASE}/${companyId}/year/${year}/unlock`);
    return data;
  },
};
