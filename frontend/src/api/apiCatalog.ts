/**
 * API Catalog client (Pack 12.0 + 9aJ-extension Phase 5.1).
 * Mirrors backend/app/api/routes/api_catalog.py.
 */
import { api } from "./client";

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE" | "WEBSOCKET";
export type AccessLevel = "public" | "authed" | "admin";

export interface CatalogEndpoint {
  path: string;
  method: HttpMethod;
  operation_id: string | null;
  summary: string | null;
  description: string | null;
  tags: string[];
  module: string | null;
  required_permission: string | null;
  request_schema_ref?: string | null;
  response_schema_ref?: string | null;
  deprecated: boolean;
}

export interface CatalogEndpointWithSubstitution extends CatalogEndpoint {
  display_path: string;
  substitutions: Record<string, string>;
  access_level: AccessLevel;
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

export interface CompanyCatalogResponse {
  company_id: string;
  company_name: string;
  endpoints: CatalogEndpointWithSubstitution[];
  tabs: string[];
  access_level: AccessLevel;
}

export interface TryRequest {
  method: HttpMethod;
  path: string;
  headers?: Record<string, string>;
  body?: Record<string, any> | null;
  confirm_destructive?: boolean;
}

export interface TryResponse {
  status_code: number;
  headers: Record<string, string>;
  body: string | null;
  duration_ms: number;
  truncated: boolean;
}

export interface CatalogStatus {
  operational: boolean;
  title: string;
  version: string;
}

export const apiCatalog = {
  summary() {
    return api.get<CatalogSummary>("/api-catalog/summary").then(r => r.data);
  },
  byCompany(companyId: string, tab?: string) {
    return api.get<CompanyCatalogResponse>(
      `/api-catalog/by-company/${companyId}`,
      { params: tab ? { tab } : {} },
    ).then(r => r.data);
  },
  try(req: TryRequest) {
    return api.post<TryResponse>("/api-catalog/try", req).then(r => r.data);
  },
  status() {
    return api.get<CatalogStatus>("/api-catalog/status").then(r => r.data);
  },
  scopes() {
    return api.get("/api-catalog/scopes").then(r => r.data);
  },
};
