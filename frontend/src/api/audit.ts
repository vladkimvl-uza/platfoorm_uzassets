import { api } from "./client";

// ─── Types matching backend Pydantic schemas ─────────────────

export interface AuditEventRead {
  id: string;
  created_at: string;
  actor_id: string | null;
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
  has_diff: boolean;
  has_payload: boolean;
}

export interface AuditEventDetail extends AuditEventRead {
  user_agent: string | null;
  diff: Record<string, unknown> | null;
  payload: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  notes: string | null;
  prev_hash: string | null;
  entry_hash: string | null;
}

export interface AuditEventList {
  items: AuditEventRead[];
  total: number;
  page: number;
  per_page: number;
}

export interface AuditStat {
  key: string;
  label: string;
  value: number;
  delta_pct: number | null;
  sub: string | null;
  accent: string | null;
}

export interface AuditStatsResponse {
  period_hours: number;
  events_total: number;
  unique_users: number;
  online_users: number;
  changes: number;
  views: number;
  errors: number;
  critical: number;
  stats: AuditStat[];
}

export interface AuditTopUser {
  actor_id: string | null;
  email: string;
  initials: string;
  count: number;
  accent: string;
}

export interface AuditTopModule {
  module: string;
  label: string;
  count: number;
}

export interface AuditSecurityFlag {
  id: string;
  severity: "critical" | "warning" | "info";
  kind: string;
  title: string;
  detail: string;
  created_at: string;
  related_user_email: string | null;
  related_ip: string | null;
  is_resolved: boolean;
}

export interface AuditTimelineBucket {
  ts: string;
  view: number;
  update: number;
  create: number;
  delete: number;
  error: number;
  login: number;
}

export interface AuditTimelineResponse {
  bucket: "hour" | "day";
  buckets: AuditTimelineBucket[];
}

export interface AuditOverviewResponse {
  stats: AuditStatsResponse;
  top_users: AuditTopUser[];
  top_modules: AuditTopModule[];
  security_flags: AuditSecurityFlag[];
  timeline: AuditTimelineResponse;
  recent_events: AuditEventRead[];
}

// ─── API client ─────────────────────────────────────────────

export const auditApi = {
  async overview(hours = 24): Promise<AuditOverviewResponse> {
    const r = await api.get<AuditOverviewResponse>("/admin/audit/overview", {
      params: { hours },
    });
    return r.data;
  },

  async listEvents(params: {
    actor_email?: string;
    module?: string;
    action?: string;
    hours?: number;
    search?: string;
    only_critical?: boolean;
    page?: number;
    per_page?: number;
  } = {}): Promise<AuditEventList> {
    const r = await api.get<AuditEventList>("/admin/audit/events", { params });
    return r.data;
  },

  async eventDetail(id: string): Promise<AuditEventDetail> {
    const r = await api.get<AuditEventDetail>(`/admin/audit/events/${id}`);
    return r.data;
  },

  async stats(hours = 24): Promise<AuditStatsResponse> {
    const r = await api.get<AuditStatsResponse>("/admin/audit/stats", {
      params: { hours },
    });
    return r.data;
  },

  async timeline(hours = 24, bucket: "hour" | "day" = "hour"): Promise<AuditTimelineResponse> {
    const r = await api.get<AuditTimelineResponse>("/admin/audit/timeline", {
      params: { hours, bucket },
    });
    return r.data;
  },

  exportCsvUrl(hours = 24): string {
    return `/admin/audit/export.csv?hours=${hours}`;
  },
};

// ─── Display helpers ────────────────────────────────────────

export const ACTION_META: Record<string, { color: string; bg: string; label: string; icon: string }> = {
  VIEW:         { color: "#185FA5", bg: "rgba(55,138,221,.12)",  label: "VIEW",    icon: "eye" },
  CREATE:       { color: "#534AB7", bg: "rgba(127,119,221,.12)", label: "CREATE",  icon: "plus" },
  UPDATE:       { color: "#0F6E56", bg: "rgba(29,158,117,.12)",  label: "UPDATE",  icon: "edit" },
  DELETE:       { color: "#993556", bg: "rgba(212,83,126,.12)",  label: "DELETE",  icon: "trash" },
  EXPORT:       { color: "#A36500", bg: "rgba(239,159,39,.12)",  label: "EXPORT",  icon: "download" },
  IMPORT:       { color: "#A36500", bg: "rgba(239,159,39,.12)",  label: "IMPORT",  icon: "upload" },
  LOGIN:        { color: "#0F6E56", bg: "rgba(29,158,117,.12)",  label: "LOGIN",   icon: "login" },
  LOGOUT:       { color: "#5F5E5A", bg: "rgba(0,0,0,.06)",       label: "LOGOUT",  icon: "logout" },
  FAILED:       { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "FAILED",  icon: "alert" },
  FAILED_LOGIN: { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "FAILED",  icon: "alert" },
  ERROR:        { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "ERROR",   icon: "alert" },
};

export function actionMeta(action: string) {
  return ACTION_META[action] || { color: "#5F5E5A", bg: "rgba(0,0,0,.06)", label: action, icon: "circle" };
}

export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}с назад`;
  if (sec < 3600) return `${Math.floor(sec / 60)}мин назад`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}ч назад`;
  return d.toLocaleDateString("ru-RU");
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateShort(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "сегодня";
  const yest = new Date(today);
  yest.setDate(yest.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return "вчера";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}
