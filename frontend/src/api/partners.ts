import { api } from "./client";
import { i18nKey } from "@/locale/keys";

export type PartnerKind   = "gov_ministry" | "portfolio_company" | "saas_vendor" | "bank" | "integrator" | "other";
export type PartnerStatus = "active" | "suspended" | "terminated";
export type PartnerTier   = "platinum" | "gold" | "silver" | "standard";

export const PARTNER_KIND_LABELS: Record<PartnerKind, string> = {
  gov_ministry:      i18nKey("Министерство"),
  portfolio_company: i18nKey("Портфельная компания"),
  saas_vendor:       i18nKey("SaaS-провайдер"),
  bank:              i18nKey("Банк"),
  integrator:        i18nKey("Системный интегратор"),
  other:             i18nKey("Другое"),
};

export interface PartnerContact {
  name: string;
  email?: string | null;
  phone?: string | null;
  role?:  string | null;
}

export interface IntegrationPartner {
  id: string;
  slug: string;
  name: string;
  legal_name: string | null;
  description: string | null;
  kind: PartnerKind | null;
  status: PartnerStatus;
  tier: PartnerTier | null;
  contacts: PartnerContact[] | null;
  tags: string[] | null;
  contract_ref: string | null;
  contract_start: string | null;
  contract_end:   string | null;
  owner_id: string | null;
  created_by_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  service_accounts_count: number;
  api_keys_count: number;
  webhooks_count: number;
  external_apis_count: number;
}

export interface LinkedResource {
  resource_type: "service_account" | "external_api" | "webhook";
  resource_id: string;
  label: string;
  extra?: Record<string, unknown> | null;
}

export interface PartnerResources {
  partner_id: string;
  service_accounts: LinkedResource[];
  external_apis:    LinkedResource[];
  webhooks:         LinkedResource[];
}

export const partnersApi = {
  async list(q?: string, status?: PartnerStatus): Promise<{ items: IntegrationPartner[]; total: number }> {
    const params: any = {};
    if (q) params.q = q;
    if (status) params.status = status;
    const r = await api.get("/partners", { params });
    return r.data;
  },
  async get(id: string): Promise<IntegrationPartner> {
    const r = await api.get<IntegrationPartner>(`/partners/${id}`);
    return r.data;
  },
  async create(payload: Partial<IntegrationPartner> & { slug: string; name: string }): Promise<IntegrationPartner> {
    const r = await api.post<IntegrationPartner>("/partners", payload);
    return r.data;
  },
  async update(id: string, payload: Partial<IntegrationPartner>): Promise<IntegrationPartner> {
    const r = await api.patch<IntegrationPartner>(`/partners/${id}`, payload);
    return r.data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/partners/${id}`);
  },
  async resources(id: string): Promise<PartnerResources> {
    const r = await api.get<PartnerResources>(`/partners/${id}/resources`);
    return r.data;
  },
  async attach(id: string, resource_type: LinkedResource["resource_type"], resource_id: string): Promise<void> {
    await api.post(`/partners/${id}/links`, { resource_type, resource_id });
  },
  async detach(id: string, resource_type: LinkedResource["resource_type"], resource_id: string): Promise<void> {
    await api.delete(`/partners/${id}/links`, { data: { resource_type, resource_id } });
  },
};

// ─── Audit log endpoints + filters) ────

export interface AuditEvent {
  id: string;
  created_at: string;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  module: string | null;
  entity_type: string | null;
  entity_id: string | null;
  entity_label: string | null;
  http_method: string | null;
  http_path: string | null;
  http_status: number | null;
  duration_ms: number | null;
  ip_address: string | null;
  is_critical: boolean;
  api_key_id?: string | null;
}

export const auditApi = {
  async events(opts: {
    actor_email?: string; module?: string; action?: string;
    hours?: number; search?: string; only_critical?: boolean;
    api_key_id?: string; only_api_key?: boolean;
    page?: number; per_page?: number;
  } = {}): Promise<{ items: AuditEvent[]; total: number; page: number; per_page: number }> {
    const r = await api.get("/audit/events", { params: opts });
    return r.data;
  },
  async event(id: string) {
    const r = await api.get(`/audit/events/${id}`);
    return r.data;
  },
  async overview() {
    const r = await api.get("/audit/overview");
    return r.data;
  },
};

// ─── Display helpers ───────────────────────────────────────

export function partnerStatusPill(s: PartnerStatus): { color: string; bg: string; label: string } {
  switch (s) {
    case "active":     return { color: "#0F6E56", bg: "rgba(29,158,117,.12)", label: "active" };
    case "suspended":  return { color: "#854F0B", bg: "rgba(239,159,39,.15)", label: "suspended" };
    case "terminated": return { color: "#A32D2D", bg: "rgba(226,75,74,.1)",   label: "terminated" };
  }
}

export function partnerTierColor(t: PartnerTier | null): string {
  switch (t) {
    case "platinum": return "#7F77DD";
    case "gold":     return "#EF9F27";
    case "silver":   return "#6E6A78";
    case "standard": return "#378ADD";
    default:         return "#cfd0d6";
  }
}

export function httpStatusColor(code: number | null): string {
  if (code === null) return "#6E6A78";
  if (code >= 200 && code < 300) return "#0F6E56";
  if (code >= 300 && code < 400) return "#185FA5";
  if (code >= 400 && code < 500) return "#854F0B";
  return "#A32D2D";
}
