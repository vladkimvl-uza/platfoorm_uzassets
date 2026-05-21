import { api } from "./client";

// =====================================================================
// Consultants API
//
// Backend: GET /consultants returns {consultants: [{id, code, name, abbr,
// color, is_big4, is_active, sort_order}]} — note `name` (not name_ru)
// and `color` (not color_hex). We normalize on read.
//
// New endpoint: GET /consultants/by-company/{company_id}?year=
// Returns consultants who work with this company through tasks.
// =====================================================================

/** Normalized consultant brief used everywhere on frontend. */
export interface ConsultantBrief {
  id: string;
  code: string;
  name_ru: string;
  name_en?: string | null;
  abbr: string | null;
  color_hex: string | null;
  is_big4?: boolean;
  is_active?: boolean;
}

export interface ConsultantListResponseRaw {
  items?: any[];
  consultants?: any[];
  total?: number;
}

/** Per-company consultant card data (from /by-company/{id}). */
export interface CompanyConsultant {
  id: string;
  code: string;
  name: string;
  abbr: string | null;
  color: string | null;
  is_big4: boolean;
  task_count: number;
  task_done: number;
  task_overdue: number;
  completion_pct: number;
  sources: string[];   // ['task' | 'manual' | 'lookup', ...]
  projects: Array<{
    id: string;
    num: number | null;
    title: string;
    status: string;
    due_date: string | null;
  }>;
}

export interface CompanyConsultantsResponse {
  company_id: string;
  year: number | null;
  consultants: CompanyConsultant[];
  total_assignments: number;
  total_consultants: number;
}

// ---------------------------------------------------------------------
// Normalization — backend uses {name, color}, we expose {name_ru, color_hex}
// ---------------------------------------------------------------------

function normalizeConsultant(c: any): ConsultantBrief {
  return {
    id: c.id,
    code: c.code,
    name_ru: c.name_ru || c.name || c.code || "—",
    name_en: c.name_en ?? null,
    abbr: c.abbr ?? null,
    color_hex: c.color_hex || c.color || null,
    is_big4: !!c.is_big4,
    is_active: c.is_active !== false,
  };
}

// ---------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------

export const consultantsApi = {
  /** Returns flat array of all consultants in the system (normalized shape). */
  async list(): Promise<ConsultantBrief[]> {
    const { data } = await api.get<any>("/consultants");
    let raw: any[];
    if (Array.isArray(data)) {
      raw = data;
    } else if (Array.isArray(data?.consultants)) {
      raw = data.consultants;
    } else if (Array.isArray(data?.items)) {
      raw = data.items;
    } else {
      raw = [];
    }
    return raw.map(normalizeConsultant);
  },

  /**
   * Returns consultants working with this company (through tasks → assignments).
   * Optional year filter narrows to specific portfolio_year.
   */
  async byCompany(companyId: string, year?: number): Promise<CompanyConsultantsResponse> {
    const params: Record<string, any> = {};
    if (year) params.year = year;
    const { data } = await api.get<CompanyConsultantsResponse>(
      `/consultants/by-company/${companyId}`,
      { params }
    );
    return data;
  },

  /** Admin: list all (including inactive). */
  async listAll(): Promise<ConsultantBrief[]> {
    const { data } = await api.get<any>("/consultants", { params: { include_inactive: true } });
    const raw = data?.consultants ?? data?.items ?? data ?? [];
    return (Array.isArray(raw) ? raw : []).map(normalizeConsultant);
  },

  async create(payload: {
    name: string; code?: string; name_en?: string | null;
    abbr?: string | null; color?: string | null;
    is_big4?: boolean; is_active?: boolean; sort_order?: number;
  }): Promise<ConsultantBrief> {
    const { data } = await api.post<any>("/consultants", payload);
    return normalizeConsultant(data);
  },

  async update(id: string, payload: {
    name?: string; name_en?: string | null;
    abbr?: string | null; color?: string | null;
    is_big4?: boolean; is_active?: boolean; sort_order?: number;
  }): Promise<ConsultantBrief> {
    const { data } = await api.patch<any>(`/consultants/${id}`, payload);
    return normalizeConsultant(data);
  },

  async usage(id: string): Promise<{ assignments: number; code: string; name: string }> {
    const { data } = await api.get(`/consultants/${id}/usage`);
    return data;
  },

  async remove(id: string, opts?: { hard?: boolean }): Promise<void> {
    await api.delete(`/consultants/${id}`, { params: opts?.hard ? { hard: true } : {} });
  },
};
