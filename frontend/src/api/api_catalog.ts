import { api } from "./client";

// ─── Types ─────────────────────────────────────────────────────

export type Environment = "production" | "sandbox";

export interface CatalogEndpoint {
  path: string;
  method: string;
  operation_id: string | null;
  summary: string | null;
  description: string | null;
  tags: string[];
  module: string | null;
  required_permission: string | null;
  request_schema_ref: string | null;
  response_schema_ref: string | null;
  deprecated: boolean;
}

export interface CatalogModule {
  name: string;
  group: string | null;
  description: string | null;
  endpoints_count: number;
}

export interface CatalogSummary {
  title: string;
  version: string;
  total_endpoints: number;
  modules: CatalogModule[];
  endpoints: CatalogEndpoint[];
}

export interface ScopeItem {
  code: string;
  name: string;
  module: string | null;
  description: string | null;
}

export interface ScopeListResponse {
  items: ScopeItem[];
  grouped_by_module: Record<string, ScopeItem[]>;
}

export interface ServiceAccount {
  id: string;
  email: string;
  full_name: string | null;
  description: string | null;
  owner_id: string | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  keys_count: number | null;
}

export interface ApiKey {
  id: string;
  service_account_id: string;
  created_by_id: string | null;
  name: string;
  description: string | null;
  prefix: string;
  scopes: string[];
  environment: Environment;
  rate_limit_per_minute: number;
  ip_allowlist: string[] | null;
  expires_at: string | null;
  revoked_at: string | null;
  revoked_by_id: string | null;
  revoke_reason: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  total_calls: number;
  failed_calls: number;
  created_at: string;
  updated_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  plaintext_token: string;
}

export interface ApiKeyAuditEntry {
  id: string;
  created_at: string;
  api_key_id: string | null;
  actor_id: string | null;
  http_method: string | null;
  http_path: string | null;
  http_status: number | null;
  duration_ms: number | null;
  ip_address: string | null;
}

// ─── API client ────────────────────────────────────────────────

export const apiCatalogApi = {
  async summary(): Promise<CatalogSummary> {
    const r = await api.get<CatalogSummary>("/api-catalog/summary");
    return r.data;
  },
  async scopes(): Promise<ScopeListResponse> {
    const r = await api.get<ScopeListResponse>("/api-catalog/scopes");
    return r.data;
  },
  openapiUrl(): string  { return "/api/api-catalog/openapi.enriched.json"; },
  postmanUrl(): string  { return "/api/api-catalog/postman.json"; },
};

export const apiKeysApi = {
  async catalog() {
    const r = await api.get("/api-keys/catalog");
    return r.data as {
      environments: { code: Environment; label: string; prefix: string; color: string }[];
      counts: { total: number; active: number; revoked: number; service_accounts: number };
    };
  },

  // Service accounts
  async listServiceAccounts(q?: string): Promise<{ items: ServiceAccount[]; total: number }> {
    const r = await api.get("/api-keys/service-accounts", { params: q ? { q } : {} });
    return r.data;
  },
  async createServiceAccount(payload: {
    email: string; full_name: string; description?: string | null; owner_id?: string | null;
  }): Promise<ServiceAccount> {
    const r = await api.post<ServiceAccount>("/api-keys/service-accounts", payload);
    return r.data;
  },
  async updateServiceAccount(id: string, payload: Partial<{
    full_name: string; description: string | null; owner_id: string | null; is_active: boolean;
  }>): Promise<ServiceAccount> {
    const r = await api.patch<ServiceAccount>(`/api-keys/service-accounts/${id}`, payload);
    return r.data;
  },
  async deleteServiceAccount(id: string) {
    await api.delete(`/api-keys/service-accounts/${id}`);
  },

  // Keys
  async listKeys(serviceAccountId?: string, includeRevoked = true): Promise<{ items: ApiKey[]; total: number }> {
    const params: Record<string, unknown> = { include_revoked: includeRevoked };
    if (serviceAccountId) params.service_account_id = serviceAccountId;
    const r = await api.get("/api-keys", { params });
    return r.data;
  },
  async createKey(payload: {
    service_account_id: string;
    name: string; description?: string | null;
    scopes: string[]; environment: Environment;
    rate_limit_per_minute: number;
    ip_allowlist?: string[] | null;
    expires_at?: string | null;
  }): Promise<ApiKeyCreated> {
    const r = await api.post<ApiKeyCreated>("/api-keys", payload);
    return r.data;
  },
  async updateKey(id: string, payload: Partial<{
    name: string; description: string | null; scopes: string[];
    rate_limit_per_minute: number; ip_allowlist: string[] | null; expires_at: string | null;
  }>): Promise<ApiKey> {
    const r = await api.patch<ApiKey>(`/api-keys/${id}`, payload);
    return r.data;
  },
  async revokeKey(id: string, reason?: string): Promise<ApiKey> {
    const r = await api.post<ApiKey>(`/api-keys/${id}/revoke`, { reason });
    return r.data;
  },
  async keyAudit(id: string, limit = 100): Promise<{ items: ApiKeyAuditEntry[]; total: number }> {
    const r = await api.get(`/api-keys/${id}/audit`, { params: { limit } });
    return r.data;
  },
};


// ─── Helpers ───────────────────────────────────────────────────

export const METHOD_PILL: Record<string, { color: string; bg: string }> = {
  GET:       { color: "#185FA5", bg: "rgba(55,138,221,.12)" },
  POST:      { color: "#0F6E56", bg: "rgba(29,158,117,.12)" },
  PATCH:     { color: "#854F0B", bg: "rgba(239,159,39,.16)" },
  PUT:       { color: "#854F0B", bg: "rgba(239,159,39,.16)" },
  DELETE:    { color: "#A32D2D", bg: "rgba(226,75,74,.12)" },
  WEBSOCKET: { color: "#534AB7", bg: "rgba(127,119,221,.14)" },
};
export function methodPill(m: string) {
  return METHOD_PILL[m.toUpperCase()] || { color: "#5F5E5A", bg: "rgba(0,0,0,.05)" };
}

export function envPill(env: Environment) {
  return env === "production"
    ? { color: "#0F6E56", bg: "rgba(29,158,117,.12)", label: "production" }
    : { color: "#854F0B", bg: "rgba(239,159,39,.15)", label: "sandbox" };
}

export function keyStatusPill(key: ApiKey): { color: string; bg: string; label: string } {
  if (key.revoked_at) return { color: "#A32D2D", bg: "rgba(226,75,74,.1)",  label: "revoked" };
  if (key.expires_at && new Date(key.expires_at) <= new Date()) {
    return { color: "#A32D2D", bg: "rgba(226,75,74,.1)", label: "expired" };
  }
  if (key.expires_at) {
    const days = (new Date(key.expires_at).getTime() - Date.now()) / 86_400_000;
    if (days < 30) return { color: "#854F0B", bg: "rgba(239,159,39,.15)", label: "истекает" };
  }
  return { color: "#0F6E56", bg: "rgba(29,158,117,.12)", label: "active" };
}
