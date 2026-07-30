import { api } from "./client";
import { i18nKey } from "@/locale/keys";

// ─── Types ───────────────────────────────────────────────────

export interface Badge {
  text: string;
  color: string;
  bg_color?: string | null;
  position?: string | null;
}

export interface CompanyAdmin {
  id: string;
  code: string;
  name_ru: string;
  name_short: string | null;
  name_uz: string | null;
  name_uz_cyr: string | null;
  name_en: string | null;
  legal_form: string | null;
  ownership_entity: string | null;
  inn: string | null;

  sector_id: string | null;
  sector_code: string | null;
  sector_name: string | null;

  description: string | null;
  website: string | null;
  address: string | null;
  ceo_name: string | null;
  employees_count: number | null;
  founded_year: number | null;

  is_active: boolean;
  is_custom: boolean;
  sort_order: number;

  primary_color: string | null;
  secondary_color: string | null;
  badges: Badge[] | null;
  status: string | null;

  is_pinned: boolean;
  include_in_rollups: boolean;
  module_flags: Record<string, boolean> | null;

  parent_id: string | null;
  parent_code: string | null;
  portfolio_start_year: number | null;

  primary_currency: string;
  fy_start_month: number;
  track_inflation: boolean;

  bloomberg_ticker: string | null;
  isin: string | null;
  lei: string | null;

  tags: string[] | null;
  aliases: string[] | null;

  children_count: number;
  year_overrides_count: number;
}

export type CompanyStatus =
  | "active" | "pilot" | "under_audit" | "divested"
  | "restructuring" | "m_a" | "ipo_imminent";

export type ExclusionReason =
  | "restructuring" | "m_a" | "divestment" | "not_in_portfolio" | "audit" | "other";

export interface CompanyYearOverride {
  id: string;
  company_id: string;
  year: number;
  is_hidden: boolean;
  name_override: string | null;
  sector_override_id: string | null;
  sector_override_code: string | null;
  exclusion_reason: ExclusionReason | null;
  notes: string | null;
}

export interface CompanyYearOverrideUpsert {
  year: number;
  is_hidden: boolean;
  name_override?: string | null;
  sector_override_code?: string | null;
  exclusion_reason?: ExclusionReason | null;
  notes?: string | null;
}

export interface SectorAdmin {
  id: string;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_uz_cyr: string | null;
  name_en: string | null;
  color_hex: string | null;
  color_secondary: string | null;
  icon_name: string | null;
  short_badge: string | null;
  sort_order: number;
  aliases: string[] | null;
  companies_count: number;
}

export interface CompanyTreeNode {
  id: string;
  code: string;
  name_short: string | null;
  name_ru: string;
  sector_code: string | null;
  primary_color: string | null;
  badges: Badge[] | null;
  status: string | null;
  children: CompanyTreeNode[];
}

// ─── API ─────────────────────────────────────────────────────

export const companiesAdminV2Api = {
  async list(params: { sector?: string; status?: string; search?: string; only_active?: boolean } = {}) {
    const r = await api.get<CompanyAdmin[]>("/companies-admin/v2/list", { params });
    return r.data;
  },
  async get(code: string) {
    const r = await api.get<CompanyAdmin>(`/companies-admin/v2/${code}`);
    return r.data;
  },
  async create(payload: Partial<CompanyAdmin> & { code: string; name_ru: string }) {
    const r = await api.post<CompanyAdmin>("/companies-admin/v2/create", payload);
    return r.data;
  },
  async update(code: string, payload: Partial<CompanyAdmin>) {
    const r = await api.patch<CompanyAdmin>(`/companies-admin/v2/${code}`, payload);
    return r.data;
  },
  async remove(code: string) {
    await api.delete(`/companies-admin/v2/${code}`);
  },
  async listYearOverrides(code: string) {
    const r = await api.get<CompanyYearOverride[]>(`/companies-admin/v2/${code}/year-overrides`);
    return r.data;
  },
  async setYearOverrides(code: string, overrides: CompanyYearOverrideUpsert[]) {
    const r = await api.put<CompanyYearOverride[]>(`/companies-admin/v2/${code}/year-overrides`, { overrides });
    return r.data;
  },
  async hierarchyTree() {
    const r = await api.get<CompanyTreeNode[]>("/companies-admin/v2/tree/hierarchy");
    return r.data;
  },
};

export const sectorsAdminV2Api = {
  async list() {
    const r = await api.get<SectorAdmin[]>("/sectors-admin/v2/list");
    return r.data;
  },
  async create(payload: Partial<SectorAdmin> & { code: string; name_ru: string }) {
    const r = await api.post<SectorAdmin>("/sectors-admin/v2/create", payload);
    return r.data;
  },
  async update(code: string, payload: Partial<SectorAdmin>) {
    const r = await api.patch<SectorAdmin>(`/sectors-admin/v2/${code}`, payload);
    return r.data;
  },
  async remove(code: string) {
    await api.delete(`/sectors-admin/v2/${code}`);
  },
};

// ─── Constants ───────────────────────────────────────────────

export const COLOR_PALETTE = [
  "#7F77DD", "#1D9E75", "#378ADD", "#EF9F27", "#D4537E",
  "#E24B4A", "#534AB7", "#888780", "#0F6E56", "#A36500",
];

export const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  active:        { label: i18nKey("Активна"),         color: "#1D9E75" },
  pilot:         { label: "Pilot",            color: "#534AB7" },
  under_audit:   { label: i18nKey("На аудите"),       color: "#EF9F27" },
  divested:      { label: i18nKey("Продана"),         color: "#888780" },
  restructuring: { label: i18nKey("Реструктуризация"), color: "#EF9F27" },
  m_a:           { label: "M&A",              color: "#D4537E" },
  ipo_imminent:  { label: i18nKey("IPO скоро"),       color: "#378ADD" },
};

export const EXCLUSION_REASONS: Record<string, string> = {
  restructuring:    i18nKey("Реструктуризация"),
  m_a:              i18nKey("Слияние / M&A"),
  divestment:       i18nKey("Дивестиция"),
  not_in_portfolio: i18nKey("Не входила в портфель"),
  audit:            i18nKey("Аудит данных"),
  other:            i18nKey("Другое"),
};

export const MODULE_FLAGS = [
  { code: "kpi",         label: "KPI tracking" },
  { code: "esg",         label: "ESG metrics" },
  { code: "procurement", label: "Procurement audit" },
  { code: "financials",  label: "Financial reports" },
  { code: "governance",  label: "Governance" },
];

export const SECTOR_ICONS = [
  "pick", "mountain", "hammer", "diamond",       // mining
  "droplet", "flame", "barrel",                  // oil/gas
  "bolt", "battery", "sun",                      // energy
  "plane", "train", "ship", "truck", "car",      // transport
  "broadcast", "wifi", "phone",                  // telecom
  "building-bank", "coin",                       // finance
  "flask", "atom",                               // chemical
];

export function statusBadge(status: string | null): { label: string; color: string } {
  return STATUS_LABELS[status || ""] || { label: status || "—", color: "#888780" };
}
