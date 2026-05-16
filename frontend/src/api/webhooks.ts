import { api } from "./client";

// ─── Types ─────────────────────────────────────────────────────

export interface WebhookEventDef {
  code: string;
  module: string;
  label: string;
  description: string;
  payload_keys: string[];
}

export interface WebhookEventCatalog {
  events: WebhookEventDef[];
  grouped_by_module: Record<string, WebhookEventDef[]>;
}

export interface WebhookSubscription {
  id: string;
  service_account_id: string;
  created_by_id: string | null;
  name: string;
  description: string | null;
  target_url: string;
  secret_hint: string;
  verify_ssl: boolean;
  custom_headers: Record<string, string> | null;
  events: string[];
  is_active: boolean;
  disabled_at: string | null;
  disabled_reason: string | null;
  max_attempts: number;
  timeout_seconds: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  total_deliveries: number;
  total_failures: number;
  consecutive_failures: number;
  created_at: string;
  updated_at: string;
}

export interface WebhookSubscriptionCreated extends WebhookSubscription {
  plaintext_secret: string;
}

export type DeliveryStatus = "pending" | "succeeded" | "failed" | "exhausted" | "cancelled";

export interface WebhookDelivery {
  id: string;
  subscription_id: string;
  event_code: string;
  event_payload: any;
  correlation_id: string | null;
  status: DeliveryStatus;
  attempt_number: number;
  scheduled_at: string;
  attempted_at: string | null;
  completed_at: string | null;
  next_retry_at: string | null;
  signature: string | null;
  timestamp_sent: number | null;
  http_status: number | null;
  response_body_snippet: string | null;
  response_headers_snippet: Record<string, string> | null;
  error_message: string | null;
  duration_ms: number | null;
  is_replay: boolean;
  replay_of_id: string | null;
  created_at: string;
}

export interface WebhookStats {
  subscriptions: { total: number; active: number };
  pending_deliveries: number;
  last_24h: { total: number; succeeded: number; success_rate: number | null };
}

// ─── API ───────────────────────────────────────────────────────

export const webhooksApi = {
  async events(): Promise<WebhookEventCatalog> {
    const r = await api.get<WebhookEventCatalog>("/webhooks/events");
    return r.data;
  },
  async stats(): Promise<WebhookStats> {
    const r = await api.get<WebhookStats>("/webhooks/stats");
    return r.data;
  },

  async listSubscriptions(saId?: string): Promise<{ items: WebhookSubscription[]; total: number }> {
    const r = await api.get("/webhooks/subscriptions", { params: saId ? { service_account_id: saId } : {} });
    return r.data;
  },
  async createSubscription(payload: {
    service_account_id: string; name: string; description?: string | null;
    target_url: string; events: string[];
    verify_ssl: boolean; custom_headers?: Record<string, string> | null;
    max_attempts: number; timeout_seconds: number;
  }): Promise<WebhookSubscriptionCreated> {
    const r = await api.post<WebhookSubscriptionCreated>("/webhooks/subscriptions", payload);
    return r.data;
  },
  async updateSubscription(id: string, payload: Partial<{
    name: string; description: string | null;
    target_url: string; events: string[];
    verify_ssl: boolean; custom_headers: Record<string, string> | null;
    max_attempts: number; timeout_seconds: number;
    is_active: boolean;
  }>): Promise<WebhookSubscription> {
    const r = await api.patch<WebhookSubscription>(`/webhooks/subscriptions/${id}`, payload);
    return r.data;
  },
  async deleteSubscription(id: string): Promise<void> {
    await api.delete(`/webhooks/subscriptions/${id}`);
  },
  async testSubscription(id: string, payload?: Record<string, unknown>): Promise<WebhookDelivery> {
    const r = await api.post<WebhookDelivery>(`/webhooks/subscriptions/${id}/test`, { payload: payload || null });
    return r.data;
  },

  async listDeliveries(opts: {
    subscription_id?: string; status?: DeliveryStatus; event_code?: string; limit?: number;
  } = {}): Promise<{ items: WebhookDelivery[]; total: number }> {
    const r = await api.get("/webhooks/deliveries", { params: opts });
    return r.data;
  },
  async replayDelivery(id: string): Promise<WebhookDelivery> {
    const r = await api.post<WebhookDelivery>(`/webhooks/deliveries/${id}/replay`, {});
    return r.data;
  },
};

// ─── Display helpers ──────────────────────────────────────────

export function statusPill(s: DeliveryStatus): { color: string; bg: string; label: string } {
  switch (s) {
    case "succeeded": return { color: "#0F6E56", bg: "rgba(29,158,117,.12)",  label: "succeeded" };
    case "pending":   return { color: "#854F0B", bg: "rgba(239,159,39,.15)",  label: "pending" };
    case "failed":    return { color: "#854F0B", bg: "rgba(239,159,39,.18)",  label: "retry" };
    case "exhausted": return { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "exhausted" };
    case "cancelled": return { color: "#6E6A78", bg: "rgba(0,0,0,.05)",       label: "cancelled" };
  }
}

export function httpStatusPill(code: number | null): { color: string; bg: string } {
  if (code === null) return { color: "#6E6A78", bg: "rgba(0,0,0,.05)" };
  if (code >= 200 && code < 300) return { color: "#0F6E56", bg: "rgba(29,158,117,.12)" };
  if (code >= 300 && code < 400) return { color: "#185FA5", bg: "rgba(55,138,221,.12)" };
  if (code >= 400 && code < 500) return { color: "#854F0B", bg: "rgba(239,159,39,.15)" };
  return { color: "#A32D2D", bg: "rgba(226,75,74,.12)" };
}
