import { api } from "./client";

// ─── Types ─────────────────────────────────────────────────────

export type AckMode = "none" | "click" | "text" | "select" | "yesno" | "file";
export type ScheduleMode = "oneshot" | "interval" | "cron";
export type BroadcastTrigger = "schedule" | "manual" | "resend";
export type Priority = "low" | "normal" | "high" | "critical";

export interface TargetFilterOp {
  field: string;
  op: "=" | "!=" | ">" | ">=" | "<" | "<=";
  value: unknown;
}
export interface TargetFilterExpr {
  ops: TargetFilterOp[];
  combine: "AND" | "OR";
}
export interface ScheduleConfig {
  every_days?:   number | null;
  every_weeks?:  number | null;
  every_months?: number | null;
  weekdays?:     number[] | null;
  time?:         string | null;   // "HH:MM"
  tz?:           string | null;
  day_of_month?: number | null;
  cron?:         string | null;
}

export interface Template {
  id: string;
  created_at: string;
  updated_at: string;
  created_by_id: string;
  name: string;
  is_active: boolean;
  type: string;
  priority: Priority;
  title: string;
  body: string | null;
  link_url: string | null;
  attachments: Record<string, unknown>[] | null;
  icon: string | null;
  color: string | null;

  target_user_ids:    string[] | null;
  target_group_codes: string[] | null;
  target_role_codes:  string[] | null;
  target_company_ids: string[] | null;
  target_sector_ids:  string[] | null;
  target_all: boolean;
  target_filter_expr: TargetFilterExpr | null;

  ack_mode: AckMode;
  ack_question: string | null;
  ack_options: string[] | null;
  is_sticky: boolean;
  ack_deadline_hours: number | null;
  auto_resend_hours: number | null;
  escalate_to_manager: boolean;
  show_site_banner_on_overdue: boolean;

  schedule_mode: ScheduleMode;
  schedule_config: ScheduleConfig | null;
  schedule_start_at: string | null;
  schedule_end_at: string | null;
  next_run_at: string | null;
  last_run_at: string | null;

  total_dispatches: number;
  total_recipients_lifetime: number;
  total_acks_lifetime: number;
}

export type TemplatePayload = Omit<Template,
  "id" | "created_at" | "updated_at" | "created_by_id" |
  "next_run_at" | "last_run_at" |
  "total_dispatches" | "total_recipients_lifetime" | "total_acks_lifetime">;

export interface TemplateListItem extends Pick<Template,
  "id" | "name" | "is_active" | "type" | "priority" | "title" |
  "is_sticky" | "ack_mode" | "schedule_mode" |
  "next_run_at" | "last_run_at" |
  "total_dispatches" | "total_acks_lifetime" |
  "created_by_id" | "created_at" | "updated_at"> {}

export interface RecipientPreview {
  total: number;
  sample: { id: string; email: string; full_name: string | null }[];
}

export interface Dispatch {
  id: string;
  template_id: string;
  dispatched_at: string;
  recipients_count: number;
  delivered_count: number;
  read_count: number;
  acked_count: number;
  dispatched_by_id: string | null;
  trigger: BroadcastTrigger;
  error: string | null;
}

export interface BroadcastAnalytics {
  template_id: string;
  template_name: string;
  is_active: boolean;
  dispatches_total: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_recipients: number;
  last_delivered: number;
  last_read: number;
  last_acked: number;
  response_distribution: Record<string, number>;
  non_responders: { id: string; email: string; full_name: string | null }[];
  history: Dispatch[];
}

export interface StickyNotification {
  id: string;
  created_at: string;
  type: string;
  priority: Priority;
  title: string;
  body: string | null;
  link_url: string | null;
  is_sticky: boolean;
  requires_ack: boolean;
  ack_mode: AckMode | null;
  ack_question: string | null;
  ack_options: string[] | null;
  ack_deadline: string | null;
  acknowledged_at: string | null;
  show_site_banner: boolean;
  broadcast_template_id: string | null;
  source_user_id: string | null;
}

export interface AckPayload {
  response_text?: string;
  response_value?: string;
  response_file?: Record<string, unknown>;
}


// ─── API ───────────────────────────────────────────────────────

