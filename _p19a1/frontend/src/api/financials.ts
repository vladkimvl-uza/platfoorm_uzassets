import { api } from "./client";

// =====================================================================
// Types
// =====================================================================

export interface FinancialLineCatalogEntry {
  code: string;
  name_ru: string;
  name_en: string | null;
  parent_code: string | null;
  is_subtotal: boolean;
  sort_order: number;
  report_type?: string;
}

export interface CatalogResponse {
  line_codes: FinancialLineCatalogEntry[];
  standards: string[];
  report_types: { code: string; name_ru: string; name_en: string }[];
  unit_scales: { value: number; label_ru: string; short: string }[];
}

export interface FinancialLineEdit {
  line_code: string;
  line_name: string;
  line_name_uz?: string | null;
  line_name_en?: string | null;
  parent_code?: string | null;
  value: number | string | null;  // string allowed for big-number transit
  is_subtotal: boolean;
  is_calculated: boolean;
  sort_order: number;
}

export interface FinancialReportFull {
  id: string;
  company_id: string;
  company_code: string;
  company_name: string | null;
  year: number;
  quarter: number | null;
  standard: "IFRS" | "NSBU";
  report_type: "PL" | "BS" | "CF";
  currency: string;
  unit_scale: number;
  source: string;
  is_audited: boolean;
  notes: string | null;
  extra: Record<string, unknown> | null;
  lines: FinancialLineEdit[];
  created_at: string;
  updated_at: string;
  checksum: string | null;
}

export interface FinancialReportSavePayload {
  year: number;
  quarter?: number | null;
  standard: "IFRS" | "NSBU";
  report_type: "PL" | "BS" | "CF";
  currency: string;
  unit_scale: number;
  source: string;
  is_audited: boolean;
  notes?: string | null;
  extra?: Record<string, unknown> | null;
  lines: FinancialLineEdit[];
  expected_prev_checksum?: string | null;
}

export interface FinancialReportSaveResponse {
  report: FinancialReportFull;
  saved_at: string;
  lines_total: number;
  server_checksum: string;
}

export interface FinancialReportListItem {
  id: string;
  company_code: string;
  year: number;
  quarter: number | null;
  standard: string;
  report_type: string;
  is_audited: boolean;
  lines_count: number;
  updated_at: string;
}

export interface FinancialReportCreatePayload {
  company_id: string;
  year: number;
  quarter?: number | null;
  standard: "IFRS" | "NSBU";
  report_type: "PL" | "BS" | "CF";
  currency?: string;
  unit_scale?: number;
  source?: string;
}

// =====================================================================
// Portfolio summary (Phase 19a-1) — dashboard aggregator
// =====================================================================

/** Per-company financial metric breakdown returned by portfolio-summary. */
export interface PortfolioCompanyMetrics {
  company_id: string;
  company_code: string;
  company_name: string;
  company_name_short: string | null;
  sector_code: string | null;
  /** year → metric_code → value (raw currency units, value × unit_scale) */
  by_year: Record<number, Record<string, number | null>>;
}

export interface PortfolioCoverage {
  companies_total: number;
  with_revenue_any_year: number;
  /** with_data_{year} keys filled per requested year */
  [key: string]: number;
}

export interface PortfolioSummaryResponse {
  standard: "IFRS" | "NSBU";
  currency: string;
  years: number[];
  items: PortfolioCompanyMetrics[];
  /** year → metric_code → portfolio total */
  portfolio_totals_by_year: Record<number, Record<string, number>>;
  coverage: PortfolioCoverage;
}

export interface PortfolioSummaryQuery {
  standard?: "IFRS" | "NSBU";
  /** Years as JS array; serialized to comma list for backend */
  years?: number[];
  currency?: "UZS" | "USD" | "EUR";
}

// =====================================================================
// API methods
// =====================================================================

export const financialsApi = {
  async catalog() {
    const { data } = await api.get<CatalogResponse>("/financials/catalog");
    return data;
  },
  async list(params: { company_code?: string; year?: number; standard?: string } = {}) {
    const { data } = await api.get<FinancialReportListItem[]>("/financials", { params });
    return data;
  },
  async get(id: string) {
    const { data } = await api.get<FinancialReportFull>(`/financials/${id}`);
    return data;
  },
  async create(payload: FinancialReportCreatePayload) {
    const { data } = await api.post<FinancialReportFull>("/financials", payload);
    return data;
  },
  async save(id: string, payload: FinancialReportSavePayload) {
    const { data } = await api.put<FinancialReportSaveResponse>(`/financials/${id}`, payload);
    return data;
  },
  async remove(id: string) {
    await api.delete(`/financials/${id}`);
  },

  /**
   * Portfolio-wide aggregate of financial metrics for the dashboard view.
   * Single backend call returns all companies × years × metrics in one
   * shape — frontend slices per active filter without re-fetching.
   */
  async portfolioSummary(query: PortfolioSummaryQuery = {}): Promise<PortfolioSummaryResponse> {
    const params: Record<string, string> = {};
    if (query.standard) params.standard = query.standard;
    if (query.currency) params.currency = query.currency;
    if (query.years && query.years.length) params.years = query.years.join(",");
    const { data } = await api.get<PortfolioSummaryResponse>(
      "/financials/portfolio-summary",
      { params },
    );
    return data;
  },
};
