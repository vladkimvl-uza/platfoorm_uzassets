import { api } from "./client";
import { i18nKey } from "@/locale/keys";

export type ExtStatus = "active" | "sandbox" | "deprecated" | "disabled";
export type AuthKind  = "oauth2" | "api_key" | "basic" | "mtls" | "jwt" | "none";
export type EnvKind   = "production" | "sandbox" | "on-prem";

export interface ExtContact {
  name: string;
  email?: string | null;
  phone?: string | null;
  role?: string | null;
}

export interface ExternalApi {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  base_url: string;
  documentation_url: string | null;
  health_check_url: string | null;
  status: ExtStatus;
  owner_id: string | null;
  created_by_id: string | null;
  contacts: ExtContact[] | null;
  tags: string[] | null;
  environment_kind: EnvKind | null;
  auth_kind: AuthKind | null;
  auth_details: Record<string, unknown> | null;
  openapi_spec_version: string | null;
  openapi_uploaded_at: string | null;
  openapi_uploaded_by_id: string | null;
  has_openapi_spec: boolean;
  notes: string | null;
  endpoint_count: number;
  created_at: string;
  updated_at: string;
}

export interface ExtEndpoint {
  path: string;
  method: string;
  operation_id: string | null;
  summary: string | null;
  description: string | null;
  tags: string[];
  deprecated: boolean;
}

export interface ExtCatalogSummary {
  api_id: string;
  title: string;
  version: string;
  description: string | null;
  servers: { url: string; description?: string }[];
  total_endpoints: number;
  endpoints: ExtEndpoint[];
}

export const externalApis = {
  async list(q?: string, status?: ExtStatus): Promise<{ items: ExternalApi[]; total: number }> {
    const params: any = {};
    if (q) params.q = q;
    if (status) params.status = status;
    const r = await api.get("/external-apis", { params });
    return r.data;
  },
  async create(payload: {
    slug: string; name: string; description?: string | null;
    base_url: string; documentation_url?: string | null; health_check_url?: string | null;
    status?: ExtStatus;
    owner_id?: string | null;
    contacts?: ExtContact[] | null;
    tags?: string[] | null;
    environment_kind?: EnvKind | null;
    auth_kind?: AuthKind | null;
    auth_details?: Record<string, unknown> | null;
    notes?: string | null;
  }): Promise<ExternalApi> {
    const r = await api.post<ExternalApi>("/external-apis", payload);
    return r.data;
  },
  async update(id: string, payload: Partial<{
    name: string; description: string | null;
    base_url: string; documentation_url: string | null; health_check_url: string | null;
    status: ExtStatus;
    owner_id: string | null;
    contacts: ExtContact[] | null;
    tags: string[] | null;
    environment_kind: EnvKind | null;
    auth_kind: AuthKind | null;
    auth_details: Record<string, unknown> | null;
    notes: string | null;
  }>): Promise<ExternalApi> {
    const r = await api.patch<ExternalApi>(`/external-apis/${id}`, payload);
    return r.data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/external-apis/${id}`);
  },

  async uploadSpec(id: string, spec: Record<string, unknown>): Promise<{
    version: string; endpoint_count: number; title?: string; uploaded_at: string;
  }> {
    const r = await api.post(`/external-apis/${id}/openapi`, { spec });
    return r.data;
  },
  async removeSpec(id: string): Promise<void> {
    await api.delete(`/external-apis/${id}/openapi`);
  },
  async catalog(id: string): Promise<ExtCatalogSummary> {
    const r = await api.get<ExtCatalogSummary>(`/external-apis/${id}/catalog`);
    return r.data;
  },
  downloadUrl(id: string): string {
    return `/api/external-apis/${id}/openapi.json`;
  },
};

// ─── Helpers ───────────────────────────────────────────────────

export function statusPill(s: ExtStatus): { color: string; bg: string; label: string } {
  switch (s) {
    case "active":     return { color: "#0F6E56", bg: "rgba(29,158,117,.12)",  label: "active" };
    case "sandbox":    return { color: "#854F0B", bg: "rgba(239,159,39,.15)",  label: "sandbox" };
    case "deprecated": return { color: "#A32D2D", bg: "rgba(226,75,74,.1)",    label: "deprecated" };
    case "disabled":   return { color: "#6E6A78", bg: "rgba(0,0,0,.07)",       label: "disabled" };
  }
}

export const AUTH_LABELS: Record<AuthKind, string> = {
  oauth2:  i18nKey("OAuth 2.0"),
  api_key: i18nKey("API key"),
  basic:   i18nKey("Basic auth"),
  mtls:    i18nKey("mTLS"),
  jwt:     i18nKey("JWT bearer"),
  none:    i18nKey("Без авторизации"),
};