export const broadcastsApi = {
  // Catalog
  async catalog() {
    const r = await api.get("/admin-broadcasts/catalog");
    return r.data as {
      types: { code: string; label: string; icon: string }[];
      priorities: Priority[];
      ack_modes: { code: AckMode; label: string }[];
      schedule_modes: { code: ScheduleMode; label: string }[];
    };
  },

  // Templates CRUD
  async listTemplates(is_active?: boolean): Promise<{ items: TemplateListItem[]; total: number }> {
    const r = await api.get("/admin-broadcasts/templates", {
      params: is_active !== undefined ? { is_active } : {},
    });
    return r.data;
  },
  async getTemplate(id: string): Promise<Template> {
    const r = await api.get<Template>(`/admin-broadcasts/templates/${id}`);
    return r.data;
  },
  async createTemplate(payload: TemplatePayload): Promise<Template> {
    const r = await api.post<Template>("/admin-broadcasts/templates", payload);
    return r.data;
  },
  async updateTemplate(id: string, payload: Partial<TemplatePayload>): Promise<Template> {
    const r = await api.patch<Template>(`/admin-broadcasts/templates/${id}`, payload);
    return r.data;
  },
  async deleteTemplate(id: string) { await api.delete(`/admin-broadcasts/templates/${id}`); },
  async toggleTemplate(id: string): Promise<Template> {
    const r = await api.post<Template>(`/admin-broadcasts/templates/${id}/toggle`);
    return r.data;
  },

  // Actions
  async previewRecipients(id: string): Promise<RecipientPreview> {
    const r = await api.get<RecipientPreview>(`/admin-broadcasts/templates/${id}/preview-recipients`);
    return r.data;
  },
  async sendNow(id: string): Promise<Dispatch> {
    const r = await api.post<Dispatch>(`/admin-broadcasts/templates/${id}/send-now`);
    return r.data;
  },
  async testOnSelf(id: string): Promise<Dispatch> {
    const r = await api.post<Dispatch>(`/admin-broadcasts/templates/${id}/test-on-self`);
    return r.data;
  },

  // Analytics + history
  async dispatches(templateId: string): Promise<{ items: Dispatch[]; total: number }> {
    const r = await api.get(`/admin-broadcasts/templates/${templateId}/dispatches`);
    return r.data;
  },
  async analytics(templateId: string): Promise<BroadcastAnalytics> {
    const r = await api.get<BroadcastAnalytics>(`/admin-broadcasts/templates/${templateId}/analytics`);
    return r.data;
  },

  // Recipient-facing
  async mySticky(): Promise<StickyNotification[]> {
    const r = await api.get<StickyNotification[]>("/broadcasts/sticky");
    return r.data;
  },
  async ack(notificationId: string, payload: AckPayload) {
    const r = await api.post(`/broadcasts/${notificationId}/ack`, payload);
    return r.data;
  },
};


// ─── Display helpers ───────────────────────────────────────────

export const ACK_MODE_LABELS: Record<AckMode, string> = {
  none: "Без ответа",
  click: "Подтверждение",
  text: "Текст",
  select: "Выбор",
  yesno: "Да/Нет",
  file: "Файл",
};

export const PRIORITY_PILL: Record<Priority, { color: string; bg: string; label: string }> = {
  low:      { color: "#5F5E5A", bg: "rgba(136,135,128,.12)", label: "low" },
  normal:   { color: "#534AB7", bg: "rgba(127,119,221,.12)", label: "normal" },
  high:     { color: "#854F0B", bg: "rgba(239,159,39,.18)",  label: "high" },
  critical: { color: "#A32D2D", bg: "rgba(226,75,74,.18)",   label: "critical" },
};

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.floor((Date.now() - then) / 1000);
  if (diffSec < 0) {
    const absSec = -diffSec;
    if (absSec < 3600) return `через ${Math.floor(absSec / 60)} мин`;
    if (absSec < 86400) return `через ${Math.floor(absSec / 3600)} ч`;
    return `через ${Math.floor(absSec / 86400)} дн`;
  }
  if (diffSec < 30) return "только что";
  if (diffSec < 60) return `${diffSec} с`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} мин`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} ч`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)} д`;
  return new Date(iso).toLocaleDateString("ru-RU");
}
