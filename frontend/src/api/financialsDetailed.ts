/**
 * Detailed audited financial reports API.
 */
import { api } from "./client";

export interface CanonicalLine {
  code: string;
  label: string;
  label_ru: string | null;
  section: string | null;
  is_subtotal: boolean;
  indent: number;
}

export type CanonicalCatalog = Record<"BS" | "PL" | "CF", CanonicalLine[]>;

export interface PreviewRow {
  code: string;
  label: string;
  indent_level: number;
  section_label: string | null;
  is_subtotal: boolean;
  values: Record<string, number | null>;
  canonical_code: string | null;
  is_unmapped: boolean;
}

export interface PreviewSection {
  report_type: "BS" | "PL" | "CF";
  years: number[];
  warnings: string[];
  rows: PreviewRow[];
  missing_canonical_codes: string[];
  unmapped_count: number;
}

export interface PreviewSheet {
  sheet_name: string;
  company_code: string;
  company_name: string;
  warnings: string[];
  sections: PreviewSection[];
}

export interface PreviewResult {
  standard: string;
  filename: string;
  sheets: PreviewSheet[];
  summary: {
    sheets: number;
    sections: number;
    rows: number;
    unmapped_rows: number;
  };
}

export interface ConfirmResult {
  standard: string;
  companies_imported: number;
  company_codes: string[];
  reports_created: number;
  lines_created: number;
  skipped: string[];
}

export interface DetailedRow {
  code: string;
  label: string;
  section: string | null;
  indent: number;
  is_subtotal: boolean;
  sort_order: number;
  values: Record<string, number | null>;
  canonical_code: string | null;
  is_unmapped: boolean;
}

export interface DetailedReport {
  company_code: string;
  company_name: string;
  standard: "IFRS" | "NSBU";
  report_type: "PL" | "BS" | "CF";
  years: number[];
  rows: DetailedRow[];
  has_data: boolean;
  imported_at?: string;
  source_filename?: string;
}


export const detailedFinancialsApi = {
  async catalog(): Promise<CanonicalCatalog> {
    const r = await api.get("/financials/detailed/canonical/catalog");
    return r.data;
  },

  async preview(opts: {
    file: File;
    standard?: "IFRS" | "NSBU";
    company_code?: string;
    sheet_name?: string;
  }): Promise<PreviewResult> {
    const fd = new FormData();
    fd.append("file", opts.file);
    fd.append("standard", opts.standard || "IFRS");
    if (opts.company_code) fd.append("company_code", opts.company_code);
    if (opts.sheet_name) fd.append("sheet_name", opts.sheet_name);
    const r = await api.post("/financials/detailed/parse-preview", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return r.data;
  },

  async confirmImport(payload: {
    standard: "IFRS" | "NSBU";
    is_audited?: boolean;
    filename: string;
    sheets: Array<{
      company_code: string;
      sections: Array<{
        report_type: "BS" | "PL" | "CF";
        years: number[];
        rows: Array<{
          code: string;
          label: string;
          canonical_code: string | null;
          is_unmapped: boolean;
          indent_level: number;
          section_label: string | null;
          is_subtotal: boolean;
          values: Record<string, number | null>;
        }>;
      }>;
    }>;
  }): Promise<ConfirmResult> {
    const r = await api.post("/financials/detailed/import-confirm", payload);
    return r.data;
  },

  async get(
    company_code: string,
    standard: "IFRS" | "NSBU" = "IFRS",
    report_type: "PL" | "BS" | "CF" = "BS",
  ): Promise<DetailedReport> {
    const r = await api.get(`/financials/detailed/${company_code}`, {
      params: { standard, report_type },
    });
    return r.data;
  },

  async updateCell(
    company_code: string, standard: "IFRS" | "NSBU",
    report_type: "PL" | "BS" | "CF", year: number, line_code: string,
    value: number | null,
  ): Promise<void> {
    await api.put(`/financials/detailed/${company_code}/cell`, null, {
      params: { standard, report_type, year, line_code, value },
    });
  },

  async updateLineMapping(
    company_code: string, standard: "IFRS" | "NSBU",
    report_type: "PL" | "BS" | "CF", line_code: string,
    canonical_code: string | null, new_label?: string,
  ): Promise<void> {
    const params: any = { standard, report_type, line_code };
    if (canonical_code !== undefined && canonical_code !== null) {
      params.canonical_code = canonical_code;
    }
    if (new_label) params.new_label = new_label;
    await api.put(`/financials/detailed/${company_code}/line/mapping`, null, { params });
  },

  async deleteLine(
    company_code: string, standard: "IFRS" | "NSBU",
    report_type: "PL" | "BS" | "CF", line_code: string,
  ): Promise<void> {
    await api.delete(`/financials/detailed/${company_code}/line`, {
      params: { standard, report_type, line_code },
    });
  },
};
