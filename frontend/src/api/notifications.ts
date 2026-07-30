import { api } from "./client";
import { getCurrentIntlLocale, t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";


// ─── Types ───────────────────────────────────────────────────

export type Priority = "low" | "normal" | "high" | "critical";
export type DigestMode = "none" | "daily" | "weekly";

export interface Notification {
  id: string;
  created_at: string;
  type: string;
  priority: Priority;
  title: string;
  body: string | null;
  payload: Record<string, unknown> | null;
  link_url: string | null;
  source_module: string | null;
  source_entity_id: string | null;
  source_user_id: string | null;
  is_read: boolean;
  read_at: string | null;
  is_archived: boolean;
  delivered_channels: Record<string, unknown> | null;
  expires_at: string | null;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread_count: number;
  page: number;
  per_page: number;
}

export interface UnreadCount {
  count: number;
  by_priority: Record<string, number>;
  by_type: Record<string, number>;
  by_module?: Record<string, number>;
  by_company?: Record<string, number>;
}

export interface NotificationPreference {
  notification_type: string;
  channels: Record<string, boolean>;
  is_muted: boolean;
  mute_until: string | null;
  digest_mode: DigestMode;
}

export interface NotificationType {
  code: string;
  label: string;
  priority: Priority;
  category: string;
}

// Field-level детали изменения из журнала аудита («что кто где изменял»)
export interface AuditChangeRow {
  label: string;
  old?: string | null;
  new?: string | null;
  value?: string | null;
}
export interface NotificationAuditDetail {
  found: boolean;
  action?: string | null;
  action_label?: string | null;
  module?: string | null;
  module_label?: string | null;
  section?: string | null;
  table?: string | null;
  entity_type?: string | null;
  entity_label?: string | null;
  actor_name?: string | null;
  notes?: string | null;
  at?: string | null;
  changes: AuditChangeRow[];
}

// ─── REST API ────────────────────────────────────────────────

export const notificationsApi = {
  // 30-сек тикет для WS-хендшейка (вместо access-JWT в URL). Authorization — авто.
  async wsTicket(): Promise<{ ticket: string; expires_in: number }> {
    const r = await api.post<{ ticket: string; expires_in: number }>("/notifications/ws-ticket");
    return r.data;
  },
  async feed(params: {
    unread_only?: boolean;
    types?: string[];
    priorities?: string[];
    include_archived?: boolean;
    page?: number;
    per_page?: number;
  } = {}): Promise<NotificationListResponse> {
    const r = await api.get<NotificationListResponse>("/notifications/feed", { params });
    return r.data;
  },
  async unreadCount(): Promise<UnreadCount> {
    const r = await api.get<UnreadCount>("/notifications/unread-count");
    return r.data;
  },
  async readOne(id: string) { await api.post(`/notifications/${id}/read`); },
  async readBulk(ids: string[]) { await api.post("/notifications/read-bulk", { ids }); },
  async readAll() { await api.post("/notifications/read-all"); },
  async readBy(filter: { types?: string[]; modules?: string[]; company_ids?: string[] }): Promise<number> {
    const r = await api.post<{ updated: number }>("/notifications/read-by", {
      types: filter.types || [], modules: filter.modules || [], company_ids: filter.company_ids || [],
    });
    return r.data?.updated || 0;
  },
  async archiveOne(id: string) { await api.post(`/notifications/${id}/archive`); },
  async archiveBulk(ids: string[]) { await api.post("/notifications/archive-bulk", { ids }); },
  async types(): Promise<{ types: NotificationType[]; categories: string[] }> {
    const r = await api.get<{ types: NotificationType[]; categories: string[] }>("/notifications/types");
    return r.data;
  },
  async preferences(): Promise<NotificationPreference[]> {
    const r = await api.get<NotificationPreference[]>("/notifications/preferences");
    return r.data;
  },
  async updatePreferences(prefs: Partial<NotificationPreference>[]): Promise<NotificationPreference[]> {
    const r = await api.put<NotificationPreference[]>("/notifications/preferences", { preferences: prefs });
    return r.data;
  },
  async sendTest() {
    const r = await api.post<{ sent: boolean; id: string | null }>("/notifications/test");
    return r.data;
  },
  // «До мелочей»: field-level детали изменения из журнала аудита по клику
  async auditDetail(id: string): Promise<NotificationAuditDetail> {
    const r = await api.get<NotificationAuditDetail>(`/notifications/${id}/audit-detail`);
    return r.data;
  },
};

// ─── Display helpers ─────────────────────────────────────────

export const PRIORITY_LABELS: Record<Priority, { label: string; color: string; bg: string }> = {
  low:      { label: i18nKey("Низкий"),   color: "#5F5E5A", bg: "rgba(136,135,128,.1)" },
  normal:   { label: i18nKey("Обычный"),  color: "#534AB7", bg: "rgba(127,119,221,.1)" },
  high:     { label: i18nKey("Высокий"),  color: "#854F0B", bg: "rgba(239,159,39,.12)" },
  critical: { label: "Critical", color: "#A32D2D", bg: "rgba(226,75,74,.12)" },
};

export const TYPE_ICONS: Record<string, string> = {
  "moderation.pending":          "shield-check",
  "moderation.approved":         "circle-check",
  "moderation.rejected":         "circle-x",
  "moderation.review_requested": "message-circle-question",
  "moderation.escalated":        "arrow-up-right",
  "moderation.expired":          "clock-x",
  mention:           "at",
  assignment:        "user-plus",
  "comment.replied": "message-circle",
  "deadline.approaching": "clock-hour-3",
  "deadline.missed":      "clock-exclamation",
  "kpi.target.missed":    "trending-down",
  "kpi.achieved":         "trending-up",
  "audit.security_flag":  "alert-octagon",
  "rbac.changed":         "shield-cog",
  "system.announcement":  "speakerphone",
  "data.imported":        "file-import",
  "report.ready":         "file-text",
};

export const TYPE_COLORS: Record<string, string> = {
  "moderation.pending":   "#854F0B",
  "moderation.approved":  "#0F6E56",
  "moderation.rejected":  "#A32D2D",
  "moderation.review_requested": "#185FA5",
  "moderation.escalated": "#854F0B",
  "moderation.expired":   "#5F5E5A",
  mention:           "#534AB7",
  assignment:        "#534AB7",
  "comment.replied": "#534AB7",
  "deadline.approaching": "#854F0B",
  "deadline.missed":      "#A32D2D",
  "kpi.target.missed":    "#A32D2D",
  "kpi.achieved":         "#0F6E56",
  "audit.security_flag":  "#A32D2D",
  "rbac.changed":         "#534AB7",
  "system.announcement":  "#185FA5",
  "data.imported":        "#185FA5",
  "report.ready":         "#0F6E56",
};

export function iconFor(type: string): string {
  return TYPE_ICONS[type] || "bell";
}

export function colorFor(type: string): string {
  return TYPE_COLORS[type] || "#534AB7";
}

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 30)         return t('только что');
  if (diffSec < 60)         return t('{value0} с', { value0: diffSec });
  if (diffSec < 3600)       return t('{value0} мин', { value0: Math.floor(diffSec / 60) });
  if (diffSec < 86400)      return t('{value0} ч', { value0: Math.floor(diffSec / 3600) });
  if (diffSec < 86400 * 7)  return t('{value0} д', { value0: Math.floor(diffSec / 86400) });
  return new Date(iso).toLocaleDateString(getCurrentIntlLocale());
}
