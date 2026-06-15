import { api } from "./client";

// =====================================================================
// Type definitions matching backend Pydantic schemas
// =====================================================================

export interface SectorBrief {
  id: string;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  color_hex: string | null;
  sort_order: number;
  company_count?: number;
}

export interface SectorCreatePayload {
  code: string;
  name_ru: string;
  name_uz?: string | null;
  name_en?: string | null;
  color_hex?: string | null;
  sort_order?: number;
}

export interface SectorUpdatePayload {
  name_ru?: string;
  name_uz?: string | null;
  name_en?: string | null;
  color_hex?: string | null;
  sort_order?: number;
}

export interface CompanyCreatePayload {
  code: string;
  name_ru: string;
  name_short?: string;
  name_uz?: string;
  name_en?: string;
  sector_code?: string;
  legal_form?: string;
  inn?: string;
  description?: string;
  website?: string;
  address?: string;
  ceo_name?: string;
  employees_count?: number;
  founded_year?: number;
}

export interface CompanyUpdatePayload {
  name_ru?: string;
  name_short?: string;
  name_uz?: string;
  name_en?: string;
  sector_code?: string;
  legal_form?: string;
  inn?: string;
  description?: string;
  website?: string;
  address?: string;
  ceo_name?: string;
  employees_count?: number;
  founded_year?: number;
  is_active?: boolean;
  sort_order?: number;
  hidden_years?: number[] | null;}

export interface CompanyListItem {
  id: string;
  code: string;
  name_ru: string;
  name_short: string | null;
  sector_code: string | null;
  sector_name: string | null;
  sector_color: string | null;
  is_active: boolean;
  is_custom: boolean;
  hidden_years?: number[] | null;  governance_score: number | null;
  latest_revenue: string | null; // Decimal serialized as string
  latest_revenue_year: number | null;
  has_financials: boolean;
  has_governance: boolean;
}

export interface CompanyListResponse {
  items: CompanyListItem[];
  total: number;
  sectors: SectorBrief[];
}

export interface CompanyDetail {
  id: string;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  name_short: string | null;
  legal_form: string | null;
  inn: string | null;
  sector: SectorBrief | null;
  description: string | null;
  website: string | null;
  address: string | null;
  ceo_name: string | null;
  employees_count: number | null;
  founded_year: number | null;
  is_active: boolean;
  is_custom: boolean;
  extra: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface FinancialLineBrief {
  line_code: string;
  line_name: string;
  value: string | null;
  sort_order: number;
}

export interface FinancialReportBrief {
  year: number;
  quarter: number | null;
  standard: string;
  report_type: string;
  currency: string;
  unit_scale: number;
  source: string;
  is_audited: boolean;
  notes: string | null;
  lines: FinancialLineBrief[];
}

export interface GovernanceBrief {
  year: number;
  board_size: number | null;
  independent_directors_count: number | null;
  women_directors_count: number | null;
  foreign_directors_count: number | null;
  avg_age: number | null;
  has_audit_committee: boolean | null;
  has_strategy_committee: boolean | null;
  meetings_per_year: number | null;
  avg_attendance_pct: number | null;
  score: number | null;
  payload: Record<string, unknown> | null;
}

export interface DashboardStats {
  companies_total: number;
  companies_with_financials: number;
  companies_with_governance: number;
  sectors_count: number;
  financial_reports_count: number;
  announcements_published: number;
  total_revenue_latest_year: string | null;
  latest_revenue_year: number | null;
  average_governance_score: number | null;
  top_governance_companies: Array<{
    code: string;
    name_short: string | null;
    name_ru: string;
    score: number;
  }>;
}

// =====================================================================
// API methods
// =====================================================================

export interface CompanyListQuery {
  sector?: string;
  search?: string;
  active_only?: boolean;
  custom_only?: boolean | null;
  sort_by?: "sort_order" | "code" | "name_ru" | "governance_score" | "latest_revenue";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface CompanyEmployee {
  id: string;
  full_name: string;
  email: string;
  initials: string;
  accent: string;
  role: string | null;
  is_owner: boolean;
  department: string | null;
  job_title: string | null;
  avatar_url: string | null;
  is_active: boolean;
  last_active: string | null;
}

export interface CompanyEmployeesResponse {
  company_code: string;
  company_name: string;
  total: number;
  employees: CompanyEmployee[];
}

export const companiesApi = {
  async list(query: CompanyListQuery = {}): Promise<CompanyListResponse> {
    const { data } = await api.get<CompanyListResponse>("/companies", {
      params: query,
    });
    return data;
  },

  async getOne(code: string): Promise<CompanyDetail> {
    const { data } = await api.get<CompanyDetail>(`/companies/${code}`);
    return data;
  },

  async create(payload: CompanyCreatePayload): Promise<CompanyDetail> {
    const { data } = await api.post<CompanyDetail>("/companies", payload);
    return data;
  },

  async update(code: string, payload: CompanyUpdatePayload): Promise<CompanyDetail> {
    const { data } = await api.patch<CompanyDetail>(`/companies/${code}`, payload);
    return data;
  },

  async getFinancials(code: string): Promise<FinancialReportBrief[]> {
    const { data } = await api.get<FinancialReportBrief[]>(`/companies/${code}/financials`);
    return data;
  },

  async getGovernance(code: string): Promise<GovernanceBrief[]> {
    const { data } = await api.get<GovernanceBrief[]>(`/companies/${code}/governance`);
    return data;
  },

  /** Сотрудники компании на платформе (привязка через organization_id). */
  async getEmployees(code: string): Promise<CompanyEmployeesResponse> {
    const { data } = await api.get<CompanyEmployeesResponse>(`/companies/${code}/employees`);
    return data;
  },

  /** Soft-deactivate (cascade=false) or hard-delete with cascade. */
  async remove(code: string, cascade = false): Promise<void> {
    await api.delete(`/companies/${code}`, { params: { cascade } });
  },

  /** Wipe all financial reports for a company, optionally filtered. */
  async deleteFinancials(code: string, opts: { standard?: "IFRS" | "NSBU"; year?: number } = {}): Promise<void> {
    await api.delete(`/companies/${code}/financials`, { params: opts });
  },

  // ---------------------------------------------------------------
  // Sectors
  // ---------------------------------------------------------------
  async listSectors(includeCounts = false): Promise<SectorBrief[]> {
    const { data } = await api.get<SectorBrief[]>("/companies/sectors/list", {
      params: { include_counts: includeCounts },
    });
    return data;
  },
  async createSector(payload: SectorCreatePayload): Promise<SectorBrief> {
    const { data } = await api.post<SectorBrief>("/companies/sectors", payload);
    return data;
  },
  async updateSector(code: string, payload: SectorUpdatePayload): Promise<SectorBrief> {
    const { data } = await api.patch<SectorBrief>(`/companies/sectors/${code}`, payload);
    return data;
  },
  async removeSector(code: string): Promise<void> {
    await api.delete(`/companies/sectors/${code}`);
  },
};

export const dashboardApi = {
  async stats(): Promise<DashboardStats> {
    const { data } = await api.get<DashboardStats>("/dashboard/stats");
    return data;
  },
};
