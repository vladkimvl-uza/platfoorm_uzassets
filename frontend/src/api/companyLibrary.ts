/**
 * Company Library (MDM) API client — Phase 2 frontend.
 * Mirrors backend/app/api/routes/company_library.py + schemas/company_library.py.
 */
import { api } from "./client";

// ── Types ─────────────────────────────────────────────────────────────

export type FieldType   = "number" | "text" | "date" | "enum" | "formula" | "boolean";
export type ScopeType   = "all"    | "sector" | "companies";
export type TabLayout   = "one_col"| "two_col" | "grid";

export interface FieldDefinition {
  id: string;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  field_type: FieldType;
  unit: string | null;
  format_pattern: string | null;
  enum_values: string[] | null;
  formula: string | null;
  scope_type: ScopeType;
  scope_value: any;
  source_module: string | null;
  source_path: string | null;
  permission_view: string | null;
  permission_edit: string | null;
  is_system: boolean;
  sort_order: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface FieldDefinitionCreate {
  code: string;
  name_ru: string;
  name_uz?: string | null;
  name_en?: string | null;
  field_type: FieldType;
  unit?: string | null;
  format_pattern?: string | null;
  enum_values?: string[] | null;
  formula?: string | null;
  scope_type?: ScopeType;
  scope_value?: any;
  source_module?: string | null;
  source_path?: string | null;
  permission_view?: string | null;
  permission_edit?: string | null;
  sort_order?: number;
}

export interface LibraryView {
  id: string;
  user_id: string;
  name: string;
  is_default: boolean;
  visible_columns: string[];
  filters: Record<string, any>;
  sort_by: string | null;
  sort_dir: "asc" | "desc";
  created_at: string;
  updated_at: string;
}

export interface LibraryTab {
  id: string;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  field_codes: string[];
  layout: TabLayout;
  is_system: boolean;
  sort_order: number;
  scope_type: ScopeType;
  scope_value: any;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LibraryCompanyRow {
  id: string;
  code: string | null;
  name_ru: string;
  name_short: string | null;
  sector_id: string | null;
  sector_name: string | null;
  fields: Record<string, any>;
}

export interface LibraryListResponse {
  items: LibraryCompanyRow[];
  total: number;
  columns: FieldDefinition[];
  available_views: LibraryView[];
  active_view_id: string | null;
}

export interface LibraryFieldValue {
  code: string;
  value: any;
  source_module: string | null;
  source_updated_at: string | null;
  source_actor: string | null;
}

export interface LibraryActivityEntry {
  ts: string;
  actor_email: string | null;
  module: string | null;
  action: string;
  field_code: string | null;
  diff: Record<string, any> | null;
}

export interface LibraryCompanyDetail {
  company_id: string;
  company_code: string | null;
  company_name: string;
  sector_id: string | null;
  sector_name: string | null;
  fields: LibraryFieldValue[];
  tabs: LibraryTab[];
  activity: LibraryActivityEntry[];
}

// ── Endpoints ─────────────────────────────────────────────────────────

export const companyLibraryApi = {
  list(params: {
    sector?: string;
    search?: string;
    view_id?: string;
    limit?: number;
    offset?: number;
  } = {}) {
    return api.get<LibraryListResponse>("/library/companies", { params }).then(r => r.data);
  },

  detail(companyId: string) {
    return api.get<LibraryCompanyDetail>(`/library/companies/${companyId}`).then(r => r.data);
  },

  updateField(companyId: string, code: string, value: any, reason?: string) {
    return api.patch(`/library/companies/${companyId}/fields/${code}`, {
      value, reason: reason ?? null,
    }).then(r => r.data);
  },

  // 30-сек тикет для sync-WebSocket (уходит в субпротокол, не в URL).
  wsTicket() {
    return api.post<{ ticket: string; expires_in: number }>(
      "/companies/ws-ticket",
    ).then(r => r.data);
  },

  activity(companyId: string, limit = 10) {
    return api.get<LibraryActivityEntry[]>(
      `/library/companies/${companyId}/activity`, { params: { limit } },
    ).then(r => r.data);
  },

  // ── Field definitions ──
  listFields(params: { sector?: string; scope_type?: string } = {}) {
    return api.get<FieldDefinition[]>("/field-definitions", { params }).then(r => r.data);
  },
  createField(payload: FieldDefinitionCreate) {
    return api.post<FieldDefinition>("/field-definitions", payload).then(r => r.data);
  },
  updateField_def(code: string, patch: Partial<FieldDefinitionCreate>) {
    return api.patch<FieldDefinition>(`/field-definitions/${code}`, patch).then(r => r.data);
  },
  deleteField_def(code: string) {
    return api.delete(`/field-definitions/${code}`);
  },

  // ── Views ──
  listViews() {
    return api.get<LibraryView[]>("/library-views").then(r => r.data);
  },
  createView(payload: { name: string; is_default?: boolean; visible_columns?: string[];
                        filters?: Record<string, any>; sort_by?: string; sort_dir?: "asc" | "desc" }) {
    return api.post<LibraryView>("/library-views", payload).then(r => r.data);
  },
  updateView(id: string, patch: Partial<LibraryView>) {
    return api.patch<LibraryView>(`/library-views/${id}`, patch).then(r => r.data);
  },
  deleteView(id: string) {
    return api.delete(`/library-views/${id}`);
  },

  // ── Tabs ──
  listTabs() {
    return api.get<LibraryTab[]>("/library-tabs").then(r => r.data);
  },
  createTab(payload: {
    code: string; name_ru: string; field_codes?: string[]; layout?: TabLayout;
    sort_order?: number; scope_type?: ScopeType; scope_value?: any;
  }) {
    return api.post<LibraryTab>("/library-tabs", payload).then(r => r.data);
  },
  updateTab(code: string, patch: Partial<LibraryTab>) {
    return api.patch<LibraryTab>(`/library-tabs/${code}`, patch).then(r => r.data);
  },
  deleteTab(code: string) {
    return api.delete(`/library-tabs/${code}`);
  },
};

// ── WebSocket envelope ────────────────────────────────────────────────

export interface FieldUpdateEvent {
  type: "field_update";
  company_id: string;
  field_code: string;
  value: any;
  source_module: string | null;
  actor_id: string | null;
  ts: number;
}
